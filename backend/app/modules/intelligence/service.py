"""Management Intelligence Service — cross-module real-time executive KPIs, trends & watchlist."""

import csv
import io
from collections import defaultdict
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError, DomainValidationError
from app.modules.audit.models import AuditLog, ReconciliationDiscrepancy, VarianceAlert
from app.modules.billing.gst_engine import get_indian_financial_year
from app.modules.billing.models import CreditNote, Dispatch, Invoice
from app.modules.costing.models import ProductionCostSummary
from app.modules.finance import service as finance_service
from app.modules.finance.models import Payment
from app.modules.iam.schemas import CurrentActor
from app.modules.intelligence.schemas import (
    IntelCustomerSalesRow,
    IntelDailyTrendRow,
    IntelFinanceSummaryOut,
    IntelInventorySummaryOut,
    IntelLowStockRow,
    IntelMovementSummaryRow,
    IntelOperationsSummaryOut,
    IntelOrderPipelineOut,
    IntelProductionSkuRow,
    IntelProductionSummaryOut,
    IntelProductSalesRow,
    IntelSalesSummaryOut,
    IntelWatchlistItemOut,
    ManagementIntelligenceDashboardOut,
)
from app.modules.inventory import service as inventory_service
from app.modules.inventory.models import InventoryMovement, StockAdjustment
from app.modules.orders.models import SalesOrder
from app.modules.production.models import ProductionRun, ProductionVariance
from app.modules.purchasing.models import PurchaseOrder, PurchaseReceipt
from app.modules.sales.models import PackSize

IST = ZoneInfo("Asia/Kolkata")
_INTEL_ROLES = {"FACTORY_ADMIN", "OWNER", "ACCOUNTANT_AUDITOR"}


def _require_intel_viewer(actor: CurrentActor) -> None:
    if actor.role_code not in _INTEL_ROLES:
        raise AuthorizationError(
            f"Role '{actor.role_code}' is not permitted to access Management Intelligence reports."
        )


def _default_dates(
    date_from: date | None, date_to: date | None, as_of_date: date | None
) -> tuple[date, date, date]:
    today = datetime.now(IST).date()
    eff_end = date_to or today
    eff_start = date_from or date(eff_end.year if eff_end.month >= 4 else eff_end.year - 1, 4, 1)
    if eff_end < eff_start:
        raise DomainValidationError("date_to cannot be earlier than date_from.")
    eff_as_of = as_of_date or eff_end
    return eff_start, eff_end, eff_as_of


def get_management_intelligence_dashboard(
    db: Session,
    actor: CurrentActor,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    as_of_date: date | None = None,
) -> ManagementIntelligenceDashboardOut:
    """Aggregate real-time sales, inventory, production, finance, and operations intelligence."""
    _require_intel_viewer(actor)
    start_d, end_d, ref_d = _default_dates(date_from, date_to, as_of_date)
    start_utc = datetime.combine(start_d, time.min, tzinfo=IST).astimezone(UTC)
    end_utc = datetime.combine(end_d, time.max, tzinfo=IST).astimezone(UTC)

    # ── 1. Sales & Profitability Reuse (exact single source of truth) ──────────
    prof = finance_service.get_profitability_report(db, actor, date_from=start_d, date_to=end_d)
    ar_summary = finance_service.get_customer_receivables_summary(
        db, actor, as_of_date=ref_d, page=1, page_size=500
    )
    ageing = finance_service.get_ageing_report(db, actor, as_of_date=ref_d, page=1, page_size=10)

    orders = list(
        db.execute(
            select(SalesOrder).where(
                SalesOrder.order_date >= start_d,
                SalesOrder.order_date <= end_d,
            )
        )
        .scalars()
        .all()
    )
    pipeline = IntelOrderPipelineOut(
        total_orders=len(orders),
        pending_verification=sum(
            1 for o in orders if o.status in {"SUBMITTED", "UNDER_REVIEW", "CORRECTION_REQUESTED"}
        ),
        approved=sum(1 for o in orders if o.status == "APPROVED"),
        invoiced=sum(1 for o in orders if o.status == "INVOICED"),
        dispatched_or_partial=sum(
            1 for o in orders if o.status in {"PARTIALLY_DISPATCHED", "DISPATCHED"}
        ),
        rejected_or_cancelled=sum(1 for o in orders if o.status in {"REJECTED", "CANCELLED"}),
        shortage_orders=sum(1 for o in orders if o.has_shortage and o.status in {"SUBMITTED", "UNDER_REVIEW", "CORRECTION_REQUESTED"}),
    )

    inv_cnt = int(
        db.execute(
            select(func.count(Invoice.id)).where(
                Invoice.invoice_date >= start_d,
                Invoice.invoice_date <= end_d,
                Invoice.doc_status.in_(["ISSUED", "CANCELLED_BY_CN"]),
            )
        ).scalar_one()
    )
    cn_cnt = int(
        db.execute(
            select(func.count(CreditNote.id)).where(
                CreditNote.issue_date >= start_d,
                CreditNote.issue_date <= end_d,
                CreditNote.status == "ISSUED",
            )
        ).scalar_one()
    )

    sales_summary = IntelSalesSummaryOut(
        gross_taxable_paisa=prof.gross_revenue_paisa,
        gst_collected_paisa=prof.gst_collected_paisa,
        credited_taxable_paisa=prof.credited_revenue_paisa,
        net_sales_excl_gst_paisa=prof.net_revenue_paisa,
        gross_invoiced_total_paisa=prof.gross_revenue_paisa + prof.gst_collected_paisa + prof.credited_revenue_paisa,
        invoice_count=inv_cnt,
        credit_note_count=cn_cnt,
        order_pipeline=pipeline,
        top_products=[
            IntelProductSalesRow(
                pack_size_id=p.pack_size_id,
                sku_code=p.sku_code,
                display_name=p.display_name,
                hsn_code=p.hsn_code,
                invoiced_qty_pkts=p.invoiced_qty_pkts,
                net_sold_qty_pkts=p.net_sold_qty_pkts,
                net_revenue_paisa=p.net_revenue_paisa,
                total_cogs_paisa=p.total_cogs_paisa,
                gross_profit_paisa=p.gross_profit_paisa,
                gross_margin_pct=p.gross_margin_pct,
            )
            for p in prof.by_product[:10]
        ],
        top_customers=[
            IntelCustomerSalesRow(
                customer_id=c.customer_id,
                customer_code=c.customer_code,
                customer_name=c.customer_name,
                customer_type=c.customer_type,
                invoice_count=c.invoice_count,
                net_revenue_paisa=c.net_revenue_paisa,
                gross_profit_paisa=c.gross_profit_paisa,
                gross_margin_pct=c.gross_margin_pct,
                cash_received_paisa=c.cash_received_paisa,
                outstanding_receivables_paisa=c.outstanding_receivables_paisa,
            )
            for c in prof.by_customer[:10]
        ],
        daily_trend=[
            IntelDailyTrendRow(
                period_date=d.period_date,
                invoice_count=d.invoice_count,
                net_revenue_paisa=d.net_revenue_paisa,
                total_cogs_paisa=d.total_cogs_paisa,
                gross_profit_paisa=d.gross_profit_paisa,
                cash_collected_paisa=d.cash_collected_on_date_paisa,
            )
            for d in prof.by_date[:30]
        ],
    )

    # ── 2. Inventory Intelligence ──────────────────────────────────────────────
    inv_dash = inventory_service.get_inventory_overview(db)
    low_items = [i for i in inv_dash.items if i.is_low_stock]
    mov_rows = db.execute(
        select(
            InventoryMovement.movement_type,
            func.count(InventoryMovement.id),
            func.coalesce(func.sum(func.abs(InventoryMovement.signed_qty_base)), 0),
            func.coalesce(func.sum(InventoryMovement.total_cost_paisa), 0),
        )
        .where(
            InventoryMovement.occurred_at >= start_utc,
            InventoryMovement.occurred_at <= end_utc,
        )
        .group_by(InventoryMovement.movement_type)
        .order_by(InventoryMovement.movement_type.asc())
    ).all()

    inventory_summary = IntelInventorySummaryOut(
        total_items=inv_dash.total_items,
        raw_material_count=inv_dash.raw_material_count,
        packaging_material_count=inv_dash.packaging_material_count,
        finished_good_count=inv_dash.finished_good_count,
        total_stock_valuation_paisa=inv_dash.total_stock_value_paisa,
        low_stock_count=inv_dash.low_stock_count,
        pending_adjustments_count=inv_dash.pending_adjustments_count,
        low_stock_alerts=[
            IntelLowStockRow(
                item_type=i.item_type,
                item_id=i.item_id,
                code=i.code,
                name=i.name,
                item_category=i.item_category,
                display_uom=i.display_uom,
                base_uom=i.base_uom,
                display_factor=i.display_factor,
                physical_qty_base=i.physical_qty_base,
                reserved_qty_base=i.reserved_qty_base,
                available_qty_base=i.available_qty_base,
                reorder_level_base=i.reorder_level_base,
                open_lot_value_paisa=i.open_lot_value_paisa,
            )
            for i in low_items
        ],
        period_movements=[
            IntelMovementSummaryRow(
                movement_type=row[0],
                movement_count=int(row[1]),
                total_abs_qty_base=Decimal(row[2]).quantize(Decimal("0.001")),
                total_cost_paisa=int(row[3]),
            )
            for row in mov_rows
        ],
    )

    # ── 3. Production Intelligence ─────────────────────────────────────────────
    runs = list(
        db.execute(
            select(ProductionRun).where(
                ProductionRun.run_date >= start_d,
                ProductionRun.run_date <= end_d,
            )
        )
        .scalars()
        .all()
    )
    run_ids = [r.id for r in runs]
    ps_ids = {r.pack_size_id for r in runs}
    ps_map = (
        {p.id: p for p in db.execute(select(PackSize).where(PackSize.id.in_(ps_ids))).scalars().all()}
        if ps_ids
        else {}
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
    flagged_var_cnt = (
        int(
            db.execute(
                select(func.count(ProductionVariance.id)).where(
                    ProductionVariance.production_run_id.in_(run_ids),
                    ProductionVariance.is_flagged.is_(True),
                )
            ).scalar_one()
        )
        if run_ids
        else 0
    )
    open_alert_cnt = int(
        db.execute(select(func.count(VarianceAlert.id)).where(VarianceAlert.status == "OPEN")).scalar_one()
    )

    posted_runs = [r for r in runs if r.status == "POSTED"]
    tot_exp_pkts = sum(r.expected_output_pkts for r in runs if r.status in {"COMPLETED", "POSTED"})
    tot_good_pkts = sum(r.actual_good_output_pkts for r in runs if r.status in {"COMPLETED", "POSTED"})
    tot_rej_pkts = sum(r.rejected_output_pkts for r in runs if r.status in {"COMPLETED", "POSTED"})
    yield_pct = (
        ((Decimal(tot_good_pkts) / Decimal(tot_exp_pkts)) * Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if tot_exp_pkts > 0
        else Decimal("0.00")
    )

    tot_batch_cost = sum(int(s.total_cost_paisa) for s in pcs_map.values())
    tot_costed_good = sum(int(s.good_packets) for s in pcs_map.values())
    tot_waste_dmg_cost = sum(
        int(s.raw_wastage_cost_paisa) + int(s.damaged_packaging_cost_paisa) + int(s.rejected_output_cost_impact_paisa)
        for s in pcs_map.values()
    )
    w_avg_unit = (
        int((Decimal(tot_batch_cost) / Decimal(tot_costed_good)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if tot_costed_good > 0
        else None
    )

    sku_agg: dict[int, dict[str, int]] = defaultdict(
        lambda: {"runs": 0, "exp": 0, "good": 0, "rej": 0, "cost": 0, "cost_pkts": 0}
    )
    for r in runs:
        if r.status == "CANCELLED":
            continue
        b = sku_agg[r.pack_size_id]
        b["runs"] += 1
        if r.status in {"COMPLETED", "POSTED"}:
            b["exp"] += r.expected_output_pkts
            b["good"] += r.actual_good_output_pkts
            b["rej"] += r.rejected_output_pkts
        s = pcs_map.get(r.id)
        if s is not None:
            b["cost"] += int(s.total_cost_paisa)
            b["cost_pkts"] += int(s.good_packets)

    by_sku: list[IntelProductionSkuRow] = []
    for pid, b in sorted(sku_agg.items(), key=lambda kv: -kv[1]["good"]):
        ps = ps_map[pid]
        y_pct = (
            ((Decimal(b["good"]) / Decimal(b["exp"])) * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if b["exp"] > 0
            else Decimal("0.00")
        )
        avg_u = (
            int((Decimal(b["cost"]) / Decimal(b["cost_pkts"])).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            if b["cost_pkts"] > 0
            else None
        )
        by_sku.append(
            IntelProductionSkuRow(
                pack_size_id=pid,
                sku_code=ps.sku_code,
                display_name=ps.display_name,
                runs_count=b["runs"],
                expected_output_pkts=b["exp"],
                actual_good_pkts=b["good"],
                rejected_pkts=b["rej"],
                yield_efficiency_pct=y_pct,
                total_cost_paisa=b["cost"],
                avg_cost_per_pkt_paisa=avg_u,
            )
        )

    production_summary = IntelProductionSummaryOut(
        total_runs=len(runs),
        posted_runs=len(posted_runs),
        in_progress_runs=sum(1 for r in runs if r.status == "IN_PROGRESS"),
        planned_runs=sum(1 for r in runs if r.status in {"DRAFT", "PLANNED"}),
        expected_output_pkts=tot_exp_pkts,
        actual_good_output_pkts=tot_good_pkts,
        rejected_output_pkts=tot_rej_pkts,
        yield_efficiency_pct=yield_pct,
        total_batch_cost_paisa=tot_batch_cost,
        weighted_avg_unit_cost_paisa=w_avg_unit,
        total_wastage_damage_cost_paisa=tot_waste_dmg_cost,
        flagged_variances_count=flagged_var_cnt,
        open_variance_alerts_count=open_alert_cnt,
        by_sku=by_sku,
    )

    # ── 4. Finance & Collections ───────────────────────────────────────────────
    pmt_totals = db.execute(
        select(
            func.coalesce(func.sum(Payment.amount_paisa), 0),
            func.coalesce(func.sum(Payment.refunded_paisa), 0),
        ).where(
            Payment.status != "REVERSED",
            Payment.payment_date >= start_d,
            Payment.payment_date <= end_d,
        )
    ).one()
    pmt_rec = int(pmt_totals[0])
    pmt_ref = int(pmt_totals[1])

    finance_summary = IntelFinanceSummaryOut(
        payments_received_paisa=pmt_rec,
        refunds_paisa=pmt_ref,
        net_cash_collected_paisa=pmt_rec - pmt_ref,
        customer_advances_paisa=ar_summary.summary_total_advance_paisa,
        total_outstanding_receivables_paisa=ageing.total_outstanding_paisa,
        overdue_receivables_paisa=ageing.overdue_total_paisa,
        not_due_receivables_paisa=ageing.not_due_paisa,
        bucket_0_30_paisa=ageing.bucket_0_30_paisa,
        bucket_31_60_paisa=ageing.bucket_31_60_paisa,
        bucket_61_90_paisa=ageing.bucket_61_90_paisa,
        bucket_90_plus_paisa=ageing.bucket_90_plus_paisa,
        total_cogs_paisa=prof.total_cogs_paisa,
        gross_profit_paisa=prof.gross_profit_paisa,
        gross_margin_pct=prof.gross_margin_pct,
        profitability_disclaimer=prof.disclaimer,
    )

    # ── 5. Operations & Governance Queues ──────────────────────────────────────
    pending_pos = int(
        db.execute(
            select(func.count(PurchaseOrder.id)).where(
                PurchaseOrder.status.in_(["DRAFT", "SUBMITTED", "APPROVED", "PARTIALLY_RECEIVED"])
            )
        ).scalar_one()
    )
    pending_grns = int(
        db.execute(
            select(func.count(PurchaseReceipt.id)).where(
                PurchaseReceipt.status.in_(["DRAFT", "SUBMITTED", "VERIFIED"])
            )
        ).scalar_one()
    )
    pending_adj = int(
        db.execute(
            select(func.count(StockAdjustment.id)).where(StockAdjustment.status == "PENDING_APPROVAL")
        ).scalar_one()
    )
    pending_dsp = int(
        db.execute(
            select(func.count(Dispatch.id)).where(Dispatch.status.in_(["CREATED", "READY_FOR_DISPATCH", "IN_TRANSIT"]))
        ).scalar_one()
    )
    exc_dsp = int(
        db.execute(
            select(func.count(Dispatch.id)).where(Dispatch.status == "DELIVERY_EXCEPTION")
        ).scalar_one()
    )
    open_discs = list(
        db.execute(
            select(ReconciliationDiscrepancy).where(
                ReconciliationDiscrepancy.status.in_(["OPEN", "UNDER_REVIEW", "ACTION_PROPOSED", "APPROVED"])
            )
        )
        .scalars()
        .all()
    )
    crit_high_discs = sum(1 for d in open_discs if d.severity in {"CRITICAL", "HIGH"})
    sec_events = int(
        db.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.action.in_(["LOGIN_FAILED", "ACCESS_DENIED"]),
                AuditLog.occurred_at >= start_utc,
                AuditLog.occurred_at <= end_utc,
            )
        ).scalar_one()
    )

    operations = IntelOperationsSummaryOut(
        pending_approval_orders=pipeline.pending_verification,
        shortage_orders=pipeline.shortage_orders,
        pending_purchase_orders=pending_pos,
        pending_goods_receipts=pending_grns,
        pending_stock_adjustments=pending_adj,
        pending_dispatches=pending_dsp,
        delivery_exceptions=exc_dsp,
        open_reconciliation_discrepancies=len(open_discs),
        critical_high_discrepancies=crit_high_discs,
        security_events_in_period=sec_events,
    )

    # ── 6. Actionable Executive Watchlist ──────────────────────────────────────
    watchlist: list[IntelWatchlistItemOut] = []
    if crit_high_discs > 0:
        watchlist.append(
            IntelWatchlistItemOut(
                severity="CRITICAL",
                category="RECONCILIATION",
                title=f"{crit_high_discs} Critical/High Reconciliation Discrepancies",
                detail="Cross-module mismatches require investigation, approval, and corrective posting.",
                link_path="/admin/reconciliation",
            )
        )
    if exc_dsp > 0:
        watchlist.append(
            IntelWatchlistItemOut(
                severity="HIGH",
                category="DISPATCH",
                title=f"{exc_dsp} Delivery Exception(s) Logged",
                detail="Dispatched consignment reported quantity discrepancy or delivery exception.",
                link_path="/admin/dispatch",
            )
        )
    if ageing.overdue_total_paisa > 0:
        watchlist.append(
            IntelWatchlistItemOut(
                severity="HIGH",
                category="RECEIVABLES",
                title=f"Overdue Receivables: ₹{ageing.overdue_total_paisa / 100:,.2f}",
                detail="Customer invoices past credit due_date pending payment allocation.",
                link_path="/admin/finance/receivables",
            )
        )
    if inv_dash.low_stock_count > 0:
        watchlist.append(
            IntelWatchlistItemOut(
                severity="MEDIUM",
                category="INVENTORY",
                title=f"{inv_dash.low_stock_count} Item(s) At or Below Reorder Level",
                detail=", ".join(i.code for i in low_items[:5]),
                link_path="/admin/inventory",
            )
        )
    if open_alert_cnt > 0:
        watchlist.append(
            IntelWatchlistItemOut(
                severity="MEDIUM",
                category="PRODUCTION",
                title=f"{open_alert_cnt} Open Production Variance Alert(s)",
                detail="Batch material consumption or yield deviated outside tolerance threshold.",
                link_path="/admin/production/variances",
            )
        )
    if pipeline.pending_verification > 0:
        watchlist.append(
            IntelWatchlistItemOut(
                severity="INFO",
                category="SALES",
                title=f"{pipeline.pending_verification} Order(s) Awaiting Admin Verification",
                detail=f"{pipeline.shortage_orders} with potential finished-goods stock shortage.",
                link_path="/admin/orders",
            )
        )
    if sec_events > 0:
        watchlist.append(
            IntelWatchlistItemOut(
                severity="INFO",
                category="SECURITY",
                title=f"{sec_events} Failed Login / Access Denied Event(s)",
                detail="Review centralized security and permission audit trail.",
                link_path="/admin/audit",
            )
        )

    return ManagementIntelligenceDashboardOut(
        period_start=start_d,
        period_end=end_d,
        as_of_date=ref_d,
        financial_year=get_indian_financial_year(end_d),
        sales=sales_summary,
        inventory=inventory_summary,
        production=production_summary,
        finance=finance_summary,
        operations=operations,
        watchlist=watchlist,
    )


def export_executive_intelligence_csv(
    db: Session,
    actor: CurrentActor,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    as_of_date: date | None = None,
) -> str:
    """Export executive intelligence KPIs, top products, top customers, and low stock to CSV."""
    dash = get_management_intelligence_dashboard(
        db, actor, date_from=date_from, date_to=date_to, as_of_date=as_of_date
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Kaveri Traditional Snacks Pvt. Ltd. — Management Intelligence Summary"])
    w.writerow(["Period", f"{dash.period_start} to {dash.period_end}", "FY", dash.financial_year, "As Of", str(dash.as_of_date)])
    w.writerow([])

    w.writerow(["Executive KPIs", "Amount / Value", "Notes"])
    w.writerow(["Net Sales (Excl. GST)", f"{dash.sales.net_sales_excl_gst_paisa / 100:.2f}", f"{dash.sales.invoice_count} invoices, {dash.sales.credit_note_count} CNs"])
    w.writerow(["GST Liability Collected", f"{dash.sales.gst_collected_paisa / 100:.2f}", "Statutory tax payable"])
    w.writerow(["COGS (Production + Dispatched)", f"{dash.finance.total_cogs_paisa / 100:.2f}", "Includes estimated pending dispatch COGS"])
    w.writerow(["Gross Profit", f"{dash.finance.gross_profit_paisa / 100:.2f}", f"Gross Margin {dash.finance.gross_margin_pct}% (Excl. non-production SG&A)"])
    w.writerow(["Net Cash Collected", f"{dash.finance.net_cash_collected_paisa / 100:.2f}", f"Advances: {dash.finance.customer_advances_paisa / 100:.2f}"])
    w.writerow(["Total Outstanding Receivables", f"{dash.finance.total_outstanding_receivables_paisa / 100:.2f}", f"Overdue: {dash.finance.overdue_receivables_paisa / 100:.2f}"])
    w.writerow(["Inventory Valuation (FIFO Open Lots)", f"{dash.inventory.total_stock_valuation_paisa / 100:.2f}", f"{dash.inventory.low_stock_count} low-stock alerts"])
    w.writerow(["Production Yield Efficiency", f"{dash.production.yield_efficiency_pct}%", f"{dash.production.actual_good_output_pkts} good / {dash.production.rejected_output_pkts} rejected pkts"])
    w.writerow([])

    w.writerow(["Product Performance", "SKU", "Net Sold Pkts", "Net Revenue (INR)", "COGS (INR)", "Gross Profit (INR)", "Margin %"])
    for p in dash.sales.top_products:
        w.writerow([
            p.display_name,
            p.sku_code,
            p.net_sold_qty_pkts,
            f"{p.net_revenue_paisa / 100:.2f}",
            f"{p.total_cogs_paisa / 100:.2f}",
            f"{p.gross_profit_paisa / 100:.2f}",
            str(p.gross_margin_pct),
        ])
    w.writerow([])

    w.writerow(["Customer Performance", "Code", "Invoices", "Net Revenue (INR)", "Cash Collected (INR)", "Outstanding AR (INR)", "Gross Profit (INR)"])
    for c in dash.sales.top_customers:
        w.writerow([
            c.customer_name,
            c.customer_code,
            c.invoice_count,
            f"{c.net_revenue_paisa / 100:.2f}",
            f"{c.cash_received_paisa / 100:.2f}",
            f"{c.outstanding_receivables_paisa / 100:.2f}",
            f"{c.gross_profit_paisa / 100:.2f}",
        ])
    w.writerow([])

    w.writerow(["Low Stock Alerts", "Code", "Category", "Available (Display)", "Reorder Level (Base)", "Lot Value (INR)"])
    for i in dash.inventory.low_stock_alerts:
        avail_disp = (i.available_qty_base / i.display_factor).quantize(Decimal("0.001"))
        w.writerow([i.name, i.code, i.item_category, f"{avail_disp} {i.display_uom}", f"{i.reorder_level_base} {i.base_uom}", f"{i.open_lot_value_paisa / 100:.2f}"])

    return buf.getvalue()
