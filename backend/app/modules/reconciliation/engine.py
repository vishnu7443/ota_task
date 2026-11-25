"""Deterministic cross-module reconciliation engine (read-only evaluators, zero mutations)."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.modules.billing.models import (
    Dispatch,
    Invoice,
)
from app.modules.costing.models import ProductionCostSummary
from app.modules.finance.models import CustomerReceivable, Payment
from app.modules.inventory.models import (
    CostLot,
    InventoryBalance,
    InventoryMovement,
    Material,
    UnitConversion,
)
from app.modules.orders.models import SalesOrder
from app.modules.production.models import ProductionRun
from app.modules.purchasing.models import PurchaseReceipt
from app.modules.reconciliation.schemas import (
    DispatchReconciliationRowOut,
    InventoryReconciliationRowOut,
    InvoiceReconciliationRowOut,
    PaymentReconciliationRowOut,
    ProductionReconciliationRowOut,
    SalesReconciliationRowOut,
)
from app.modules.sales.models import Customer, PackSize

IST = ZoneInfo("Asia/Kolkata")
QTY_TOLERANCE = Decimal("0.0005")


@dataclass
class DiscrepancyCandidate:
    domain: str
    discrepancy_code: str
    severity: str
    entity_schema: str
    entity_table: str
    entity_id: int
    entity_ref: str
    expected_value: dict[str, Any]
    actual_value: dict[str, Any]
    difference_summary: str


def _ist_date_range_to_utc(
    period_start: date, period_end: date, cutoff_at: datetime
) -> tuple[datetime, datetime]:
    start_utc = datetime.combine(period_start, time.min, tzinfo=IST).astimezone(UTC)
    end_bound = datetime.combine(period_end, time.max, tzinfo=IST).astimezone(UTC)
    effective_end = cutoff_at if cutoff_at.tzinfo else cutoff_at.replace(tzinfo=UTC)
    effective_end = min(effective_end, end_bound)
    return start_utc, effective_end


def evaluate_inventory_reconciliation(
    db: Session,
    *,
    period_start: date,
    period_end: date,
    cutoff_at: datetime,
    item_category: str | None = None,
    material_id: int | None = None,
    pack_size_id: int | None = None,
) -> tuple[list[InventoryReconciliationRowOut], list[DiscrepancyCandidate]]:
    """Recompute Opening + Inward - Outward from InventoryMovement and compare against balances & lots."""
    start_utc, end_utc = _ist_date_range_to_utc(period_start, period_end, cutoff_at)

    # Display factors for Materials
    uc_rows = db.execute(select(UnitConversion)).scalars().all()
    uc_map = {(u.from_uom, u.to_base_uom): Decimal(u.multiplier) for u in uc_rows}

    mats = db.execute(select(Material).order_by(Material.code.asc())).scalars().all()
    packs = db.execute(select(PackSize).order_by(PackSize.sku_code.asc())).scalars().all()

    bal_rows = db.execute(select(InventoryBalance)).scalars().all()
    mat_bal = {b.material_id: Decimal(b.on_hand_qty_base) for b in bal_rows if b.material_id is not None}
    ps_bal = {b.pack_size_id: Decimal(b.on_hand_qty_base) for b in bal_rows if b.pack_size_id is not None}

    lot_rows = db.execute(select(CostLot).where(CostLot.remaining_qty_base > 0)).scalars().all()
    mat_lot_sum: dict[int, Decimal] = defaultdict(Decimal)
    ps_lot_sum: dict[int, Decimal] = defaultdict(Decimal)
    for lot in lot_rows:
        if lot.material_id is not None:
            mat_lot_sum[lot.material_id] += Decimal(lot.remaining_qty_base)
        elif lot.pack_size_id is not None:
            ps_lot_sum[lot.pack_size_id] += Decimal(lot.remaining_qty_base)

    movs = (
        db.execute(
            select(InventoryMovement)
            .where(InventoryMovement.occurred_at <= end_utc)
            .order_by(InventoryMovement.id.asc())
        )
        .scalars()
        .all()
    )
    # Deduplicate strictly by movement id and also collect later movements to detect cutoff lag
    later_mov_keys: set[tuple[str, int]] = set()
    latest_movs = db.execute(
        select(InventoryMovement.material_id, InventoryMovement.pack_size_id).where(
            InventoryMovement.occurred_at > end_utc
        )
    ).all()
    for mid, pid in latest_movs:
        if mid is not None:
            later_mov_keys.add(("MATERIAL", int(mid)))
        elif pid is not None:
            later_mov_keys.add(("PACK_SIZE", int(pid)))

    mat_movs: dict[int, list[InventoryMovement]] = defaultdict(list)
    ps_movs: dict[int, list[InventoryMovement]] = defaultdict(list)
    seen_mov_ids: set[int] = set()
    for m in movs:
        if m.id in seen_mov_ids:
            continue
        seen_mov_ids.add(m.id)
        if m.material_id is not None:
            mat_movs[m.material_id].append(m)
        elif m.pack_size_id is not None:
            ps_movs[m.pack_size_id].append(m)

    rows: list[InventoryReconciliationRowOut] = []
    discrepancies: list[DiscrepancyCandidate] = []

    def _compute_item(
        *,
        itype: str,
        iid: int,
        code: str,
        name: str,
        icat: str,
        base_uom: str,
        disp_uom: str,
        disp_factor: Decimal,
        item_movs: list[InventoryMovement],
        persisted_bal: Decimal,
        lot_rem: Decimal,
    ) -> None:
        opening = Decimal(0)
        in_pur = Decimal(0)
        in_prd = Decimal(0)
        in_ret = Decimal(0)
        in_adj = Decimal(0)
        out_prd_iss = Decimal(0)
        out_dsp = Decimal(0)
        out_dmg = Decimal(0)
        out_sup = Decimal(0)
        out_adj = Decimal(0)

        for mv in item_movs:
            qty = Decimal(mv.signed_qty_base)
            occ = mv.occurred_at if mv.occurred_at.tzinfo else mv.occurred_at.replace(tzinfo=UTC)
            if occ < start_utc or mv.movement_type == "OPENING":
                opening += qty
                continue
            mt = mv.movement_type
            if mt == "PURCHASE_IN":
                in_pur += qty
            elif mt == "PROD_OUTPUT_IN":
                in_prd += qty
            elif mt in {"PROD_RETURN_IN", "CREDIT_RETURN_IN"}:
                in_ret += qty
            elif mt == "ADJUSTMENT":
                if qty > 0:
                    in_adj += qty
                else:
                    out_adj += abs(qty)
            elif mt == "PROD_ISSUE_OUT":
                out_prd_iss += abs(qty)
            elif mt == "DISPATCH_OUT":
                out_dsp += abs(qty)
            elif mt in {"PACKAGING_DAMAGE_OUT", "DAMAGE_WASTAGE"}:
                out_dmg += abs(qty)
            elif mt == "SUPPLIER_RETURN":
                out_sup += abs(qty)

        tot_in = in_pur + in_prd + in_ret + in_adj
        tot_out = out_prd_iss + out_dsp + out_dmg + out_sup + out_adj
        expected = opening + tot_in - tot_out

        # Compare live InventoryBalance when no movements exist beyond cutoff; otherwise compare all-time ledger vs persisted
        has_future = (itype, iid) in later_mov_keys
        diff = Decimal(0) if has_future else (persisted_bal - expected)
        lot_diff = Decimal(0) if has_future else (persisted_bal - lot_rem)
        is_mismatch = abs(diff) > QTY_TOLERANCE or abs(lot_diff) > QTY_TOLERANCE

        rows.append(
            InventoryReconciliationRowOut(
                item_type=itype,
                item_id=iid,
                code=code,
                name=name,
                item_category=icat,
                base_uom=base_uom,
                display_uom=disp_uom,
                display_factor=disp_factor,
                opening_qty_base=opening.quantize(Decimal("0.001")),
                inward_purchase_qty_base=in_pur.quantize(Decimal("0.001")),
                inward_production_qty_base=in_prd.quantize(Decimal("0.001")),
                inward_returns_qty_base=in_ret.quantize(Decimal("0.001")),
                inward_adjustment_qty_base=in_adj.quantize(Decimal("0.001")),
                total_inward_qty_base=tot_in.quantize(Decimal("0.001")),
                outward_production_issue_qty_base=out_prd_iss.quantize(Decimal("0.001")),
                outward_dispatch_qty_base=out_dsp.quantize(Decimal("0.001")),
                outward_damage_wastage_qty_base=out_dmg.quantize(Decimal("0.001")),
                outward_supplier_return_qty_base=out_sup.quantize(Decimal("0.001")),
                outward_adjustment_qty_base=out_adj.quantize(Decimal("0.001")),
                total_outward_qty_base=tot_out.quantize(Decimal("0.001")),
                expected_closing_qty_base=expected.quantize(Decimal("0.001")),
                persisted_closing_qty_base=persisted_bal.quantize(Decimal("0.001")),
                difference_qty_base=diff.quantize(Decimal("0.001")),
                cost_lot_remaining_qty_base=lot_rem.quantize(Decimal("0.001")),
                cost_lot_difference_qty_base=lot_diff.quantize(Decimal("0.001")),
                status="MISMATCH" if is_mismatch else "MATCHED",
            )
        )

        if abs(diff) > QTY_TOLERANCE:
            discrepancies.append(
                DiscrepancyCandidate(
                    domain="INVENTORY",
                    discrepancy_code="INV_BAL_MISMATCH",
                    severity="HIGH",
                    entity_schema="inventory",
                    entity_table="inventory_balances",
                    entity_id=iid,
                    entity_ref=f"{code} ({itype})",
                    expected_value={
                        "expected_closing_qty_base": str(expected.quantize(Decimal("0.001"))),
                        "base_uom": base_uom,
                        "item_type": itype,
                        "item_id": iid,
                    },
                    actual_value={
                        "persisted_on_hand_qty_base": str(persisted_bal.quantize(Decimal("0.001"))),
                        "base_uom": base_uom,
                    },
                    difference_summary=f"{code} persisted balance ({persisted_bal} {base_uom}) differs from ledger sum ({expected} {base_uom}) by {diff} {base_uom}.",
                )
            )
        if abs(lot_diff) > QTY_TOLERANCE:
            discrepancies.append(
                DiscrepancyCandidate(
                    domain="INVENTORY",
                    discrepancy_code="COST_LOT_MISMATCH",
                    severity="MEDIUM",
                    entity_schema="inventory",
                    entity_table="cost_lots",
                    entity_id=iid,
                    entity_ref=f"{code} ({itype})",
                    expected_value={"balance_on_hand_qty_base": str(persisted_bal.quantize(Decimal("0.001")))},
                    actual_value={"open_cost_lot_sum_base": str(lot_rem.quantize(Decimal("0.001")))},
                    difference_summary=f"{code} balance ({persisted_bal} {base_uom}) does not equal open CostLot remaining sum ({lot_rem} {base_uom}).",
                )
            )

    if pack_size_id is None and item_category != "FINISHED_GOOD":
        for mat in mats:
            if item_category and mat.material_category != item_category:
                continue
            if material_id and mat.id != material_id:
                continue
            factor = Decimal(1) if mat.display_uom == mat.base_uom else uc_map.get((mat.display_uom, mat.base_uom), Decimal(1))
            _compute_item(
                itype="MATERIAL",
                iid=mat.id,
                code=mat.code,
                name=mat.name,
                icat=mat.material_category,
                base_uom=mat.base_uom,
                disp_uom=mat.display_uom,
                disp_factor=factor,
                item_movs=mat_movs.get(mat.id, []),
                persisted_bal=mat_bal.get(mat.id, Decimal(0)),
                lot_rem=mat_lot_sum.get(mat.id, Decimal(0)),
            )

    if material_id is None and item_category in (None, "FINISHED_GOOD"):
        for ps in packs:
            if pack_size_id and ps.id != pack_size_id:
                continue
            _compute_item(
                itype="PACK_SIZE",
                iid=ps.id,
                code=ps.sku_code,
                name=ps.display_name,
                icat="FINISHED_GOOD",
                base_uom="packet",
                disp_uom="packet",
                disp_factor=Decimal(1),
                item_movs=ps_movs.get(ps.id, []),
                persisted_bal=ps_bal.get(ps.id, Decimal(0)),
                lot_rem=ps_lot_sum.get(ps.id, Decimal(0)),
            )

    # Also verify posted PurchaseReceiptItems against PURCHASE_IN ledger entries in period
    if material_id is None and pack_size_id is None and item_category != "FINISHED_GOOD":
        pr_rows = (
            db.execute(
                select(PurchaseReceipt)
                .options(selectinload(PurchaseReceipt.items))
                .where(
                    PurchaseReceipt.status.in_(["POSTED", "RECEIVED", "CLOSED"]),
                    PurchaseReceipt.receipt_date >= period_start,
                    PurchaseReceipt.receipt_date <= period_end,
                )
            )
            .scalars()
            .all()
        )
        pur_mov_by_pri: dict[int, Decimal] = defaultdict(Decimal)
        for m in movs:
            if m.movement_type == "PURCHASE_IN" and m.purchase_receipt_item_id is not None:
                pur_mov_by_pri[m.purchase_receipt_item_id] += Decimal(m.signed_qty_base)
        for pr in pr_rows:
            for item in pr.items:
                expected_acc = Decimal(item.accepted_qty_base)
                ledger_qty = pur_mov_by_pri.get(item.id, Decimal(0))
                if abs(expected_acc - ledger_qty) > QTY_TOLERANCE:
                    discrepancies.append(
                        DiscrepancyCandidate(
                            domain="PURCHASING",
                            discrepancy_code="PR_ACC_VS_LEDGER_MISMATCH",
                            severity="HIGH",
                            entity_schema="purchasing",
                            entity_table="purchase_receipts",
                            entity_id=pr.id,
                            entity_ref=f"{pr.receipt_number}#item-{item.id}",
                            expected_value={"accepted_qty_base": str(expected_acc)},
                            actual_value={"ledger_purchase_in_base": str(ledger_qty)},
                            difference_summary=f"GRN {pr.receipt_number} accepted {expected_acc}, ledger posted {ledger_qty}.",
                        )
                    )

    return rows, discrepancies


def evaluate_sales_reconciliation(
    db: Session, *, period_start: date, period_end: date
) -> tuple[list[SalesReconciliationRowOut], list[DiscrepancyCandidate]]:
    """Cross-check SalesOrders vs GST Invoices for uninvoiced approvals, duplicates & qty mismatches."""
    orders = (
        db.execute(
            select(SalesOrder)
            .options(selectinload(SalesOrder.items))
            .where(
                SalesOrder.order_date >= period_start,
                SalesOrder.order_date <= period_end,
                SalesOrder.status != "DRAFT",
            )
            .order_by(SalesOrder.id.desc())
        )
        .scalars()
        .all()
    )
    cust_ids = {o.customer_id for o in orders}
    cust_map = (
        {c.id: c for c in db.execute(select(Customer).where(Customer.id.in_(cust_ids))).scalars().all()}
        if cust_ids
        else {}
    )
    ord_ids = [o.id for o in orders]
    invs = (
        db.execute(
            select(Invoice)
            .options(selectinload(Invoice.items))
            .where(Invoice.sales_order_id.in_(ord_ids))
        )
        .scalars()
        .all()
        if ord_ids
        else []
    )
    inv_by_order: dict[int, list[Invoice]] = defaultdict(list)
    for inv in invs:
        inv_by_order[inv.sales_order_id].append(inv)

    rows: list[SalesReconciliationRowOut] = []
    discrepancies: list[DiscrepancyCandidate] = []

    for o in orders:
        cust = cust_map.get(o.customer_id)
        ord_qty = sum((it.approved_qty_pkts if it.approved_qty_pkts is not None else it.ordered_qty_pkts) for it in o.items)
        all_invs = inv_by_order.get(o.id, [])
        active_invs = [i for i in all_invs if i.doc_status != "CANCELLED_BY_CN"]
        issued_invs = [i for i in active_invs if i.doc_status == "ISSUED"]
        inv_qty = sum(sum(ii.qty_pkts for ii in i.items) for i in issued_invs)
        inv_nums = [i.invoice_number or i.draft_ref for i in all_invs]

        issue_code: str | None = None
        issue_detail: str | None = None

        if len(active_invs) > 1:
            issue_code = "DUPLICATE_ACTIVE_INVOICE"
            issue_detail = f"Order {o.order_number} has {len(active_invs)} active invoices."
        elif o.status == "APPROVED" and len(issued_invs) == 0:
            issue_code = "APPROVED_ORDER_UNINVOICED"
            issue_detail = f"Approved order {o.order_number} ({ord_qty} pkts) has no issued GST invoice yet."
        elif o.status in {"INVOICED", "PARTIALLY_DISPATCHED", "DISPATCHED"} and len(issued_invs) == 0:
            issue_code = "ORDER_STATUS_INV_MISMATCH"
            issue_detail = f"Order {o.order_number} is {o.status} without an active ISSUED invoice."
        elif o.status in {"CANCELLED", "REJECTED"} and len(issued_invs) > 0:
            issue_code = "CANCELLED_ORDER_ACTIVE_INVOICE"
            issue_detail = f"Order {o.order_number} is {o.status} but invoice {issued_invs[0].invoice_number} remains ISSUED."
        elif len(issued_invs) == 1 and inv_qty != ord_qty:
            issue_code = "ORDER_INV_QTY_MISMATCH"
            issue_detail = f"Order {o.order_number} qty ({ord_qty}) differs from invoice qty ({inv_qty})."

        if issue_code:
            severity = "CRITICAL" if issue_code in {"DUPLICATE_ACTIVE_INVOICE", "CANCELLED_ORDER_ACTIVE_INVOICE", "ORDER_INV_QTY_MISMATCH"} else "MEDIUM"
            discrepancies.append(
                DiscrepancyCandidate(
                    domain="SALES",
                    discrepancy_code=issue_code,
                    severity=severity,
                    entity_schema="sales",
                    entity_table="sales_orders",
                    entity_id=o.id,
                    entity_ref=o.order_number,
                    expected_value={"order_status": o.status, "ordered_qty_pkts": ord_qty},
                    actual_value={"active_invoices": len(active_invs), "invoiced_qty_pkts": inv_qty, "invoice_numbers": inv_nums},
                    difference_summary=issue_detail or issue_code,
                )
            )

        rows.append(
            SalesReconciliationRowOut(
                sales_order_id=o.id,
                order_number=o.order_number,
                order_date=o.order_date,
                order_status=o.status,
                customer_name=cust.name if cust else f"Customer#{o.customer_id}",
                ordered_qty_pkts=ord_qty,
                invoiced_qty_pkts=inv_qty,
                active_invoice_count=len(active_invs),
                invoice_numbers=inv_nums,
                status="DISCREPANCY" if issue_code else "MATCHED",
                issue_code=issue_code,
                issue_detail=issue_detail,
            )
        )

    return rows, discrepancies


def evaluate_invoice_reconciliation(
    db: Session, *, period_start: date, period_end: date
) -> tuple[list[InvoiceReconciliationRowOut], list[DiscrepancyCandidate]]:
    """Verify invoice line sums, GST CGST/SGST/IGST split rules, grand totals & credit note parity."""
    invs = (
        db.execute(
            select(Invoice)
            .options(selectinload(Invoice.items), selectinload(Invoice.credit_notes))
            .where(
                Invoice.invoice_date >= period_start,
                Invoice.invoice_date <= period_end,
                Invoice.doc_status != "DRAFT",
            )
            .order_by(Invoice.id.desc())
        )
        .scalars()
        .all()
    )

    rows: list[InvoiceReconciliationRowOut] = []
    discrepancies: list[DiscrepancyCandidate] = []

    for inv in invs:
        comp_taxable = sum(int(it.taxable_paisa) for it in inv.items)
        comp_cgst = sum(int(it.cgst_paisa) for it in inv.items)
        comp_sgst = sum(int(it.sgst_paisa) for it in inv.items)
        comp_igst = sum(int(it.igst_paisa) for it in inv.items)
        comp_tax = comp_cgst + comp_sgst + comp_igst
        comp_grand = comp_taxable + comp_tax + int(inv.round_off_paisa)
        pers_tax = int(inv.cgst_total_paisa) + int(inv.sgst_total_paisa) + int(inv.igst_total_paisa)
        comp_cred = sum(int(cn.total_reversed_paisa) for cn in inv.credit_notes if cn.status == "ISSUED")

        issue_code: str | None = None
        issue_detail: str | None = None

        if comp_taxable != int(inv.taxable_total_paisa) or comp_tax != pers_tax or comp_grand != int(inv.grand_total_paisa):
            issue_code = "INV_LINE_SUM_MISMATCH"
            issue_detail = (
                f"Invoice {inv.invoice_number} persisted total ({inv.grand_total_paisa} p) != "
                f"line recomputation ({comp_grand} p)."
            )
        elif inv.supply_type == "INTRA_STATE" and (int(inv.igst_total_paisa) != 0 or int(inv.cgst_total_paisa) != int(inv.sgst_total_paisa)):
            issue_code = "INV_GST_SPLIT_MISMATCH"
            issue_detail = f"Intra-state {inv.invoice_number} violates CGST == SGST & IGST == 0 rule."
        elif inv.supply_type == "INTER_STATE" and (int(inv.cgst_total_paisa) != 0 or int(inv.sgst_total_paisa) != 0):
            issue_code = "INV_GST_SPLIT_MISMATCH"
            issue_detail = f"Inter-state {inv.invoice_number} has non-zero CGST/SGST."
        elif comp_cred != int(inv.credited_paisa):
            issue_code = "INV_CN_CREDITED_MISMATCH"
            issue_detail = f"Invoice {inv.invoice_number} credited_paisa ({inv.credited_paisa}) != sum of ISSUED CNs ({comp_cred})."
        elif inv.doc_status == "CANCELLED_BY_CN" and int(inv.credited_paisa) != int(inv.grand_total_paisa):
            issue_code = "CANCELLED_INV_CREDITED_INCOMPLETE"
            issue_detail = f"CANCELLED_BY_CN {inv.invoice_number} credited ({inv.credited_paisa}) != grand total ({inv.grand_total_paisa})."

        if issue_code:
            discrepancies.append(
                DiscrepancyCandidate(
                    domain="GST" if "GST" in issue_code else "INVOICE",
                    discrepancy_code=issue_code,
                    severity="CRITICAL",
                    entity_schema="billing",
                    entity_table="invoices",
                    entity_id=inv.id,
                    entity_ref=inv.invoice_number or inv.draft_ref,
                    expected_value={
                        "taxable_paisa": comp_taxable,
                        "tax_paisa": comp_tax,
                        "grand_total_paisa": comp_grand,
                        "credited_paisa": comp_cred,
                    },
                    actual_value={
                        "taxable_paisa": int(inv.taxable_total_paisa),
                        "tax_paisa": pers_tax,
                        "grand_total_paisa": int(inv.grand_total_paisa),
                        "credited_paisa": int(inv.credited_paisa),
                    },
                    difference_summary=issue_detail or issue_code,
                )
            )

        rows.append(
            InvoiceReconciliationRowOut(
                invoice_id=inv.id,
                invoice_number=inv.invoice_number or inv.draft_ref,
                invoice_date=inv.invoice_date,
                doc_status=inv.doc_status,
                supply_type=inv.supply_type,
                persisted_taxable_paisa=int(inv.taxable_total_paisa),
                computed_taxable_paisa=comp_taxable,
                persisted_tax_paisa=pers_tax,
                computed_tax_paisa=comp_tax,
                persisted_grand_total_paisa=int(inv.grand_total_paisa),
                computed_grand_total_paisa=comp_grand,
                persisted_credited_paisa=int(inv.credited_paisa),
                computed_credited_paisa=comp_cred,
                status="DISCREPANCY" if issue_code else "MATCHED",
                issue_code=issue_code,
                issue_detail=issue_detail,
            )
        )

    return rows, discrepancies


def evaluate_payment_reconciliation(
    db: Session, *, period_start: date, period_end: date
) -> tuple[list[PaymentReconciliationRowOut], list[DiscrepancyCandidate]]:
    """Verify Payment allocations, refunds, unallocated balances, invoice paid_paisa & AR parity."""
    payments = (
        db.execute(
            select(Payment)
            .options(selectinload(Payment.allocations), selectinload(Payment.refunds))
            .where(Payment.payment_date >= period_start, Payment.payment_date <= period_end)
            .order_by(Payment.id.desc())
        )
        .scalars()
        .all()
    )
    cust_ids = {p.customer_id for p in payments}
    cust_map = (
        {c.id: c for c in db.execute(select(Customer).where(Customer.id.in_(cust_ids))).scalars().all()}
        if cust_ids
        else {}
    )

    rows: list[PaymentReconciliationRowOut] = []
    discrepancies: list[DiscrepancyCandidate] = []

    for p in payments:
        cust = cust_map.get(p.customer_id)
        active_alloc = sum(int(a.allocated_paisa) for a in p.allocations if a.status == "ACTIVE")
        posted_refund = sum(int(r.amount_paisa) for r in p.refunds if r.status == "POSTED")

        issue_code: str | None = None
        issue_detail: str | None = None

        if p.status == "REVERSED" and active_alloc > 0:
            issue_code = "REVERSED_PMT_HAS_ACTIVE_ALLOC"
            issue_detail = f"Reversed payment {p.payment_number} still has {active_alloc} paise active allocations."
        elif p.status != "REVERSED" and (active_alloc != int(p.allocated_paisa) or posted_refund != int(p.refunded_paisa)):
            issue_code = "PMT_ALLOC_SUM_MISMATCH"
            issue_detail = (
                f"Payment {p.payment_number} persisted alloc/refund ({p.allocated_paisa}/{p.refunded_paisa}) "
                f"!= recomputed ({active_alloc}/{posted_refund})."
            )
        elif active_alloc + posted_refund > int(p.amount_paisa):
            issue_code = "PMT_OVER_ALLOCATED"
            issue_detail = f"Payment {p.payment_number} alloc+refund ({active_alloc + posted_refund}) exceeds amount ({p.amount_paisa})."

        if issue_code:
            discrepancies.append(
                DiscrepancyCandidate(
                    domain="PAYMENT",
                    discrepancy_code=issue_code,
                    severity="CRITICAL",
                    entity_schema="finance",
                    entity_table="payments",
                    entity_id=p.id,
                    entity_ref=p.payment_number,
                    expected_value={"allocated_paisa": active_alloc, "refunded_paisa": posted_refund},
                    actual_value={"allocated_paisa": int(p.allocated_paisa), "refunded_paisa": int(p.refunded_paisa)},
                    difference_summary=issue_detail or issue_code,
                )
            )

        rows.append(
            PaymentReconciliationRowOut(
                payment_id=p.id,
                payment_number=p.payment_number,
                payment_date=p.payment_date,
                customer_name=cust.name if cust else f"Customer#{p.customer_id}",
                amount_paisa=int(p.amount_paisa),
                persisted_allocated_paisa=int(p.allocated_paisa),
                computed_allocated_paisa=active_alloc,
                persisted_refunded_paisa=int(p.refunded_paisa),
                computed_refunded_paisa=posted_refund,
                unallocated_paisa=int(p.unallocated_paisa),
                status="DISCREPANCY" if issue_code else "MATCHED",
                issue_code=issue_code,
                issue_detail=issue_detail,
            )
        )

    # Also cross-check Invoice paid_paisa vs CustomerReceivable parity across period invoices
    invs = (
        db.execute(
            select(Invoice).where(
                Invoice.invoice_date >= period_start,
                Invoice.invoice_date <= period_end,
                Invoice.doc_status != "DRAFT",
            )
        )
        .scalars()
        .all()
    )
    inv_ids = [i.id for i in invs]
    ar_map = (
        {
            ar.invoice_id: ar
            for ar in db.execute(
                select(CustomerReceivable).where(CustomerReceivable.invoice_id.in_(inv_ids))
            )
            .scalars()
            .all()
        }
        if inv_ids
        else {}
    )
    for inv in invs:
        ar = ar_map.get(inv.id)
        if ar is None:
            discrepancies.append(
                DiscrepancyCandidate(
                    domain="PAYMENT",
                    discrepancy_code="MISSING_CUSTOMER_RECEIVABLE",
                    severity="HIGH",
                    entity_schema="finance",
                    entity_table="customer_receivables",
                    entity_id=inv.id,
                    entity_ref=inv.invoice_number or inv.draft_ref,
                    expected_value={"outstanding_paisa": int(inv.outstanding_paisa)},
                    actual_value={"receivable_row": None},
                    difference_summary=f"Issued invoice {inv.invoice_number} is missing its CustomerReceivable row.",
                )
            )
        elif (
            int(ar.original_paisa) != int(inv.grand_total_paisa)
            or int(ar.credited_paisa) != int(inv.credited_paisa)
            or int(ar.paid_paisa) != int(inv.paid_paisa)
            or int(ar.outstanding_paisa) != int(inv.outstanding_paisa)
        ):
            discrepancies.append(
                DiscrepancyCandidate(
                    domain="PAYMENT",
                    discrepancy_code="INV_AR_OUTSTANDING_MISMATCH",
                    severity="CRITICAL",
                    entity_schema="finance",
                    entity_table="customer_receivables",
                    entity_id=inv.id,
                    entity_ref=inv.invoice_number or inv.draft_ref,
                    expected_value={
                        "paid_paisa": int(inv.paid_paisa),
                        "credited_paisa": int(inv.credited_paisa),
                        "outstanding_paisa": int(inv.outstanding_paisa),
                    },
                    actual_value={
                        "ar_paid_paisa": int(ar.paid_paisa),
                        "ar_credited_paisa": int(ar.credited_paisa),
                        "ar_outstanding_paisa": int(ar.outstanding_paisa),
                    },
                    difference_summary=f"AR projection for {inv.invoice_number} ({ar.outstanding_paisa} p) out of sync with invoice ({inv.outstanding_paisa} p).",
                )
            )

    return rows, discrepancies


def evaluate_dispatch_reconciliation(
    db: Session, *, period_start: date, period_end: date
) -> tuple[list[DispatchReconciliationRowOut], list[DiscrepancyCandidate]]:
    """Compare Issued Invoices against Posted Dispatches and DISPATCH_OUT inventory ledger rows."""
    invs = (
        db.execute(
            select(Invoice)
            .options(selectinload(Invoice.items), selectinload(Invoice.dispatches).selectinload(Dispatch.items))
            .where(
                Invoice.invoice_date >= period_start,
                Invoice.invoice_date <= period_end,
                Invoice.doc_status == "ISSUED",
            )
            .order_by(Invoice.id.desc())
        )
        .scalars()
        .all()
    )
    all_di_ids = [
        di.id
        for inv in invs
        for d in inv.dispatches
        if d.status in {"DISPATCHED", "IN_TRANSIT", "DELIVERED", "DELIVERY_EXCEPTION"}
        for di in d.items
    ]
    dsp_movs = (
        db.execute(
            select(InventoryMovement).where(
                InventoryMovement.movement_type == "DISPATCH_OUT",
                InventoryMovement.dispatch_item_id.in_(all_di_ids),
            )
        )
        .scalars()
        .all()
        if all_di_ids
        else []
    )
    mov_by_di: dict[int, int] = defaultdict(int)
    seen_movs: set[int] = set()
    for m in dsp_movs:
        if m.id in seen_movs or m.dispatch_item_id is None:
            continue
        seen_movs.add(m.id)
        mov_by_di[m.dispatch_item_id] += int(abs(Decimal(m.signed_qty_base)))

    rows: list[DispatchReconciliationRowOut] = []
    discrepancies: list[DiscrepancyCandidate] = []

    for inv in invs:
        invoiced_qty = sum(it.qty_pkts for it in inv.items)
        posted_dispatches = [
            d
            for d in inv.dispatches
            if d.status in {"DISPATCHED", "IN_TRANSIT", "DELIVERED", "DELIVERY_EXCEPTION"}
        ]
        dsp_qty = sum(di.dispatched_qty_pkts for d in posted_dispatches for di in d.items)
        ledger_qty = sum(mov_by_di.get(di.id, 0) for d in posted_dispatches for di in d.items)
        pending_qty = max(0, invoiced_qty - dsp_qty)

        expected_dsp_status = (
            "PENDING" if dsp_qty == 0 else ("DISPATCHED" if dsp_qty >= invoiced_qty else "PARTIAL")
        )
        issue_code: str | None = None
        issue_detail: str | None = None

        if dsp_qty > invoiced_qty:
            issue_code = "DISPATCH_EXCEEDS_INVOICE"
            issue_detail = f"Invoice {inv.invoice_number} dispatched {dsp_qty} pkts > invoiced {invoiced_qty} pkts."
        elif dsp_qty != ledger_qty:
            issue_code = "DISPATCH_VS_LEDGER_MISMATCH"
            issue_detail = f"Invoice {inv.invoice_number} dispatch docs ({dsp_qty} pkts) != DISPATCH_OUT ledger ({ledger_qty} pkts)."
        elif inv.dispatch_status != expected_dsp_status:
            issue_code = "INV_DISPATCH_FLAG_MISMATCH"
            issue_detail = f"Invoice {inv.invoice_number} dispatch_status '{inv.dispatch_status}' != expected '{expected_dsp_status}'."

        if issue_code:
            discrepancies.append(
                DiscrepancyCandidate(
                    domain="DISPATCH",
                    discrepancy_code=issue_code,
                    severity="HIGH",
                    entity_schema="billing",
                    entity_table="invoices",
                    entity_id=inv.id,
                    entity_ref=inv.invoice_number or inv.draft_ref,
                    expected_value={"invoiced_qty_pkts": invoiced_qty, "expected_dispatch_status": expected_dsp_status, "ledger_dispatch_qty": ledger_qty},
                    actual_value={"dispatched_qty_pkts": dsp_qty, "dispatch_status": inv.dispatch_status},
                    difference_summary=issue_detail or issue_code,
                )
            )

        rows.append(
            DispatchReconciliationRowOut(
                invoice_id=inv.id,
                invoice_number=inv.invoice_number or inv.draft_ref,
                invoice_date=inv.invoice_date,
                dispatch_status=inv.dispatch_status,
                invoiced_qty_pkts=invoiced_qty,
                dispatched_qty_pkts=dsp_qty,
                ledger_dispatch_qty_pkts=ledger_qty,
                pending_qty_pkts=pending_qty,
                status="DISCREPANCY" if issue_code else "MATCHED",
                issue_code=issue_code,
                issue_detail=issue_detail,
            )
        )

    return rows, discrepancies


def evaluate_production_reconciliation(
    db: Session, *, period_start: date, period_end: date
) -> tuple[list[ProductionReconciliationRowOut], list[DiscrepancyCandidate]]:
    """Reconcile Production Runs, BOM variances, deduplicated InventoryMovements & Costing totals."""
    runs = (
        db.execute(
            select(ProductionRun)
            .options(
                selectinload(ProductionRun.material_issues),
                selectinload(ProductionRun.outputs),
                selectinload(ProductionRun.variances),
            )
            .where(
                ProductionRun.run_date >= period_start,
                ProductionRun.run_date <= period_end,
                ProductionRun.status.in_(["COMPLETED", "POSTED"]),
            )
            .order_by(ProductionRun.id.desc())
        )
        .scalars()
        .all()
    )
    ps_ids = {r.pack_size_id for r in runs}
    ps_map = (
        {p.id: p for p in db.execute(select(PackSize).where(PackSize.id.in_(ps_ids))).scalars().all()}
        if ps_ids
        else {}
    )
    run_ids = [r.id for r in runs]
    movs = (
        db.execute(
            select(InventoryMovement).where(InventoryMovement.production_run_id.in_(run_ids))
        )
        .scalars()
        .all()
        if run_ids
        else []
    )
    pcs_map = (
        {
            s.production_run_id: s
            for s in db.execute(
                select(ProductionCostSummary).where(
                    ProductionCostSummary.production_run_id.in_(run_ids),
                    ProductionCostSummary.is_current.is_(True),
                )
            )
            .scalars()
            .all()
        }
        if run_ids
        else {}
    )

    seen_mov_ids: set[int] = set()
    output_mov_by_run: dict[int, int] = defaultdict(int)
    net_mat_mov_by_run_mat: dict[tuple[int, int], Decimal] = defaultdict(Decimal)

    for m in movs:
        if m.id in seen_mov_ids or m.production_run_id is None:
            continue
        seen_mov_ids.add(m.id)
        if m.movement_type == "PROD_OUTPUT_IN":
            output_mov_by_run[m.production_run_id] += int(Decimal(m.signed_qty_base))
        elif m.material_id is not None and m.movement_type in {"PROD_ISSUE_OUT", "PROD_RETURN_IN", "PACKAGING_DAMAGE_OUT"}:
            # Outbound negative -> net positive consumed/damaged weight/count
            net_mat_mov_by_run_mat[(m.production_run_id, m.material_id)] += -Decimal(m.signed_qty_base)

    rows: list[ProductionReconciliationRowOut] = []
    discrepancies: list[DiscrepancyCandidate] = []

    for r in runs:
        ps = ps_map.get(r.pack_size_id)
        ledger_out = output_mov_by_run.get(r.id, 0)
        flagged_vars = sum(1 for v in r.variances if v.is_flagged)
        pcs = pcs_map.get(r.id)

        issue_code: str | None = None
        issue_detail: str | None = None

        # 1. Verify Output vs PROD_OUTPUT_IN when POSTED
        sum_outputs = sum(o.good_qty_pkts for o in r.outputs)
        if r.status == "POSTED" and (r.actual_good_output_pkts != ledger_out or sum_outputs != r.actual_good_output_pkts):
            issue_code = "PROD_OUTPUT_VS_LEDGER_MISMATCH"
            issue_detail = f"Run {r.run_number} good output ({r.actual_good_output_pkts}) != ledger PROD_OUTPUT_IN ({ledger_out})."

        # 2. Verify Material Issues vs deduplicated movement sum
        if not issue_code and r.status == "POSTED":
            mat_issue_totals: dict[int, Decimal] = defaultdict(Decimal)
            for mi in r.material_issues:
                mat_issue_totals[mi.material_id] += Decimal(mi.actual_consumed_qty_base)
            for mid, iss_qty in mat_issue_totals.items():
                mov_qty = net_mat_mov_by_run_mat.get((r.id, mid), Decimal(0))
                if abs(iss_qty - mov_qty) > QTY_TOLERANCE:
                    issue_code = "PROD_ISSUE_VS_MOVEMENT_MISMATCH"
                    issue_detail = f"Run {r.run_number} material#{mid} issue ({iss_qty}) != net ledger movements ({mov_qty})."
                    break

        # 3. Verify Cost summary matches sum of material cost + overheads
        expected_cost: int | None = None
        if pcs is not None:
            mat_sum_cost = sum(int(mi.cost_absorbed_paisa) for mi in r.material_issues)
            expected_cost = mat_sum_cost + int(pcs.direct_overhead_paisa) + int(pcs.allocated_overhead_paisa)
            if not issue_code and int(pcs.total_cost_paisa) != expected_cost:
                issue_code = "PROD_COST_SUMMARY_MISMATCH"
                issue_detail = f"Run {r.run_number} cost summary ({pcs.total_cost_paisa} p) != materials+overheads ({expected_cost} p)."

        if issue_code:
            discrepancies.append(
                DiscrepancyCandidate(
                    domain="PRODUCTION",
                    discrepancy_code=issue_code,
                    severity="HIGH",
                    entity_schema="production",
                    entity_table="production_runs",
                    entity_id=r.id,
                    entity_ref=r.run_number,
                    expected_value={"actual_good_output_pkts": r.actual_good_output_pkts, "expected_cost_paisa": expected_cost},
                    actual_value={"ledger_output_pkts": ledger_out, "persisted_cost_paisa": int(pcs.total_cost_paisa) if pcs else None},
                    difference_summary=issue_detail or issue_code,
                )
            )
        elif flagged_vars > 0:
            discrepancies.append(
                DiscrepancyCandidate(
                    domain="PRODUCTION",
                    discrepancy_code="BOM_CONSUMPTION_VARIANCE",
                    severity="LOW",
                    entity_schema="production",
                    entity_table="production_runs",
                    entity_id=r.id,
                    entity_ref=r.run_number,
                    expected_value={"expected_output_pkts": r.expected_output_pkts, "tolerance_exceeded": False},
                    actual_value={"actual_good_pkts": r.actual_good_output_pkts, "flagged_variances": flagged_vars},
                    difference_summary=f"Run {r.run_number} recorded {flagged_vars} tolerance-exceeding BOM consumption/yield variance(s) for supervisor review.",
                )
            )

        rows.append(
            ProductionReconciliationRowOut(
                production_run_id=r.id,
                run_number=r.run_number,
                run_date=r.run_date,
                sku_code=ps.sku_code if ps else f"SKU#{r.pack_size_id}",
                run_status=r.status,
                expected_output_pkts=r.expected_output_pkts,
                actual_good_pkts=r.actual_good_output_pkts,
                rejected_pkts=r.rejected_output_pkts,
                ledger_output_pkts=ledger_out,
                bom_variance_flags_count=flagged_vars,
                cost_summary_paisa=int(pcs.total_cost_paisa) if pcs else None,
                lot_consumption_cost_with_overheads_paisa=expected_cost,
                status="DISCREPANCY" if (issue_code or flagged_vars > 0) else "MATCHED",
                issue_code=issue_code or ("BOM_CONSUMPTION_VARIANCE" if flagged_vars > 0 else None),
                issue_detail=issue_detail,
            )
        )

    return rows, discrepancies
