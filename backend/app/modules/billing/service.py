"""Billing, GST Invoicing, Credit Note, Dispatch, Delivery & Reporting service layer."""

from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.modules.audit.service import record_audit_log
from app.modules.billing import repository as billing_repo
from app.modules.billing.gst_engine import (
    TaxLineInput,
    get_indian_financial_year,
    round_half_up_bps,
    validate_tax_conditions_and_calculate_gst,
)
from app.modules.billing.models import (
    CreditNote,
    CreditNoteItem,
    Dispatch,
    DispatchItem,
    DispatchStatusHistory,
    Invoice,
    InvoiceItem,
    InvoiceTaxComponent,
)
from app.modules.billing.pdf_generator import render_invoice_pdf
from app.modules.billing.schemas import (
    BillingDashboardOut,
    BillingReportsBundleOut,
    CreateCreditNoteRequest,
    CreateDispatchRequest,
    CreateInvoiceRequest,
    CreditNoteItemOut,
    CreditNoteOut,
    CustomerSalesSummaryRow,
    DispatchActionRemarksRequest,
    DispatchDashboardOut,
    DispatchItemOut,
    DispatchOut,
    DispatchRegisterRow,
    DispatchStatusHistoryOut,
    GstHsnReportRow,
    GstSummaryReportOut,
    InvoiceAuditOut,
    InvoiceDetailOut,
    InvoiceItemOut,
    InvoiceSummaryOut,
    InvoiceTaxComponentOut,
    IssueInvoiceRequest,
    ProductSalesSummaryRow,
    ReadyForBillingOrderOut,
    ReadyForDispatchInvoiceOut,
    SalesInvoiceRegisterRow,
    UpdateDeliveryStatusRequest,
    VerifyInvoiceRequest,
)
from app.modules.iam import repository as iam_repo
from app.modules.iam.models import CompanyProfile, User
from app.modules.iam.schemas import CurrentActor
from app.modules.inventory import repository as inventory_repo
from app.modules.inventory.models import CostLot, CostLotConsumption, InventoryMovement
from app.modules.orders import repository as orders_repo
from app.modules.orders.models import SalesOrder, SalesOrderStatusHistory
from app.modules.orders.state_machine import OrderStatus
from app.modules.sales import repository as sales_repo
from app.modules.sales.models import Customer, CustomerAddress, PackSize

IST = ZoneInfo("Asia/Kolkata")
_DEFAULT_LEGAL_DECLARATION = (
    "We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct. "
    "Issued invoices cannot be edited or deleted; corrections require an authorised Credit Note."
)
_DELIVERY_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "DISPATCHED": {"IN_TRANSIT", "DELIVERED", "DELIVERY_EXCEPTION"},
    "IN_TRANSIT": {"DELIVERED", "DELIVERY_EXCEPTION"},
    "DELIVERY_EXCEPTION": {"IN_TRANSIT", "DELIVERED"},
}


# ── Helpers ─────────────────────────────────────────────────────────────────


def _require_operator(actor: CurrentActor, action: str) -> None:
    if actor.role_code != "FACTORY_ADMIN":
        raise AuthorizationError(f"Only Factory Admin is permitted to {action}.")


def _require_viewer(actor: CurrentActor, action: str) -> None:
    if actor.role_code not in {"FACTORY_ADMIN", "ACCOUNTANT_AUDITOR", "OWNER"}:
        raise AuthorizationError(f"Role '{actor.role_code}' is not permitted to {action}.")


def _get_company(db: Session) -> CompanyProfile:
    company = iam_repo.get_company_profile(db)
    if company is None:
        raise DomainValidationError("Company GST profile is not configured.")
    return company


def _users_map(db: Session, ids: set[int]) -> dict[int, User]:
    clean = {uid for uid in ids if uid}
    if not clean:
        return {}
    rows = db.execute(select(User).where(User.id.in_(clean))).scalars().all()
    return {u.id: u for u in rows}


def _orders_map(db: Session, order_ids: set[int]) -> dict[int, SalesOrder]:
    if not order_ids:
        return {}
    rows = db.execute(select(SalesOrder).where(SalesOrder.id.in_(order_ids))).scalars().all()
    return {o.id: o for o in rows}


def _customers_map(db: Session, cust_ids: set[int]) -> dict[int, Customer]:
    if not cust_ids:
        return {}
    rows = db.execute(select(Customer).where(Customer.id.in_(cust_ids))).scalars().all()
    return {c.id: c for c in rows}


def _format_address(addr: CustomerAddress | None, fallback_state: str, fallback_code: str) -> str:
    if addr is None:
        return f"{fallback_state} (State Code: {fallback_code})"
    parts = [addr.line1]
    if addr.line2:
        parts.append(addr.line2)
    parts.append(f"{addr.city}, {addr.state_name} ({addr.state_code}) - {addr.pincode}")
    return ", ".join(parts)


def _resolve_customer_addresses(customer: Customer, shipping_id: int | None) -> tuple[str, str, str, str]:
    billing = next((a for a in customer.addresses if a.address_type == "BILLING" and a.is_default), None)
    if billing is None:
        billing = next((a for a in customer.addresses if a.address_type == "BILLING"), None)
    shipping = None
    if shipping_id is not None:
        shipping = next((a for a in customer.addresses if a.id == shipping_id), None)
    if shipping is None:
        shipping = next((a for a in customer.addresses if a.address_type == "SHIPPING" and a.is_default), None)
    if shipping is None:
        shipping = next((a for a in customer.addresses if a.address_type == "SHIPPING"), None)

    bill_str = _format_address(billing, customer.primary_state_name, customer.primary_state_code)
    ship_str = _format_address(shipping, customer.primary_state_name, customer.primary_state_code)
    pos_code = shipping.state_code if shipping else customer.primary_state_code
    pos_name = shipping.state_name if shipping else customer.primary_state_name
    return bill_str, ship_str, pos_code, pos_name


# ── Hydration ───────────────────────────────────────────────────────────────


def _hydrate_credit_note(
    cn: CreditNote,
    *,
    invoice_map: dict[int, Invoice],
    cust_map: dict[int, Customer],
    users: dict[int, User],
    ps_map: dict[int, PackSize],
    inv_items_map: dict[int, InvoiceItem],
) -> CreditNoteOut:
    orig_inv = invoice_map[cn.original_invoice_id]
    cust = cust_map[cn.customer_id]
    return CreditNoteOut(
        id=cn.id,
        draft_ref=cn.draft_ref,
        cn_number=cn.cn_number,
        financial_year=cn.financial_year,
        original_invoice_id=cn.original_invoice_id,
        original_invoice_number=orig_inv.invoice_number or orig_inv.draft_ref,
        customer_id=cn.customer_id,
        customer_name=cust.name,
        supply_type=cn.supply_type,
        note_type=cn.note_type,
        issue_date=cn.issue_date,
        reason=cn.reason,
        status=cn.status,
        cancel_original_invoice=cn.cancel_original_invoice,
        taxable_reversed_paisa=int(cn.taxable_reversed_paisa),
        cgst_reversed_paisa=int(cn.cgst_reversed_paisa),
        sgst_reversed_paisa=int(cn.sgst_reversed_paisa),
        igst_reversed_paisa=int(cn.igst_reversed_paisa),
        round_off_reversed_paisa=int(cn.round_off_reversed_paisa),
        total_reversed_paisa=int(cn.total_reversed_paisa),
        created_by_name=users[cn.created_by].full_name,
        approved_by_name=users[cn.approved_by].full_name if cn.approved_by else None,
        issued_by_name=users[cn.issued_by].full_name if cn.issued_by else None,
        issued_at=cn.issued_at,
        created_at=cn.created_at,
        items=[
            CreditNoteItemOut(
                id=it.id,
                invoice_item_id=it.invoice_item_id,
                pack_size_id=it.pack_size_id,
                sku_code=ps_map[it.pack_size_id].sku_code,
                description=inv_items_map[it.invoice_item_id].description
                if it.invoice_item_id in inv_items_map
                else ps_map[it.pack_size_id].display_name,
                qty_pkts=it.qty_pkts,
                return_disposition=it.return_disposition,
                taxable_reversed_paisa=int(it.taxable_reversed_paisa),
                cgst_reversed_paisa=int(it.cgst_reversed_paisa),
                sgst_reversed_paisa=int(it.sgst_reversed_paisa),
                igst_reversed_paisa=int(it.igst_reversed_paisa),
                line_total_reversed_paisa=int(it.line_total_reversed_paisa),
            )
            for it in cn.items
        ],
    )


def _hydrate_dispatch(
    dsp: Dispatch,
    *,
    inv_map: dict[int, Invoice],
    ord_map: dict[int, SalesOrder],
    cust_map: dict[int, Customer],
    users: dict[int, User],
    ps_map: dict[int, PackSize],
) -> DispatchOut:
    inv = inv_map[dsp.invoice_id]
    order = ord_map[dsp.sales_order_id]
    cust = cust_map[dsp.customer_id]
    return DispatchOut(
        id=dsp.id,
        dispatch_number=dsp.dispatch_number,
        invoice_id=dsp.invoice_id,
        invoice_number=inv.invoice_number or inv.draft_ref,
        sales_order_id=dsp.sales_order_id,
        order_number=order.order_number,
        customer_id=dsp.customer_id,
        customer_name=cust.name,
        status=dsp.status,
        dispatch_date=dsp.dispatch_date,
        transporter_name=dsp.transporter_name,
        vehicle_number=dsp.vehicle_number,
        lr_number=dsp.lr_number,
        packing_verified=dsp.packing_verified,
        packing_remarks=dsp.packing_remarks,
        notes=dsp.notes,
        created_by_name=users[dsp.created_by].full_name,
        created_at=dsp.created_at,
        ready_by_name=users[dsp.ready_by].full_name if dsp.ready_by else None,
        ready_at=dsp.ready_at,
        dispatched_by_name=users[dsp.dispatched_by].full_name if dsp.dispatched_by else None,
        dispatched_at=dsp.dispatched_at,
        in_transit_at=dsp.in_transit_at,
        delivery_date=dsp.delivery_date,
        delivery_confirmed_by_name=(
            users[dsp.delivery_confirmed_by].full_name if dsp.delivery_confirmed_by else None
        ),
        delivery_confirmed_at=dsp.delivery_confirmed_at,
        delivery_remarks=dsp.delivery_remarks,
        delivery_exception_reason=dsp.delivery_exception_reason,
        version=dsp.version,
        total_dispatched_pkts=sum(i.dispatched_qty_pkts for i in dsp.items),
        total_received_pkts=sum(i.received_qty_pkts or 0 for i in dsp.items),
        items=[
            DispatchItemOut(
                id=i.id,
                invoice_item_id=i.invoice_item_id,
                pack_size_id=i.pack_size_id,
                sku_code=ps_map[i.pack_size_id].sku_code,
                display_name=ps_map[i.pack_size_id].display_name,
                dispatched_qty_pkts=i.dispatched_qty_pkts,
                batch_code_ref=i.batch_code_ref,
                received_qty_pkts=i.received_qty_pkts,
                discrepancy_qty_pkts=i.discrepancy_qty_pkts,
                discrepancy_remarks=i.discrepancy_remarks,
            )
            for i in dsp.items
        ],
        status_history=[
            DispatchStatusHistoryOut(
                id=h.id,
                from_status=h.from_status,
                to_status=h.to_status,
                changed_by_name=users[h.changed_by].full_name,
                reason=h.reason,
                changed_at=h.changed_at,
            )
            for h in dsp.status_history
        ],
    )


def _hydrate_invoice_summary(
    inv: Invoice,
    *,
    ord_map: dict[int, SalesOrder],
    dispatched_by_item: dict[int, int],
) -> InvoiceSummaryOut:
    total_qty = sum(i.qty_pkts for i in inv.items)
    dispatched_qty = sum(dispatched_by_item.get(i.id, 0) for i in inv.items)
    return InvoiceSummaryOut(
        id=inv.id,
        draft_ref=inv.draft_ref,
        invoice_number=inv.invoice_number,
        financial_year=inv.financial_year,
        sales_order_id=inv.sales_order_id,
        order_number=ord_map[inv.sales_order_id].order_number,
        customer_id=inv.customer_id,
        customer_name=inv.customer_name,
        buyer_gstin=inv.buyer_gstin,
        place_of_supply_state_code=inv.place_of_supply_state_code,
        place_of_supply_state_name=inv.place_of_supply_state_name,
        nature_of_supply=inv.nature_of_supply,
        supply_type=inv.supply_type,
        invoice_date=inv.invoice_date,
        due_date=inv.due_date,
        doc_status=inv.doc_status,
        payment_status=inv.payment_status,
        dispatch_status=inv.dispatch_status,
        taxable_total_paisa=int(inv.taxable_total_paisa),
        cgst_total_paisa=int(inv.cgst_total_paisa),
        sgst_total_paisa=int(inv.sgst_total_paisa),
        igst_total_paisa=int(inv.igst_total_paisa),
        round_off_paisa=int(inv.round_off_paisa),
        grand_total_paisa=int(inv.grand_total_paisa),
        credited_paisa=int(inv.credited_paisa),
        paid_paisa=int(inv.paid_paisa),
        outstanding_paisa=int(inv.outstanding_paisa),
        total_qty_pkts=total_qty,
        dispatched_qty_pkts=dispatched_qty,
        remaining_dispatch_qty_pkts=max(0, total_qty - dispatched_qty),
        issued_at=inv.issued_at,
        created_at=inv.created_at,
    )


def _hydrate_invoice_detail(db: Session, inv: Invoice, *, include_audit: bool = True) -> InvoiceDetailOut:
    item_ids = [i.id for i in inv.items]
    dispatched_by_item = billing_repo.sum_dispatched_qty_by_invoice_item_ids(db, item_ids)
    order = orders_repo.get_order_by_id(db, inv.sales_order_id)
    assert order is not None

    cust_ids = {inv.customer_id}
    ps_ids = {i.pack_size_id for i in inv.items}
    user_ids: set[int] = {inv.created_by}
    if inv.verified_by:
        user_ids.add(inv.verified_by)
    if inv.issued_by:
        user_ids.add(inv.issued_by)
    for cn in inv.credit_notes:
        user_ids.add(cn.created_by)
        if cn.approved_by:
            user_ids.add(cn.approved_by)
        if cn.issued_by:
            user_ids.add(cn.issued_by)
        for ci in cn.items:
            ps_ids.add(ci.pack_size_id)
    for dsp in inv.dispatches:
        user_ids.add(dsp.created_by)
        for uid in (dsp.ready_by, dsp.dispatched_by, dsp.delivery_confirmed_by):
            if uid:
                user_ids.add(uid)
        for h in dsp.status_history:
            user_ids.add(h.changed_by)
        for di in dsp.items:
            ps_ids.add(di.pack_size_id)

    audit_logs = billing_repo.list_invoice_audit_logs(db, inv.id) if include_audit else []
    for lg in audit_logs:
        if lg.actor_user_id:
            user_ids.add(lg.actor_user_id)

    users = _users_map(db, user_ids)
    cust_map = _customers_map(db, cust_ids)
    ps_map = sales_repo.get_pack_sizes_by_ids(db, list(ps_ids), include_inactive=True)
    ord_map = {order.id: order}
    inv_map = {inv.id: inv}
    inv_items_map = {it.id: it for it in inv.items}

    summary = _hydrate_invoice_summary(inv, ord_map=ord_map, dispatched_by_item=dispatched_by_item)
    return InvoiceDetailOut(
        **summary.model_dump(),
        seller_legal_name=inv.seller_legal_name,
        seller_gstin=inv.seller_gstin,
        seller_state_name=inv.seller_state_name,
        seller_state_code=inv.seller_state_code,
        seller_address=inv.seller_address,
        customer_type=inv.customer_type,
        billing_address_snapshot=inv.billing_address_snapshot,
        shipping_address_snapshot=inv.shipping_address_snapshot,
        payment_terms=inv.payment_terms,
        discount_total_paisa=int(inv.discount_total_paisa),
        amount_in_words=inv.amount_in_words,
        notes=inv.notes,
        legal_declaration=inv.legal_declaration,
        tax_calculation_snapshot=inv.tax_calculation_snapshot,
        created_by_name=users[inv.created_by].full_name,
        verified_by_name=users[inv.verified_by].full_name if inv.verified_by else None,
        verified_at=inv.verified_at,
        verification_remarks=inv.verification_remarks,
        issued_by_name=users[inv.issued_by].full_name if inv.issued_by else None,
        version=inv.version,
        items=[
            InvoiceItemOut(
                id=i.id,
                sales_order_item_id=i.sales_order_item_id,
                pack_size_id=i.pack_size_id,
                sku_code=i.sku_code,
                product_name=i.product_name,
                description=i.description,
                hsn_code=i.hsn_code,
                qty_pkts=i.qty_pkts,
                uom=i.uom,
                unit_price_paisa=int(i.unit_price_paisa),
                discount_paisa=int(i.discount_paisa),
                taxable_paisa=int(i.taxable_paisa),
                gst_rate_bps=i.gst_rate_bps,
                cgst_rate_bps=i.cgst_rate_bps,
                sgst_rate_bps=i.sgst_rate_bps,
                igst_rate_bps=i.igst_rate_bps,
                cgst_paisa=int(i.cgst_paisa),
                sgst_paisa=int(i.sgst_paisa),
                igst_paisa=int(i.igst_paisa),
                line_total_paisa=int(i.line_total_paisa),
                dispatched_qty_pkts=dispatched_by_item.get(i.id, 0),
                remaining_dispatch_qty_pkts=max(0, i.qty_pkts - dispatched_by_item.get(i.id, 0)),
            )
            for i in inv.items
        ],
        tax_components=[
            InvoiceTaxComponentOut(
                id=c.id,
                hsn_code=c.hsn_code,
                tax_type=c.tax_type,
                rate_bps=c.rate_bps,
                taxable_base_paisa=int(c.taxable_base_paisa),
                tax_amount_paisa=int(c.tax_amount_paisa),
            )
            for c in inv.tax_components
        ],
        credit_notes=[
            _hydrate_credit_note(
                cn,
                invoice_map=inv_map,
                cust_map=cust_map,
                users=users,
                ps_map=ps_map,
                inv_items_map=inv_items_map,
            )
            for cn in inv.credit_notes
        ],
        dispatches=[
            _hydrate_dispatch(
                dsp,
                inv_map=inv_map,
                ord_map=ord_map,
                cust_map=cust_map,
                users=users,
                ps_map=ps_map,
            )
            for dsp in inv.dispatches
        ],
        audit_trail=[
            InvoiceAuditOut(
                id=lg.id,
                actor_name=users[lg.actor_user_id].full_name if lg.actor_user_id else "System",
                actor_role=lg.actor_role,
                action=lg.action,
                entity_table=lg.entity_table,
                reason=lg.reason,
                after_state=lg.after_state,
                occurred_at=lg.occurred_at,
            )
            for lg in audit_logs
        ],
    )


# ── Invoice Generation, Verification & Issuance ─────────────────────────────


def get_billing_dashboard(
    db: Session,
    actor: CurrentActor,
    *,
    doc_status: str | None = None,
    dispatch_status: str | None = None,
    search: str | None = None,
) -> BillingDashboardOut:
    _require_viewer(actor, "view billing dashboard")
    company = _get_company(db)
    ready_orders_raw = billing_repo.list_ready_for_billing_orders(db)
    cust_ids = {o.customer_id for o in ready_orders_raw}
    ps_ids = {it.pack_size_id for o in ready_orders_raw for it in o.items}
    cust_map = _customers_map(db, cust_ids)
    ps_map = sales_repo.get_pack_sizes_by_ids(db, list(ps_ids), include_inactive=True)

    ready_orders: list[ReadyForBillingOrderOut] = []
    for o in ready_orders_raw:
        cust = cust_map[o.customer_id]
        _, _, pos_code, pos_name = _resolve_customer_addresses(cust, o.shipping_address_id)
        tax_lines = [
            TaxLineInput(
                sales_order_item_id=it.id,
                pack_size_id=it.pack_size_id,
                sku_code=ps_map[it.pack_size_id].sku_code,
                product_name=ps_map[it.pack_size_id].product.name,
                description=ps_map[it.pack_size_id].display_name,
                hsn_code=ps_map[it.pack_size_id].product.hsn_code,
                qty_pkts=it.approved_qty_pkts if it.approved_qty_pkts is not None else it.ordered_qty_pkts,
                unit_price_paisa=int(it.unit_price_paisa),
                gst_rate_bps=ps_map[it.pack_size_id].product.gst_rate_bps,
            )
            for it in o.items
            if (it.approved_qty_pkts if it.approved_qty_pkts is not None else it.ordered_qty_pkts) > 0
        ]
        calc = validate_tax_conditions_and_calculate_gst(
            seller_gstin=company.gstin,
            seller_state_code=company.state_code,
            seller_state_name=company.state_name,
            buyer_gstin=cust.gstin,
            customer_state_code=cust.primary_state_code,
            place_of_supply_state_code=pos_code,
            place_of_supply_state_name=pos_name,
            lines=tax_lines,
        )
        ready_orders.append(
            ReadyForBillingOrderOut(
                sales_order_id=o.id,
                order_number=o.order_number,
                order_date=o.order_date,
                customer_id=cust.id,
                customer_name=cust.name,
                customer_gstin=cust.gstin,
                place_of_supply_state_code=calc.place_of_supply_state_code,
                place_of_supply_state_name=calc.place_of_supply_state_name,
                supply_type=calc.supply_type,
                total_packets=sum(it.qty_pkts for it in tax_lines),
                taxable_total_paisa=calc.taxable_total_paisa,
                estimated_tax_paisa=calc.cgst_total_paisa + calc.sgst_total_paisa + calc.igst_total_paisa,
                estimated_grand_total_paisa=calc.grand_total_paisa,
                approved_at=o.approved_at,
            )
        )

    all_invoices = billing_repo.list_invoices(db, limit=500)
    filtered = billing_repo.list_invoices(
        db, doc_status=doc_status, dispatch_status=dispatch_status, search=search, limit=200
    )
    ord_map = _orders_map(db, {inv.sales_order_id for inv in filtered})
    item_ids = [it.id for inv in filtered for it in inv.items]
    dispatched_by_item = billing_repo.sum_dispatched_qty_by_invoice_item_ids(db, item_ids)

    draft_cnt = sum(1 for i in all_invoices if i.doc_status == "DRAFT")
    issued_list = [i for i in all_invoices if i.doc_status == "ISSUED"]
    cancelled_cnt = sum(1 for i in all_invoices if i.doc_status == "CANCELLED_BY_CN")

    return BillingDashboardOut(
        ready_for_billing_count=len(ready_orders),
        draft_invoices_count=draft_cnt,
        issued_invoices_count=len(issued_list),
        cancelled_invoices_count=cancelled_cnt,
        total_taxable_paisa=sum(int(i.taxable_total_paisa) for i in issued_list),
        total_cgst_paisa=sum(int(i.cgst_total_paisa) for i in issued_list),
        total_sgst_paisa=sum(int(i.sgst_total_paisa) for i in issued_list),
        total_igst_paisa=sum(int(i.igst_total_paisa) for i in issued_list),
        total_invoiced_paisa=sum(int(i.grand_total_paisa) for i in issued_list),
        total_credited_paisa=sum(int(i.credited_paisa) for i in all_invoices),
        total_outstanding_paisa=sum(int(i.outstanding_paisa) for i in issued_list),
        ready_orders=ready_orders,
        invoices=[
            _hydrate_invoice_summary(i, ord_map=ord_map, dispatched_by_item=dispatched_by_item)
            for i in filtered
        ],
    )


def _perform_issue_invoice(
    db: Session,
    *,
    inv: Invoice,
    order: SalesOrder,
    actor: CurrentActor,
    verification_remarks: str | None = None,
) -> None:
    if inv.doc_status != "DRAFT":
        raise ConflictError(
            f"Invoice {inv.invoice_number or inv.draft_ref} is in '{inv.doc_status}' status and cannot be re-issued.",
            error_code="DUPLICATE_INVOICE_ISSUE",
        )
    if order.status != OrderStatus.APPROVED:
        raise ConflictError(
            f"Sales order {order.order_number} is in status '{order.status}', expected 'APPROVED'.",
            error_code="INVALID_STATE_TRANSITION",
        )

    now_utc = datetime.now(UTC)
    inv_no = billing_repo.allocate_fiscal_sequence(
        db, doc_type="INVOICE", financial_year=inv.financial_year, prefix="INV"
    )
    inv.invoice_number = inv_no
    inv.doc_status = "ISSUED"
    if inv.verified_by is None:
        inv.verified_by = actor.user_id
        inv.verified_at = now_utc
    if verification_remarks and verification_remarks.strip():
        inv.verification_remarks = verification_remarks.strip()
    inv.issued_by = actor.user_id
    inv.issued_at = now_utc
    inv.version += 1

    prev_order_status = order.status
    order.status = OrderStatus.INVOICED
    order.version += 1
    db.add(
        SalesOrderStatusHistory(
            sales_order_id=order.id,
            from_status=prev_order_status,
            to_status=OrderStatus.INVOICED,
            changed_by=actor.user_id,
            reason=f"GST Invoice {inv_no} issued",
        )
    )
    db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="INVOICE_ISSUED",
        entity_schema="billing",
        entity_table="invoices",
        entity_id=inv.id,
        before_state={"doc_status": "DRAFT", "invoice_number": None},
        after_state={
            "invoice_id": inv.id,
            "invoice_number": inv_no,
            "financial_year": inv.financial_year,
            "sales_order_id": order.id,
            "doc_status": "ISSUED",
            "supply_type": inv.supply_type,
            "taxable_total_paisa": int(inv.taxable_total_paisa),
            "cgst_total_paisa": int(inv.cgst_total_paisa),
            "sgst_total_paisa": int(inv.sgst_total_paisa),
            "igst_total_paisa": int(inv.igst_total_paisa),
            "grand_total_paisa": int(inv.grand_total_paisa),
        },
        reason=inv.verification_remarks or f"Issued statutory GST invoice {inv_no} from {order.order_number}",
    )


def create_invoice_from_order(
    db: Session, actor: CurrentActor, payload: CreateInvoiceRequest
) -> InvoiceDetailOut:
    """Create a GST Invoice (DRAFT or immediately ISSUED) from an APPROVED SalesOrder without deducting stock."""
    _require_operator(actor, "generate GST invoices")
    try:
        order = orders_repo.get_order_by_id_for_update(db, payload.sales_order_id)
        if order is None:
            raise NotFoundError(f"Sales order {payload.sales_order_id} was not found.")
        if order.status != OrderStatus.APPROVED:
            raise ConflictError(
                f"Cannot generate invoice for order {order.order_number} in status '{order.status}'; order must be APPROVED.",
                error_code="INVALID_STATE_TRANSITION",
            )

        existing = billing_repo.get_active_invoice_for_order(db, order.id)
        if existing is not None:
            raise ConflictError(
                f"Order {order.order_number} already has an active invoice ({existing.invoice_number or existing.draft_ref}).",
                error_code="DUPLICATE_INVOICE",
            )

        company = _get_company(db)
        customer = sales_repo.get_customer_by_id(db, order.customer_id)
        if customer is None or not customer.is_active:
            raise DomainValidationError("Customer account must be active before billing.")

        ps_map = sales_repo.get_pack_sizes_by_ids(
            db, [i.pack_size_id for i in order.items], include_inactive=True
        )
        discount_map = {d.sales_order_item_id: d.discount_paisa for d in payload.item_discounts}
        valid_item_ids = {i.id for i in order.items}
        for req_item_id in discount_map:
            if req_item_id not in valid_item_ids:
                raise DomainValidationError(
                    f"Order item {req_item_id} does not belong to order {order.order_number}."
                )

        bill_addr, ship_addr, addr_pos_code, addr_pos_name = _resolve_customer_addresses(
            customer, order.shipping_address_id
        )
        pos_code = order.place_of_supply_state_code or addr_pos_code
        pos_name = (
            addr_pos_name
            if pos_code == addr_pos_code
            else customer.primary_state_name
        )

        tax_inputs: list[TaxLineInput] = []
        for item in order.items:
            qty = item.approved_qty_pkts if item.approved_qty_pkts is not None else item.ordered_qty_pkts
            if qty <= 0:
                continue
            ps = ps_map[item.pack_size_id]
            tax_inputs.append(
                TaxLineInput(
                    sales_order_item_id=item.id,
                    pack_size_id=ps.id,
                    sku_code=ps.sku_code,
                    product_name=ps.product.name,
                    description=ps.display_name,
                    hsn_code=ps.product.hsn_code,
                    qty_pkts=qty,
                    unit_price_paisa=int(item.unit_price_paisa),
                    gst_rate_bps=ps.product.gst_rate_bps,
                    discount_paisa=discount_map.get(item.id, 0),
                )
            )

        calc = validate_tax_conditions_and_calculate_gst(
            seller_gstin=company.gstin,
            seller_state_code=company.state_code,
            seller_state_name=company.state_name,
            buyer_gstin=customer.gstin,
            customer_state_code=customer.primary_state_code,
            place_of_supply_state_code=pos_code,
            place_of_supply_state_name=pos_name,
            lines=tax_inputs,
            apply_round_off=payload.apply_round_off,
        )

        inv_date = payload.invoice_date or datetime.now(IST).date()
        due_date = inv_date + timedelta(days=int(customer.credit_days))
        fy = get_indian_financial_year(inv_date)

        inv = Invoice(
            draft_ref=f"DRF-INV-{uuid4().hex[:10].upper()}",
            invoice_number=None,
            financial_year=fy,
            sales_order_id=order.id,
            customer_id=customer.id,
            customer_name=customer.name,
            customer_type=customer.customer_type,
            seller_legal_name=company.legal_name,
            seller_gstin=company.gstin,
            seller_state_name=company.state_name,
            seller_state_code=company.state_code,
            seller_address=company.address,
            buyer_gstin=customer.gstin,
            place_of_supply_state_name=calc.place_of_supply_state_name,
            place_of_supply_state_code=calc.place_of_supply_state_code,
            billing_address_snapshot=bill_addr,
            shipping_address_snapshot=ship_addr,
            nature_of_supply=calc.nature_of_supply,
            supply_type=calc.supply_type,
            invoice_date=inv_date,
            due_date=due_date,
            payment_terms=f"Net {customer.credit_days} days" if customer.credit_days > 0 else "Immediate",
            doc_status="DRAFT",
            payment_status="UNPAID",
            dispatch_status="PENDING",
            discount_total_paisa=calc.discount_total_paisa,
            taxable_total_paisa=calc.taxable_total_paisa,
            cgst_total_paisa=calc.cgst_total_paisa,
            sgst_total_paisa=calc.sgst_total_paisa,
            igst_total_paisa=calc.igst_total_paisa,
            round_off_paisa=calc.round_off_paisa,
            amount_in_words=calc.amount_in_words,
            notes=payload.notes.strip() if payload.notes else None,
            legal_declaration=_DEFAULT_LEGAL_DECLARATION,
            tax_calculation_snapshot=calc.snapshot,
            created_by=actor.user_id,
        )
        db.add(inv)
        db.flush()

        for ln in calc.lines:
            db.add(
                InvoiceItem(
                    invoice_id=inv.id,
                    sales_order_item_id=ln.sales_order_item_id,
                    pack_size_id=ln.pack_size_id,
                    sku_code=ln.sku_code,
                    product_name=ln.product_name,
                    description=ln.description,
                    hsn_code=ln.hsn_code,
                    qty_pkts=ln.qty_pkts,
                    uom="packet",
                    unit_price_paisa=ln.unit_price_paisa,
                    discount_paisa=ln.discount_paisa,
                    taxable_paisa=ln.taxable_paisa,
                    gst_rate_bps=ln.gst_rate_bps,
                    cgst_rate_bps=ln.cgst_rate_bps,
                    sgst_rate_bps=ln.sgst_rate_bps,
                    igst_rate_bps=ln.igst_rate_bps,
                    cgst_paisa=ln.cgst_paisa,
                    sgst_paisa=ln.sgst_paisa,
                    igst_paisa=ln.igst_paisa,
                )
            )
        for comp in calc.components:
            db.add(
                InvoiceTaxComponent(
                    invoice_id=inv.id,
                    hsn_code=comp.hsn_code,
                    tax_type=comp.tax_type,
                    rate_bps=comp.rate_bps,
                    taxable_base_paisa=comp.taxable_base_paisa,
                    tax_amount_paisa=comp.tax_amount_paisa,
                )
            )
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="INVOICE_DRAFT_CREATED",
            entity_schema="billing",
            entity_table="invoices",
            entity_id=inv.id,
            after_state={
                "invoice_id": inv.id,
                "draft_ref": inv.draft_ref,
                "sales_order_id": order.id,
                "supply_type": inv.supply_type,
                "taxable_total_paisa": inv.taxable_total_paisa,
                "grand_total_paisa": inv.taxable_total_paisa
                + inv.cgst_total_paisa
                + inv.sgst_total_paisa
                + inv.igst_total_paisa
                + inv.round_off_paisa,
                "tax_snapshot": calc.snapshot,
            },
            reason=f"Generated draft GST invoice for {order.order_number}",
        )

        if payload.issue_immediately:
            _perform_issue_invoice(db, inv=inv, order=order, actor=actor)

        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Duplicate active invoice prevented for sales order {payload.sales_order_id}.",
            error_code="DUPLICATE_INVOICE",
        ) from exc
    except Exception:
        db.rollback()
        raise

    created = billing_repo.get_invoice(db, inv.id)
    assert created is not None
    return _hydrate_invoice_detail(db, created)


def verify_invoice(
    db: Session, actor: CurrentActor, invoice_id: int, payload: VerifyInvoiceRequest
) -> InvoiceDetailOut:
    _require_operator(actor, "verify draft GST invoices")
    try:
        inv = billing_repo.get_invoice(db, invoice_id, for_update=True)
        if inv is None:
            raise NotFoundError(f"Invoice {invoice_id} was not found.")
        if payload.expected_version is not None and inv.version != payload.expected_version:
            raise ConflictError("Invoice version changed concurrently.", error_code="VERSION_CONFLICT")
        if inv.doc_status != "DRAFT":
            raise ConflictError(
                f"Only DRAFT invoices can be verified (current status: {inv.doc_status}).",
                error_code="INVALID_STATE_TRANSITION",
            )
        inv.verified_by = actor.user_id
        inv.verified_at = datetime.now(UTC)
        inv.verification_remarks = payload.remarks.strip() if payload.remarks else "Verified by Factory Admin"
        inv.version += 1
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="INVOICE_VERIFIED",
            entity_schema="billing",
            entity_table="invoices",
            entity_id=inv.id,
            after_state={"invoice_id": inv.id, "verified_at": inv.verified_at.isoformat()},
            reason=inv.verification_remarks,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = billing_repo.get_invoice(db, invoice_id)
    assert refreshed is not None
    return _hydrate_invoice_detail(db, refreshed)


def issue_invoice(
    db: Session, actor: CurrentActor, invoice_id: int, payload: IssueInvoiceRequest
) -> InvoiceDetailOut:
    """DRAFT -> ISSUED: Allocate gap-free FY sequence & freeze invoice atomically."""
    _require_operator(actor, "issue statutory GST invoices")
    try:
        inv = billing_repo.get_invoice(db, invoice_id, for_update=True)
        if inv is None:
            raise NotFoundError(f"Invoice {invoice_id} was not found.")
        if payload.expected_version is not None and inv.version != payload.expected_version:
            raise ConflictError("Invoice version changed concurrently.", error_code="VERSION_CONFLICT")
        order = orders_repo.get_order_by_id_for_update(db, inv.sales_order_id)
        assert order is not None

        _perform_issue_invoice(
            db,
            inv=inv,
            order=order,
            actor=actor,
            verification_remarks=payload.verification_remarks,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = billing_repo.get_invoice(db, invoice_id)
    assert refreshed is not None
    return _hydrate_invoice_detail(db, refreshed)


def get_invoice_detail_scoped(db: Session, actor: CurrentActor, invoice_id: int) -> InvoiceDetailOut:
    inv = billing_repo.get_invoice(db, invoice_id)
    if inv is None:
        raise NotFoundError(f"Invoice {invoice_id} was not found.")
    if actor.role_code == "SALESMAN":
        order = orders_repo.get_order_by_id(db, inv.sales_order_id)
        if order is None or order.salesman_id != actor.user_id:
            raise AuthorizationError("Salesmen can only view invoices belonging to their own orders.")
        return _hydrate_invoice_detail(db, inv, include_audit=False)
    _require_viewer(actor, "view invoice details")
    return _hydrate_invoice_detail(db, inv, include_audit=True)


def list_invoices_view(
    db: Session,
    actor: CurrentActor,
    *,
    doc_status: str | None = None,
    dispatch_status: str | None = None,
    search: str | None = None,
) -> list[InvoiceSummaryOut]:
    _require_viewer(actor, "list GST invoices")
    rows = billing_repo.list_invoices(
        db, doc_status=doc_status, dispatch_status=dispatch_status, search=search
    )
    ord_map = _orders_map(db, {inv.sales_order_id for inv in rows})
    item_ids = [it.id for inv in rows for it in inv.items]
    dispatched_by_item = billing_repo.sum_dispatched_qty_by_invoice_item_ids(db, item_ids)
    return [
        _hydrate_invoice_summary(i, ord_map=ord_map, dispatched_by_item=dispatched_by_item)
        for i in rows
    ]


def generate_invoice_pdf_scoped(
    db: Session, actor: CurrentActor, invoice_id: int
) -> tuple[bytes, str]:
    inv = billing_repo.get_invoice(db, invoice_id)
    if inv is None:
        raise NotFoundError(f"Invoice {invoice_id} was not found.")
    order = orders_repo.get_order_by_id(db, inv.sales_order_id)
    assert order is not None

    if actor.role_code == "SALESMAN":
        if order.salesman_id != actor.user_id:
            raise AuthorizationError("Salesmen can only download PDFs for their own orders.")
        if inv.doc_status == "DRAFT":
            raise AuthorizationError("Draft invoices are not available for download by salesmen.")
    else:
        _require_viewer(actor, "download GST invoice PDF")

    pdf_bytes = render_invoice_pdf(inv, order_number=order.order_number)
    safe_name = (inv.invoice_number or inv.draft_ref).replace("/", "-")
    return pdf_bytes, f"{safe_name}.pdf"


# ── Credit Notes ────────────────────────────────────────────────────────────


def _apply_credit_note_issuance(
    db: Session,
    *,
    cn: CreditNote,
    inv: Invoice,
    actor: CurrentActor,
) -> None:
    if cn.status == "ISSUED":
        raise ConflictError("Credit note is already issued.", error_code="DUPLICATE_CREDIT_NOTE")
    if inv.doc_status != "ISSUED":
        raise ConflictError(
            f"Cannot issue credit note against invoice in '{inv.doc_status}' status.",
            error_code="INVALID_STATE_TRANSITION",
        )

    remaining_creditable = int(inv.grand_total_paisa) - int(inv.credited_paisa)
    if int(cn.total_reversed_paisa) > remaining_creditable:
        raise ConflictError(
            f"Credit note reversal ({cn.total_reversed_paisa} paise) exceeds remaining invoice balance ({remaining_creditable} paise).",
            error_code="EXCESS_CREDIT_NOTE",
        )

    now_utc = datetime.now(UTC)
    cn_no = billing_repo.allocate_fiscal_sequence(
        db, doc_type="CREDIT_NOTE", financial_year=cn.financial_year, prefix="CN"
    )
    cn.cn_number = cn_no
    cn.status = "ISSUED"
    cn.approved_by = actor.user_id
    cn.approved_at = now_utc
    cn.issued_by = actor.user_id
    cn.issued_at = now_utc

    inv.credited_paisa = int(inv.credited_paisa) + int(cn.total_reversed_paisa)
    is_full_cancel = cn.cancel_original_invoice or (inv.credited_paisa >= int(inv.grand_total_paisa))
    if is_full_cancel:
        inv.doc_status = "CANCELLED_BY_CN"
        inv.payment_status = "CREDITED"
    inv.version += 1

    order = orders_repo.get_order_by_id_for_update(db, inv.sales_order_id)
    assert order is not None

    # Release undispatched FG reservations if full invoice cancellation occurs before full dispatch
    if is_full_cancel:
        active_res = inventory_repo.list_active_reservations_for_order_for_update(db, order.id)
        if active_res:
            locked_bals = inventory_repo.lock_balances_by_pack_size_ids(
                db, [r.pack_size_id for r in active_res]
            )
            for r in active_res:
                rem = r.reserved_qty_pkts - r.fulfilled_qty_pkts
                if rem > 0 and r.pack_size_id in locked_bals:
                    bal = locked_bals[r.pack_size_id]
                    bal.reserved_qty_base = max(
                        Decimal("0.000"),
                        (Decimal(bal.reserved_qty_base) - Decimal(rem)).quantize(Decimal("0.001")),
                    )
                r.status = "RELEASED"
                r.released_by = actor.user_id
                r.released_at = now_utc
                r.release_reason = f"Cancelled via Credit Note {cn_no}"

        if order.status == OrderStatus.INVOICED:
            prev = order.status
            order.status = OrderStatus.CANCELLED
            order.cancelled_by = actor.user_id
            order.cancelled_at = now_utc
            order.cancellation_reason = f"Credit Note {cn_no}: {cn.reason}"
            order.version += 1
            db.add(
                SalesOrderStatusHistory(
                    sales_order_id=order.id,
                    from_status=prev,
                    to_status=OrderStatus.CANCELLED,
                    changed_by=actor.user_id,
                    reason=f"Invoice {inv.invoice_number} cancelled by {cn_no}",
                )
            )

    # Stock return ledger writes ONLY for physical RESTOCK_SELLABLE goods returns
    restock_items = [it for it in cn.items if it.return_disposition == "RESTOCK_SELLABLE" and it.qty_pkts > 0]
    if restock_items:
        inventory_repo.lock_balances_by_pack_size_ids(db, [it.pack_size_id for it in restock_items])
        for it in restock_items:
            lots = inventory_repo.list_open_cost_lots_for_update(db, pack_size_id=it.pack_size_id)
            unit_cost = Decimal(lots[0].unit_cost_paisa_per_base) if lots else Decimal("2885.000000")
            qty_dec = Decimal(it.qty_pkts).quantize(Decimal("0.001"))
            tot_cost = int((qty_dec * unit_cost).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            db.add(
                InventoryMovement(
                    item_category="FINISHED_GOOD",
                    pack_size_id=it.pack_size_id,
                    movement_type="CREDIT_RETURN_IN",
                    entered_qty=qty_dec,
                    entered_uom="packet",
                    signed_qty_base=qty_dec,
                    unit_cost_paisa_per_base=unit_cost,
                    total_cost_paisa=tot_cost,
                    source_doc_type="CREDIT_NOTE",
                    reference_code=cn_no,
                    notes=f"Sellable sales return from {inv.invoice_number} via {cn_no}",
                    credit_note_item_id=it.id,
                    created_by=actor.user_id,
                )
            )
            db.add(
                CostLot(
                    item_category="FINISHED_GOOD",
                    pack_size_id=it.pack_size_id,
                    source_doc_type="CREDIT_NOTE",
                    source_doc_id=cn.id,
                    batch_code=cn_no,
                    original_qty_base=qty_dec,
                    remaining_qty_base=qty_dec,
                    unit_cost_paisa_per_base=unit_cost,
                )
            )

    db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="CREDIT_NOTE_ISSUED",
        entity_schema="billing",
        entity_table="credit_notes",
        entity_id=cn.id,
        after_state={
            "cn_number": cn_no,
            "invoice_id": inv.id,
            "original_invoice_number": inv.invoice_number,
            "note_type": cn.note_type,
            "cancel_original_invoice": is_full_cancel,
            "total_reversed_paisa": int(cn.taxable_reversed_paisa + cn.cgst_reversed_paisa + cn.sgst_reversed_paisa + cn.igst_reversed_paisa + cn.round_off_reversed_paisa),
        },
        reason=cn.reason,
    )


def create_credit_note(
    db: Session, actor: CurrentActor, payload: CreateCreditNoteRequest
) -> CreditNoteOut:
    """Create a controlled GST Credit Note (cancellation, return, or value adjustment)."""
    _require_operator(actor, "issue GST credit notes")
    try:
        inv = billing_repo.get_invoice(db, payload.original_invoice_id, for_update=True)
        if inv is None:
            raise NotFoundError(f"Invoice {payload.original_invoice_id} was not found.")
        if inv.doc_status != "ISSUED":
            raise ConflictError(
                f"Cannot create credit note for invoice {inv.invoice_number or inv.draft_ref} in '{inv.doc_status}' status.",
                error_code="INVALID_STATE_TRANSITION",
            )

        inv_items_map = {it.id: it for it in inv.items}
        dispatched_by_item = billing_repo.sum_dispatched_qty_by_invoice_item_ids(
            db, list(inv_items_map.keys())
        )
        total_dispatched = sum(dispatched_by_item.values())

        requested_lines = payload.items
        if not requested_lines:
            if payload.note_type != "INVOICE_CANCELLATION":
                raise DomainValidationError("Item references are required for Sales Return or Value Adjustment credit notes.")
            default_disp = "NONE_NOT_DISPATCHED" if total_dispatched == 0 else "RESTOCK_SELLABLE"
            requested_lines = [
                type("Line", (), {
                    "invoice_item_id": it.id,
                    "qty_pkts": it.qty_pkts,
                    "taxable_override_paisa": int(it.taxable_paisa),
                    "return_disposition": default_disp,
                })()
                for it in inv.items
            ]

        cn_date = payload.issue_date or datetime.now(IST).date()
        fy = get_indian_financial_year(cn_date)

        taxable_sum = 0
        cgst_sum = 0
        sgst_sum = 0
        igst_sum = 0
        built_items: list[CreditNoteItem] = []

        for req in requested_lines:
            orig_item = inv_items_map.get(req.invoice_item_id)
            if orig_item is None:
                raise DomainValidationError(
                    f"Invoice item {req.invoice_item_id} does not belong to invoice {inv.invoice_number}."
                )
            if req.qty_pkts > orig_item.qty_pkts:
                raise ConflictError(
                    f"Credit note qty ({req.qty_pkts}) exceeds invoiced qty ({orig_item.qty_pkts}) on {orig_item.sku_code}.",
                    error_code="EXCESS_CREDIT_QUANTITY",
                )
            if req.return_disposition in {"RESTOCK_SELLABLE", "SCRAP_DAMAGED"} and dispatched_by_item.get(orig_item.id, 0) < req.qty_pkts:
                raise ConflictError(
                    f"Cannot record physical return of {req.qty_pkts} pkts on {orig_item.sku_code}; only {dispatched_by_item.get(orig_item.id, 0)} pkts dispatched.",
                    error_code="RETURN_EXCEEDS_DISPATCHED",
                )

            if req.taxable_override_paisa is not None:
                line_taxable = req.taxable_override_paisa
            elif req.qty_pkts == orig_item.qty_pkts:
                line_taxable = int(orig_item.taxable_paisa)
            else:
                per_unit_net = Decimal(orig_item.taxable_paisa) / Decimal(orig_item.qty_pkts)
                line_taxable = int((per_unit_net * Decimal(req.qty_pkts)).quantize(Decimal(1), rounding=ROUND_HALF_UP))

            if line_taxable <= 0:
                raise DomainValidationError(f"Credit reversal amount must be positive for {orig_item.sku_code}.")

            if inv.supply_type == "INTRA_STATE":
                cgst_rev = round_half_up_bps(line_taxable, orig_item.cgst_rate_bps)
                sgst_rev = cgst_rev
                igst_rev = 0
            else:
                cgst_rev = 0
                sgst_rev = 0
                igst_rev = round_half_up_bps(line_taxable, orig_item.igst_rate_bps)

            taxable_sum += line_taxable
            cgst_sum += cgst_rev
            sgst_sum += sgst_rev
            igst_sum += igst_rev
            built_items.append(
                CreditNoteItem(
                    invoice_item_id=orig_item.id,
                    pack_size_id=orig_item.pack_size_id,
                    qty_pkts=req.qty_pkts,
                    return_disposition=req.return_disposition,
                    taxable_reversed_paisa=line_taxable,
                    cgst_reversed_paisa=cgst_rev,
                    sgst_reversed_paisa=sgst_rev,
                    igst_reversed_paisa=igst_rev,
                )
            )

        cancel_orig = payload.cancel_original_invoice or (payload.note_type == "INVOICE_CANCELLATION")
        round_rev = int(inv.round_off_paisa) if cancel_orig else 0
        total_rev = taxable_sum + cgst_sum + sgst_sum + igst_sum + round_rev
        remaining_creditable = int(inv.grand_total_paisa) - int(inv.credited_paisa)
        if total_rev > remaining_creditable:
            raise ConflictError(
                f"Credit note total ({total_rev} paise) exceeds remaining creditable balance ({remaining_creditable} paise).",
                error_code="EXCESS_CREDIT_NOTE",
            )

        cn = CreditNote(
            draft_ref=f"DRF-CN-{uuid4().hex[:10].upper()}",
            cn_number=None,
            financial_year=fy,
            original_invoice_id=inv.id,
            customer_id=inv.customer_id,
            supply_type=inv.supply_type,
            note_type=payload.note_type,
            issue_date=cn_date,
            reason=payload.reason,
            status="DRAFT",
            cancel_original_invoice=cancel_orig,
            taxable_reversed_paisa=taxable_sum,
            cgst_reversed_paisa=cgst_sum,
            sgst_reversed_paisa=sgst_sum,
            igst_reversed_paisa=igst_sum,
            round_off_reversed_paisa=round_rev,
            created_by=actor.user_id,
        )
        db.add(cn)
        db.flush()
        for ci in built_items:
            ci.credit_note_id = cn.id
            db.add(ci)
        db.flush()
        cn.items = built_items

        if payload.issue_immediately:
            _apply_credit_note_issuance(db, cn=cn, inv=inv, actor=actor)

        db.commit()
    except Exception:
        db.rollback()
        raise

    created = billing_repo.get_credit_note(db, cn.id)
    assert created is not None
    return get_credit_note_detail(db, actor, created.id)


def issue_credit_note(db: Session, actor: CurrentActor, cn_id: int) -> CreditNoteOut:
    _require_operator(actor, "issue GST credit notes")
    try:
        cn = billing_repo.get_credit_note(db, cn_id, for_update=True)
        if cn is None:
            raise NotFoundError(f"Credit note {cn_id} was not found.")
        inv = billing_repo.get_invoice(db, cn.original_invoice_id, for_update=True)
        assert inv is not None
        _apply_credit_note_issuance(db, cn=cn, inv=inv, actor=actor)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_credit_note_detail(db, actor, cn_id)


def get_credit_note_detail(db: Session, actor: CurrentActor, cn_id: int) -> CreditNoteOut:
    _require_viewer(actor, "view credit notes")
    cn = billing_repo.get_credit_note(db, cn_id)
    if cn is None:
        raise NotFoundError(f"Credit note {cn_id} was not found.")
    inv = billing_repo.get_invoice(db, cn.original_invoice_id)
    assert inv is not None
    cust_map = _customers_map(db, {cn.customer_id})
    ps_map = sales_repo.get_pack_sizes_by_ids(
        db, [i.pack_size_id for i in cn.items], include_inactive=True
    )
    uids = {cn.created_by}
    if cn.approved_by:
        uids.add(cn.approved_by)
    if cn.issued_by:
        uids.add(cn.issued_by)
    return _hydrate_credit_note(
        cn,
        invoice_map={inv.id: inv},
        cust_map=cust_map,
        users=_users_map(db, uids),
        ps_map=ps_map,
        inv_items_map={it.id: it for it in inv.items},
    )


def list_credit_notes_view(db: Session, actor: CurrentActor) -> list[CreditNoteOut]:
    _require_viewer(actor, "list credit notes")
    rows = billing_repo.list_credit_notes(db)
    if not rows:
        return []
    inv_ids = {cn.original_invoice_id for cn in rows}
    cust_ids = {cn.customer_id for cn in rows}
    ps_ids = {ci.pack_size_id for cn in rows for ci in cn.items}
    uids = {cn.created_by for cn in rows} | {cn.approved_by for cn in rows if cn.approved_by} | {cn.issued_by for cn in rows if cn.issued_by}

    inv_rows = [billing_repo.get_invoice(db, iid) for iid in inv_ids]
    inv_map = {inv.id: inv for inv in inv_rows if inv is not None}
    inv_items_map = {it.id: it for inv in inv_map.values() for it in inv.items}
    cust_map = _customers_map(db, cust_ids)
    ps_map = sales_repo.get_pack_sizes_by_ids(db, list(ps_ids), include_inactive=True)
    users = _users_map(db, uids)
    return [
        _hydrate_credit_note(
            cn,
            invoice_map=inv_map,
            cust_map=cust_map,
            users=users,
            ps_map=ps_map,
            inv_items_map=inv_items_map,
        )
        for cn in rows
    ]


# ── Dispatch, Inventory Integration & Delivery Tracking ─────────────────────


def get_dispatch_dashboard(
    db: Session, actor: CurrentActor, *, status: str | None = None
) -> DispatchDashboardOut:
    _require_viewer(actor, "view dispatch dashboard")
    ready_invoices_raw = billing_repo.list_ready_for_dispatch_invoices(db)
    ready_item_ids = [it.id for inv in ready_invoices_raw for it in inv.items]
    committed_map = billing_repo.sum_dispatched_qty_by_invoice_item_ids(db, ready_item_ids)
    ps_ids = list({it.pack_size_id for inv in ready_invoices_raw for it in inv.items})
    avail_map = inventory_repo.get_balances_by_pack_size_ids(db, ps_ids)
    ord_map = _orders_map(db, {inv.sales_order_id for inv in ready_invoices_raw})

    ready_invoices: list[ReadyForDispatchInvoiceOut] = []
    for inv in ready_invoices_raw:
        tot_inv = sum(i.qty_pkts for i in inv.items)
        tot_dsp = sum(committed_map.get(i.id, 0) for i in inv.items)
        rem = tot_inv - tot_dsp
        if rem <= 0:
            continue
        enough_fg = all(
            int(avail_map[i.pack_size_id].on_hand_qty_base) >= max(0, i.qty_pkts - committed_map.get(i.id, 0))
            if i.pack_size_id in avail_map
            else False
            for i in inv.items
        )
        ready_invoices.append(
            ReadyForDispatchInvoiceOut(
                invoice_id=inv.id,
                invoice_number=inv.invoice_number or inv.draft_ref,
                sales_order_id=inv.sales_order_id,
                order_number=ord_map[inv.sales_order_id].order_number,
                customer_id=inv.customer_id,
                customer_name=inv.customer_name,
                place_of_supply_state_code=inv.place_of_supply_state_code,
                invoice_date=inv.invoice_date,
                dispatch_status=inv.dispatch_status,
                total_qty_pkts=tot_inv,
                dispatched_qty_pkts=tot_dsp,
                remaining_qty_pkts=rem,
                fg_on_hand_sufficient=enough_fg,
            )
        )

    all_dsp = billing_repo.list_dispatches(db, limit=500)
    filtered = [d for d in all_dsp if status is None or d.status == status]
    hyd_ord = _orders_map(db, {d.sales_order_id for d in filtered})
    hyd_cust = _customers_map(db, {d.customer_id for d in filtered})
    hyd_ps = sales_repo.get_pack_sizes_by_ids(
        db, list({di.pack_size_id for d in filtered for di in d.items}), include_inactive=True
    )
    inv_rows = (
        db.execute(select(Invoice).where(Invoice.id.in_({d.invoice_id for d in filtered}))).scalars().all()
        if filtered
        else []
    )
    hyd_inv = {i.id: i for i in inv_rows}
    uids: set[int] = set()
    for d in filtered:
        uids.add(d.created_by)
        for uid in (d.ready_by, d.dispatched_by, d.delivery_confirmed_by):
            if uid:
                uids.add(uid)
        for h in d.status_history:
            uids.add(h.changed_by)
    users = _users_map(db, uids)

    return DispatchDashboardOut(
        ready_for_dispatch_invoices_count=len(ready_invoices),
        created_count=sum(1 for d in all_dsp if d.status == "CREATED"),
        ready_count=sum(1 for d in all_dsp if d.status == "READY_FOR_DISPATCH"),
        dispatched_count=sum(1 for d in all_dsp if d.status == "DISPATCHED"),
        in_transit_count=sum(1 for d in all_dsp if d.status == "IN_TRANSIT"),
        delivered_count=sum(1 for d in all_dsp if d.status == "DELIVERED"),
        exception_count=sum(1 for d in all_dsp if d.status == "DELIVERY_EXCEPTION"),
        ready_invoices=ready_invoices,
        dispatches=[
            _hydrate_dispatch(
                d, inv_map=hyd_inv, ord_map=hyd_ord, cust_map=hyd_cust, users=users, ps_map=hyd_ps
            )
            for d in filtered
        ],
    )


def _perform_post_dispatch(
    db: Session,
    *,
    dsp: Dispatch,
    inv: Invoice,
    order: SalesOrder,
    actor: CurrentActor,
) -> None:
    if dsp.status not in {"CREATED", "READY_FOR_DISPATCH"}:
        raise ConflictError(
            f"Dispatch {dsp.dispatch_number} is already in status '{dsp.status}'; duplicate posting is blocked.",
            error_code="DUPLICATE_DISPATCH_POST",
        )
    if inv.doc_status != "ISSUED":
        raise ConflictError(
            f"Cannot post dispatch for invoice in '{inv.doc_status}' status.",
            error_code="INVOICE_NOT_ISSUED",
        )

    ps_ids = [di.pack_size_id for di in dsp.items]
    locked_bals = inventory_repo.lock_balances_by_pack_size_ids(db, ps_ids)
    active_res = inventory_repo.list_active_reservations_for_order_for_update(db, order.id)
    res_by_order_item = {r.sales_order_item_id: r for r in active_res}
    inv_item_by_id = {it.id: it for it in inv.items}

    # Pre-validate physical stock BEFORE touching any ledger or reservation rows (atomic safety)
    for di in dsp.items:
        bal = locked_bals.get(di.pack_size_id)
        on_hand = int(bal.on_hand_qty_base) if bal else 0
        if on_hand < di.dispatched_qty_pkts:
            raise ConflictError(
                f"Insufficient finished-goods physical stock on SKU {di.pack_size_id}: on hand {on_hand} pkts, dispatch requests {di.dispatched_qty_pkts} pkts.",
                error_code="INSUFFICIENT_STOCK",
            )

    now_utc = datetime.now(UTC)
    movement_ids: list[int] = []

    for di in dsp.items:
        inv_item = inv_item_by_id[di.invoice_item_id]
        qty_dec = Decimal(di.dispatched_qty_pkts).quantize(Decimal("0.001"))

        # Deplete FG CostLot layers in FEFO order
        lots = billing_repo.list_open_fg_lots_fefo_for_update(db, pack_size_id=di.pack_size_id)
        rem_to_consume = qty_dec
        total_cost_paisa = 0
        consumed_pairs: list[tuple[CostLot, Decimal, int]] = []
        batch_refs: list[str] = []

        for lot in lots:
            if rem_to_consume <= 0:
                break
            take = min(Decimal(lot.remaining_qty_base), rem_to_consume).quantize(Decimal("0.001"))
            lot.remaining_qty_base = (Decimal(lot.remaining_qty_base) - take).quantize(Decimal("0.001"))
            lot_cost = int((take * Decimal(lot.unit_cost_paisa_per_base)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            consumed_pairs.append((lot, take, lot_cost))
            total_cost_paisa += lot_cost
            if lot.batch_code and lot.batch_code not in batch_refs:
                batch_refs.append(lot.batch_code)
            rem_to_consume -= take

        if not di.batch_code_ref and batch_refs:
            di.batch_code_ref = ", ".join(batch_refs)[:120]

        unit_cost_base = (
            (Decimal(total_cost_paisa) / qty_dec).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            if total_cost_paisa > 0
            else Decimal("0.000000")
        )

        # Fulfill reservation proportionally and ensure InventoryBalance.reserved_qty_base <= on_hand_qty_base holds!
        bal = locked_bals[di.pack_size_id]
        res = res_by_order_item.get(inv_item.sales_order_item_id)
        if res is not None:
            rem_res = res.reserved_qty_pkts - res.fulfilled_qty_pkts
            release_amt = min(rem_res, di.dispatched_qty_pkts)
            if release_amt > 0:
                bal.reserved_qty_base = max(
                    Decimal("0.000"),
                    (Decimal(bal.reserved_qty_base) - Decimal(release_amt)).quantize(Decimal("0.001")),
                )
                res.fulfilled_qty_pkts += release_amt
                if res.fulfilled_qty_pkts >= res.reserved_qty_pkts:
                    res.status = "FULFILLED"

        mov = InventoryMovement(
            item_category="FINISHED_GOOD",
            pack_size_id=di.pack_size_id,
            movement_type="DISPATCH_OUT",
            entered_qty=qty_dec,
            entered_uom="packet",
            signed_qty_base=-qty_dec,
            unit_cost_paisa_per_base=unit_cost_base,
            total_cost_paisa=total_cost_paisa,
            source_doc_type="DISPATCH",
            reference_code=dsp.dispatch_number,
            notes=(
                f"Dispatched against {inv.invoice_number} / {order.order_number}"
                + (f" (Vehicle {dsp.vehicle_number})" if dsp.vehicle_number else "")
            ),
            dispatch_item_id=di.id,
            created_by=actor.user_id,
        )
        db.add(mov)
        db.flush()
        movement_ids.append(mov.id)

        for lot, take_qty, lot_cost in consumed_pairs:
            db.add(
                CostLotConsumption(
                    inventory_movement_id=mov.id,
                    cost_lot_id=lot.id,
                    consumed_qty_base=take_qty,
                    unit_cost_paisa_per_base=Decimal(lot.unit_cost_paisa_per_base),
                    cost_paisa=lot_cost,
                )
            )

    prev_dsp_status = dsp.status
    dsp.status = "DISPATCHED"
    dsp.dispatched_by = actor.user_id
    dsp.dispatched_at = now_utc
    dsp.version += 1
    db.add(
        DispatchStatusHistory(
            dispatch_id=dsp.id,
            from_status=prev_dsp_status,
            to_status="DISPATCHED",
            changed_by=actor.user_id,
            reason=f"Posted dispatch {dsp.dispatch_number} to inventory ledger",
        )
    )
    db.flush()

    # Check cumulative POSTED/IN_TRANSIT/DELIVERED dispatch quantity vs invoice total
    all_posted_dsps = [
        d for d in inv.dispatches if d.status in {"DISPATCHED", "IN_TRANSIT", "DELIVERED", "DELIVERY_EXCEPTION"}
    ]
    if dsp not in all_posted_dsps:
        all_posted_dsps.append(dsp)
    posted_qty = sum(di.dispatched_qty_pkts for d in all_posted_dsps for di in d.items)
    total_inv_qty = sum(i.qty_pkts for i in inv.items)

    if posted_qty >= total_inv_qty:
        inv.dispatch_status = "DISPATCHED"
        target_order_status = OrderStatus.DISPATCHED
    else:
        inv.dispatch_status = "PARTIAL"
        target_order_status = OrderStatus.PARTIALLY_DISPATCHED
    inv.version += 1

    if order.status != target_order_status:
        prev_order_status = order.status
        order.status = target_order_status
        order.version += 1
        db.add(
            SalesOrderStatusHistory(
                sales_order_id=order.id,
                from_status=prev_order_status,
                to_status=target_order_status,
                changed_by=actor.user_id,
                reason=f"Dispatch {dsp.dispatch_number} posted ({posted_qty}/{total_inv_qty} pkts)",
            )
        )

    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="DISPATCH_POSTED",
        entity_schema="billing",
        entity_table="dispatches",
        entity_id=dsp.id,
        before_state={"status": prev_dsp_status},
        after_state={
            "dispatch_id": dsp.id,
            "dispatch_number": dsp.dispatch_number,
            "invoice_id": inv.id,
            "invoice_number": inv.invoice_number,
            "sales_order_id": order.id,
            "dispatched_pkts": sum(i.dispatched_qty_pkts for i in dsp.items),
            "cumulative_posted_pkts": posted_qty,
            "invoiced_pkts": total_inv_qty,
            "movement_ids": movement_ids,
        },
        reason=f"Posted dispatch {dsp.dispatch_number} atomically with FG DISPATCH_OUT",
    )


def create_dispatch(
    db: Session, actor: CurrentActor, payload: CreateDispatchRequest
) -> DispatchOut:
    """Create a dispatch record bound strictly to an ISSUED GST Invoice (supporting partial dispatch)."""
    _require_operator(actor, "create dispatch notes")
    try:
        inv = billing_repo.get_invoice(db, payload.invoice_id, for_update=True)
        if inv is None:
            raise NotFoundError(f"Invoice {payload.invoice_id} was not found.")
        if inv.doc_status != "ISSUED":
            raise ConflictError(
                f"Cannot create dispatch: invoice {inv.invoice_number or inv.draft_ref} must be in 'ISSUED' status (current: '{inv.doc_status}').",
                error_code="INVOICE_NOT_ISSUED",
            )
        order = orders_repo.get_order_by_id_for_update(db, inv.sales_order_id)
        assert order is not None

        inv_items_map = {it.id: it for it in inv.items}
        already_committed = billing_repo.sum_dispatched_qty_by_invoice_item_ids(
            db, list(inv_items_map.keys())
        )

        seen_items: set[int] = set()
        for req in payload.items:
            if req.invoice_item_id in seen_items:
                raise DomainValidationError(f"Duplicate invoice item {req.invoice_item_id} in dispatch.")
            seen_items.add(req.invoice_item_id)
            orig = inv_items_map.get(req.invoice_item_id)
            if orig is None:
                raise DomainValidationError(
                    f"Invoice item {req.invoice_item_id} does not belong to invoice {inv.invoice_number}."
                )
            committed = already_committed.get(orig.id, 0)
            remaining = orig.qty_pkts - committed
            if req.dispatched_qty_pkts > remaining:
                raise ConflictError(
                    f"Dispatch qty ({req.dispatched_qty_pkts}) exceeds remaining undispatched qty ({remaining}) for {orig.sku_code} (invoiced {orig.qty_pkts}, already dispatched/allocated {committed}).",
                    error_code="DISPATCH_EXCEEDS_ORDER",
                )

        dsp_date = payload.dispatch_date or datetime.now(IST).date()
        fy = get_indian_financial_year(dsp_date)
        dsp_no = billing_repo.allocate_fiscal_sequence(
            db, doc_type="DISPATCH", financial_year=fy, prefix="DSP"
        )
        dsp = Dispatch(
            dispatch_number=dsp_no,
            invoice_id=inv.id,
            sales_order_id=order.id,
            customer_id=inv.customer_id,
            status="CREATED",
            dispatch_date=dsp_date,
            transporter_name=payload.transporter_name.strip() if payload.transporter_name else None,
            vehicle_number=payload.vehicle_number.strip().upper() if payload.vehicle_number else None,
            lr_number=payload.lr_number.strip() if payload.lr_number else None,
            packing_verified=payload.packing_verified,
            packing_remarks=payload.packing_remarks.strip() if payload.packing_remarks else None,
            notes=payload.notes.strip() if payload.notes else None,
            created_by=actor.user_id,
        )
        db.add(dsp)
        db.flush()

        built_items: list[DispatchItem] = []
        for req in payload.items:
            orig = inv_items_map[req.invoice_item_id]
            di = DispatchItem(
                dispatch_id=dsp.id,
                invoice_item_id=orig.id,
                pack_size_id=orig.pack_size_id,
                dispatched_qty_pkts=req.dispatched_qty_pkts,
                batch_code_ref=req.batch_code_ref.strip() if req.batch_code_ref else None,
            )
            db.add(di)
            built_items.append(di)
        db.add(
            DispatchStatusHistory(
                dispatch_id=dsp.id,
                from_status=None,
                to_status="CREATED",
                changed_by=actor.user_id,
                reason=f"Created dispatch {dsp_no} for {inv.invoice_number}",
            )
        )
        db.flush()
        dsp.items = built_items

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="DISPATCH_CREATED",
            entity_schema="billing",
            entity_table="dispatches",
            entity_id=dsp.id,
            after_state={
                "dispatch_number": dsp_no,
                "invoice_id": inv.id,
                "invoice_number": inv.invoice_number,
                "items": [
                    {"sku_code": inv_items_map[di.invoice_item_id].sku_code, "qty_pkts": di.dispatched_qty_pkts}
                    for di in built_items
                ],
            },
            reason=f"Created dispatch {dsp_no}",
        )

        if payload.post_immediately:
            _perform_post_dispatch(db, dsp=dsp, inv=inv, order=order, actor=actor)

        db.commit()
    except Exception:
        db.rollback()
        raise

    return get_dispatch_detail_scoped(db, actor, dsp.id)


def mark_dispatch_ready(
    db: Session, actor: CurrentActor, dispatch_id: int, payload: DispatchActionRemarksRequest
) -> DispatchOut:
    _require_operator(actor, "mark dispatch ready")
    try:
        dsp = billing_repo.get_dispatch(db, dispatch_id, for_update=True)
        if dsp is None:
            raise NotFoundError(f"Dispatch {dispatch_id} was not found.")
        if payload.expected_version is not None and dsp.version != payload.expected_version:
            raise ConflictError("Dispatch changed concurrently.", error_code="VERSION_CONFLICT")
        if dsp.status != "CREATED":
            raise ConflictError(
                f"Dispatch {dsp.dispatch_number} in status '{dsp.status}' cannot transition to READY_FOR_DISPATCH.",
                error_code="INVALID_STATE_TRANSITION",
            )

        dsp.status = "READY_FOR_DISPATCH"
        dsp.packing_verified = True
        dsp.ready_by = actor.user_id
        dsp.ready_at = datetime.now(UTC)
        if payload.remarks:
            dsp.packing_remarks = payload.remarks.strip()
        if payload.transporter_name:
            dsp.transporter_name = payload.transporter_name.strip()
        if payload.vehicle_number:
            dsp.vehicle_number = payload.vehicle_number.strip().upper()
        if payload.lr_number:
            dsp.lr_number = payload.lr_number.strip()
        dsp.version += 1

        db.add(
            DispatchStatusHistory(
                dispatch_id=dsp.id,
                from_status="CREATED",
                to_status="READY_FOR_DISPATCH",
                changed_by=actor.user_id,
                reason=dsp.packing_remarks or "Packing verified & ready for dispatch",
            )
        )
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="DISPATCH_READY",
            entity_schema="billing",
            entity_table="dispatches",
            entity_id=dsp.id,
            after_state={"invoice_id": dsp.invoice_id, "status": "READY_FOR_DISPATCH"},
            reason=dsp.packing_remarks,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_dispatch_detail_scoped(db, actor, dispatch_id)


def post_dispatch(
    db: Session, actor: CurrentActor, dispatch_id: int, payload: DispatchActionRemarksRequest
) -> DispatchOut:
    """Atomically deduct FG stock (DISPATCH_OUT), fulfill reservation, update invoice & order status."""
    _require_operator(actor, "post dispatch and deduct inventory")
    try:
        dsp = billing_repo.get_dispatch(db, dispatch_id, for_update=True)
        if dsp is None:
            raise NotFoundError(f"Dispatch {dispatch_id} was not found.")
        if payload.expected_version is not None and dsp.version != payload.expected_version:
            raise ConflictError("Dispatch changed concurrently.", error_code="VERSION_CONFLICT")
        inv = billing_repo.get_invoice(db, dsp.invoice_id, for_update=True)
        assert inv is not None
        order = orders_repo.get_order_by_id_for_update(db, dsp.sales_order_id)
        assert order is not None

        if payload.transporter_name:
            dsp.transporter_name = payload.transporter_name.strip()
        if payload.vehicle_number:
            dsp.vehicle_number = payload.vehicle_number.strip().upper()
        if payload.lr_number:
            dsp.lr_number = payload.lr_number.strip()

        _perform_post_dispatch(db, dsp=dsp, inv=inv, order=order, actor=actor)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_dispatch_detail_scoped(db, actor, dispatch_id)


def update_delivery_status(
    db: Session, actor: CurrentActor, dispatch_id: int, payload: UpdateDeliveryStatusRequest
) -> DispatchOut:
    """Update delivery tracking (IN_TRANSIT, DELIVERED, DELIVERY_EXCEPTION) with partial/discrepancy logging."""
    _require_operator(actor, "update delivery tracking")
    try:
        dsp = billing_repo.get_dispatch(db, dispatch_id, for_update=True)
        if dsp is None:
            raise NotFoundError(f"Dispatch {dispatch_id} was not found.")
        if payload.expected_version is not None and dsp.version != payload.expected_version:
            raise ConflictError("Dispatch changed concurrently.", error_code="VERSION_CONFLICT")

        allowed_targets = _DELIVERY_ALLOWED_TRANSITIONS.get(dsp.status, set())
        if payload.target_status not in allowed_targets:
            raise ConflictError(
                f"Dispatch {dsp.dispatch_number} cannot move from '{dsp.status}' to '{payload.target_status}'.",
                error_code="INVALID_STATE_TRANSITION",
            )

        if payload.target_status == "DELIVERY_EXCEPTION" and not (
            payload.exception_reason and payload.exception_reason.strip()
        ):
            raise DomainValidationError("An exception reason is required when marking DELIVERY_EXCEPTION.")

        prev_status = dsp.status
        now_utc = datetime.now(UTC)

        if payload.target_status == "IN_TRANSIT":
            dsp.in_transit_at = now_utc
        else:
            dsp.delivery_date = payload.delivery_date or datetime.now(IST).date()
            dsp.delivery_confirmed_by = actor.user_id
            dsp.delivery_confirmed_at = now_utc

            items_map = {di.id: di for di in dsp.items}
            if payload.items:
                for rec in payload.items:
                    di = items_map.get(rec.dispatch_item_id)
                    if di is None:
                        raise DomainValidationError(f"Dispatch item {rec.dispatch_item_id} not found on dispatch.")
                    if rec.received_qty_pkts > di.dispatched_qty_pkts:
                        raise DomainValidationError(
                            f"Received qty ({rec.received_qty_pkts}) cannot exceed dispatched qty ({di.dispatched_qty_pkts})."
                        )
                    di.received_qty_pkts = rec.received_qty_pkts
                    di.discrepancy_qty_pkts = di.dispatched_qty_pkts - rec.received_qty_pkts
                    di.discrepancy_remarks = rec.discrepancy_remarks.strip() if rec.discrepancy_remarks else None
            elif payload.target_status == "DELIVERED":
                for di in dsp.items:
                    di.received_qty_pkts = di.dispatched_qty_pkts
                    di.discrepancy_qty_pkts = 0

        if payload.remarks:
            dsp.delivery_remarks = payload.remarks.strip()
        if payload.exception_reason:
            dsp.delivery_exception_reason = payload.exception_reason.strip()
        dsp.status = payload.target_status
        dsp.version += 1

        reason_msg = (
            payload.exception_reason.strip()
            if payload.exception_reason
            else (payload.remarks.strip() if payload.remarks else f"Updated delivery status to {payload.target_status}")
        )
        db.add(
            DispatchStatusHistory(
                dispatch_id=dsp.id,
                from_status=prev_status,
                to_status=payload.target_status,
                changed_by=actor.user_id,
                reason=reason_msg,
            )
        )
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="DELIVERY_UPDATED",
            entity_schema="billing",
            entity_table="dispatches",
            entity_id=dsp.id,
            before_state={"status": prev_status},
            after_state={
                "invoice_id": dsp.invoice_id,
                "status": payload.target_status,
                "delivery_date": dsp.delivery_date.isoformat() if dsp.delivery_date else None,
                "total_received_pkts": sum(i.received_qty_pkts or 0 for i in dsp.items),
                "total_discrepancy_pkts": sum(i.discrepancy_qty_pkts for i in dsp.items),
            },
            reason=reason_msg,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_dispatch_detail_scoped(db, actor, dispatch_id)


def get_dispatch_detail_scoped(db: Session, actor: CurrentActor, dispatch_id: int) -> DispatchOut:
    dsp = billing_repo.get_dispatch(db, dispatch_id)
    if dsp is None:
        raise NotFoundError(f"Dispatch {dispatch_id} was not found.")
    order = orders_repo.get_order_by_id(db, dsp.sales_order_id)
    assert order is not None
    if actor.role_code == "SALESMAN":
        if order.salesman_id != actor.user_id:
            raise AuthorizationError("Salesmen can only inspect dispatches for their own orders.")
    else:
        _require_viewer(actor, "view dispatch details")

    inv = billing_repo.get_invoice(db, dsp.invoice_id)
    assert inv is not None
    cust_map = _customers_map(db, {dsp.customer_id})
    ps_map = sales_repo.get_pack_sizes_by_ids(
        db, [di.pack_size_id for di in dsp.items], include_inactive=True
    )
    uids = {dsp.created_by}
    for uid in (dsp.ready_by, dsp.dispatched_by, dsp.delivery_confirmed_by):
        if uid:
            uids.add(uid)
    for h in dsp.status_history:
        uids.add(h.changed_by)
    return _hydrate_dispatch(
        dsp,
        inv_map={inv.id: inv},
        ord_map={order.id: order},
        cust_map=cust_map,
        users=_users_map(db, uids),
        ps_map=ps_map,
    )


# ── Reporting ───────────────────────────────────────────────────────────────


def get_billing_reports_bundle(
    db: Session,
    actor: CurrentActor,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> BillingReportsBundleOut:
    _require_viewer(actor, "view billing and GST reports")
    invoices = billing_repo.list_invoices(db, date_from=date_from, date_to=date_to, limit=1000)
    non_draft = [i for i in invoices if i.doc_status != "DRAFT"]
    ord_map = _orders_map(db, {i.sales_order_id for i in non_draft})

    sales_register = [
        SalesInvoiceRegisterRow(
            invoice_id=inv.id,
            invoice_number=inv.invoice_number or inv.draft_ref,
            invoice_date=inv.invoice_date,
            financial_year=inv.financial_year,
            order_number=ord_map[inv.sales_order_id].order_number,
            customer_name=inv.customer_name,
            buyer_gstin=inv.buyer_gstin,
            place_of_supply_state_code=inv.place_of_supply_state_code,
            nature_of_supply=inv.nature_of_supply,
            supply_type=inv.supply_type,
            doc_status=inv.doc_status,
            dispatch_status=inv.dispatch_status,
            payment_status=inv.payment_status,
            taxable_total_paisa=int(inv.taxable_total_paisa),
            cgst_total_paisa=int(inv.cgst_total_paisa),
            sgst_total_paisa=int(inv.sgst_total_paisa),
            igst_total_paisa=int(inv.igst_total_paisa),
            round_off_paisa=int(inv.round_off_paisa),
            grand_total_paisa=int(inv.grand_total_paisa),
            credited_paisa=int(inv.credited_paisa),
            outstanding_paisa=int(inv.outstanding_paisa),
        )
        for inv in non_draft
    ]

    hsn_agg: dict[tuple[str, str, int], list[int]] = {}
    cust_agg: dict[int, dict[str, Any]] = {}
    prod_agg: dict[tuple[int, str], dict[str, Any]] = {}
    cust_map = _customers_map(db, {inv.customer_id for inv in non_draft})

    for inv in non_draft:
        c_ent = cust_agg.setdefault(
            inv.customer_id,
            {
                "customer_id": inv.customer_id,
                "customer_name": inv.customer_name,
                "customer_type": inv.customer_type,
                "buyer_gstin": inv.buyer_gstin,
                "state_code": inv.place_of_supply_state_code,
                "invoice_count": 0,
                "total_qty_pkts": 0,
                "taxable_paisa": 0,
                "gst_paisa": 0,
                "grand_total_paisa": 0,
                "credited_paisa": 0,
                "outstanding_paisa": 0,
            },
        )
        c_ent["invoice_count"] += 1
        c_ent["taxable_paisa"] += int(inv.taxable_total_paisa)
        c_ent["gst_paisa"] += int(inv.cgst_total_paisa) + int(inv.sgst_total_paisa) + int(inv.igst_total_paisa)
        c_ent["grand_total_paisa"] += int(inv.grand_total_paisa)
        c_ent["credited_paisa"] += int(inv.credited_paisa)
        c_ent["outstanding_paisa"] += int(inv.outstanding_paisa)

        for it in inv.items:
            c_ent["total_qty_pkts"] += it.qty_pkts
            h_key = (it.hsn_code, inv.supply_type, it.gst_rate_bps)
            h_vals = hsn_agg.setdefault(h_key, [0, 0, 0, 0])
            h_vals[0] += int(it.taxable_paisa)
            h_vals[1] += int(it.cgst_paisa)
            h_vals[2] += int(it.sgst_paisa)
            h_vals[3] += int(it.igst_paisa)

            p_key = (it.pack_size_id, it.hsn_code)
            p_ent = prod_agg.setdefault(
                p_key,
                {
                    "pack_size_id": it.pack_size_id,
                    "sku_code": it.sku_code,
                    "description": it.description,
                    "hsn_code": it.hsn_code,
                    "total_qty_pkts": 0,
                    "taxable_paisa": 0,
                    "cgst_paisa": 0,
                    "sgst_paisa": 0,
                    "igst_paisa": 0,
                    "line_total_paisa": 0,
                },
            )
            p_ent["total_qty_pkts"] += it.qty_pkts
            p_ent["taxable_paisa"] += int(it.taxable_paisa)
            p_ent["cgst_paisa"] += int(it.cgst_paisa)
            p_ent["sgst_paisa"] += int(it.sgst_paisa)
            p_ent["igst_paisa"] += int(it.igst_paisa)
            p_ent["line_total_paisa"] += int(it.line_total_paisa)

    all_cns = [
        cn for cn in billing_repo.list_credit_notes(db, date_from=date_from, date_to=date_to)
        if cn.status == "ISSUED"
    ]
    cn_outs = list_credit_notes_view(db, actor)
    if date_from or date_to:
        cn_ids = {c.id for c in all_cns}
        cn_outs = [c for c in cn_outs if c.id in cn_ids]

    gross_taxable = sum(int(i.taxable_total_paisa) for i in non_draft)
    gross_cgst = sum(int(i.cgst_total_paisa) for i in non_draft)
    gross_sgst = sum(int(i.sgst_total_paisa) for i in non_draft)
    gross_igst = sum(int(i.igst_total_paisa) for i in non_draft)
    cred_taxable = sum(int(c.taxable_reversed_paisa) for c in all_cns)
    cred_cgst = sum(int(c.cgst_reversed_paisa) for c in all_cns)
    cred_sgst = sum(int(c.sgst_reversed_paisa) for c in all_cns)
    cred_igst = sum(int(c.igst_reversed_paisa) for c in all_cns)

    gst_summary = GstSummaryReportOut(
        gross_taxable_paisa=gross_taxable,
        gross_cgst_paisa=gross_cgst,
        gross_sgst_paisa=gross_sgst,
        gross_igst_paisa=gross_igst,
        credited_taxable_paisa=cred_taxable,
        credited_cgst_paisa=cred_cgst,
        credited_sgst_paisa=cred_sgst,
        credited_igst_paisa=cred_igst,
        net_taxable_paisa=gross_taxable - cred_taxable,
        net_cgst_paisa=gross_cgst - cred_cgst,
        net_sgst_paisa=gross_sgst - cred_sgst,
        net_igst_paisa=gross_igst - cred_igst,
        disclaimer=(
            "Internal operational tax register derived directly from persisted Invoices and Credit Notes; "
            "not a statutory GST portal filing or GSTR return validation."
        ),
        hsn_rows=[
            GstHsnReportRow(
                hsn_code=hsn,
                supply_type=s_type,
                tax_rate_bps=bps,
                taxable_value_paisa=v[0],
                cgst_paisa=v[1],
                sgst_paisa=v[2],
                igst_paisa=v[3],
                total_tax_paisa=v[1] + v[2] + v[3],
            )
            for (hsn, s_type, bps), v in sorted(hsn_agg.items())
        ],
    )

    dispatches = billing_repo.list_dispatches(db, date_from=date_from, date_to=date_to, limit=1000)
    dsp_inv_rows = (
        db.execute(select(Invoice).where(Invoice.id.in_({d.invoice_id for d in dispatches}))).scalars().all()
        if dispatches
        else []
    )
    dsp_inv_map = {i.id: i for i in dsp_inv_rows}
    dsp_ord_map = _orders_map(db, {d.sales_order_id for d in dispatches})
    dsp_cust_map = _customers_map(db, {d.customer_id for d in dispatches})
    dispatch_register = [
        DispatchRegisterRow(
            dispatch_id=d.id,
            dispatch_number=d.dispatch_number,
            dispatch_date=d.dispatch_date,
            invoice_number=dsp_inv_map[d.invoice_id].invoice_number or dsp_inv_map[d.invoice_id].draft_ref,
            order_number=dsp_ord_map[d.sales_order_id].order_number,
            customer_name=dsp_cust_map[d.customer_id].name,
            status=d.status,
            transporter_name=d.transporter_name,
            vehicle_number=d.vehicle_number,
            total_dispatched_pkts=sum(i.dispatched_qty_pkts for i in d.items),
            total_received_pkts=sum(i.received_qty_pkts or 0 for i in d.items),
            delivery_date=d.delivery_date,
        )
        for d in dispatches
    ]

    _ = cust_map
    return BillingReportsBundleOut(
        sales_register=sales_register,
        gst_summary=gst_summary,
        credit_notes=cn_outs,
        dispatch_register=dispatch_register,
        customer_sales=[CustomerSalesSummaryRow(**v) for v in sorted(cust_agg.values(), key=lambda x: -x["grand_total_paisa"])],
        product_sales=[ProductSalesSummaryRow(**v) for v in sorted(prod_agg.values(), key=lambda x: -x["line_total_paisa"])],
        outstanding_invoices=[r for r in sales_register if r.outstanding_paisa > 0],
    )


def get_order_billing_dispatch_snapshot(db: Session, order_id: int) -> dict[str, Any]:
    """Read-only order-level invoice & dispatch tracking snapshot for Salesman and Admin views."""
    inv = db.execute(
        select(Invoice)
        .where(Invoice.sales_order_id == order_id)
        .order_by(Invoice.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if inv is None:
        return {
            "invoice_id": None,
            "invoice_number": None,
            "invoice_doc_status": None,
            "invoice_grand_total_paisa": None,
            "invoice_dispatch_status": None,
            "dispatches": [],
        }
    dispatches = billing_repo.list_dispatches(db, invoice_id=inv.id)
    return {
        "invoice_id": inv.id,
        "invoice_number": inv.invoice_number,
        "invoice_doc_status": inv.doc_status,
        "invoice_grand_total_paisa": int(inv.grand_total_paisa),
        "invoice_dispatch_status": inv.dispatch_status,
        "dispatches": [
            {
                "id": d.id,
                "dispatch_number": d.dispatch_number,
                "status": d.status,
                "dispatch_date": d.dispatch_date.isoformat(),
                "delivery_date": d.delivery_date.isoformat() if d.delivery_date else None,
                "vehicle_number": d.vehicle_number,
                "transporter_name": d.transporter_name,
                "total_dispatched_pkts": sum(i.dispatched_qty_pkts for i in d.items),
                "total_received_pkts": sum(i.received_qty_pkts or 0 for i in d.items),
                "delivery_remarks": d.delivery_remarks,
                "delivery_exception_reason": d.delivery_exception_reason,
            }
            for d in dispatches
        ],
    }
