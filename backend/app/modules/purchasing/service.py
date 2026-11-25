from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.modules.audit.service import record_audit_log
from app.modules.iam.models import User
from app.modules.iam.schemas import CurrentActor
from app.modules.inventory import service as inventory_service
from app.modules.inventory.models import Material
from app.modules.inventory.schemas import PurchaseReceiptReportRow
from app.modules.inventory.uom import convert_to_base_qty, unit_rate_to_base_cost
from app.modules.purchasing import repository as purchasing_repo
from app.modules.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
    Supplier,
)
from app.modules.purchasing.schemas import (
    GoodsReceiptCreateRequest,
    GoodsReceiptDetailResponse,
    GoodsReceiptItemResponse,
    GoodsReceiptSummaryResponse,
    PurchaseOrderCreateRequest,
    PurchaseOrderDetailResponse,
    PurchaseOrderItemResponse,
    PurchaseOrderSummaryResponse,
    SupplierCreateRequest,
    SupplierDetailResponse,
    SupplierResponse,
    SupplierUpdateRequest,
)

IST = ZoneInfo("Asia/Kolkata")


def _bps_tax(amount_paisa: int, gst_bps: int) -> int:
    return ((amount_paisa * gst_bps) + 5000) // 10000


def _qty_mul_rate_paisa(qty: Decimal, rate_paisa: int) -> int:
    return int((qty * Decimal(rate_paisa)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _require_admin(actor: CurrentActor, msg: str) -> None:
    if actor.role_code != "FACTORY_ADMIN":
        raise AuthorizationError(msg)


def _require_purchasing_operator(actor: CurrentActor, msg: str) -> None:
    if actor.role_code not in {"FACTORY_ADMIN", "PRODUCTION_SUPERVISOR"}:
        raise AuthorizationError(msg)


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------


def _to_supplier_response(
    sup: Supplier, stats: dict[str, int] | None = None
) -> SupplierResponse:
    s = stats or {"po_count": 0, "receipt_count": 0, "total_purchased_paisa": 0}
    return SupplierResponse(
        id=sup.id,
        code=sup.code,
        name=sup.name,
        contact_person=sup.contact_person,
        phone=sup.phone,
        email=sup.email,
        gstin=sup.gstin,
        state_name=sup.state_name,
        state_code=sup.state_code,
        address=sup.address,
        is_active=sup.is_active,
        po_count=s["po_count"],
        receipt_count=s["receipt_count"],
        total_purchased_paisa=s["total_purchased_paisa"],
        created_at=sup.created_at,
        updated_at=sup.updated_at,
    )


def list_suppliers(
    db: Session, *, active_only: bool = False, search: str | None = None
) -> list[SupplierResponse]:
    suppliers = purchasing_repo.list_suppliers(db, active_only=active_only, search=search)
    stats_map = purchasing_repo.get_supplier_stats_map(db, [s.id for s in suppliers])
    return [_to_supplier_response(s, stats_map.get(s.id)) for s in suppliers]


def get_supplier_detail(db: Session, supplier_id: int) -> SupplierDetailResponse:
    sup = purchasing_repo.get_supplier_by_id(db, supplier_id)
    if sup is None:
        raise NotFoundError(f"Supplier {supplier_id} was not found.")
    stats = purchasing_repo.get_supplier_stats_map(db, [sup.id]).get(sup.id)
    pos = purchasing_repo.list_purchase_orders(db, supplier_id=sup.id)
    prs = purchasing_repo.list_purchase_receipts(db, supplier_id=sup.id)
    base = _to_supplier_response(sup, stats)
    return SupplierDetailResponse(
        **base.model_dump(),
        purchase_orders=[_hydrate_po_summary(db, po) for po in pos],
        purchase_receipts=[_hydrate_receipt_summary(db, pr) for pr in prs],
    )


def create_supplier(
    db: Session, actor: CurrentActor, payload: SupplierCreateRequest
) -> SupplierResponse:
    _require_admin(actor, "Only Factory Admin can create suppliers.")
    existing = purchasing_repo.get_supplier_by_code(db, payload.code)
    if existing is not None:
        raise ConflictError(
            f"Supplier code '{payload.code}' already exists.",
            error_code="DUPLICATE_SUPPLIER_CODE",
        )
    sup = Supplier(
        code=payload.code,
        name=payload.name.strip(),
        contact_person=payload.contact_person.strip() if payload.contact_person else None,
        phone=payload.phone.strip() if payload.phone else None,
        email=payload.email.strip() if payload.email else None,
        gstin=payload.gstin,
        state_name=payload.state_name.strip(),
        state_code=payload.state_code,
        address=payload.address.strip(),
        is_active=payload.is_active,
    )
    db.add(sup)
    db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="SUPPLIER_CREATED",
        entity_schema="purchasing",
        entity_table="suppliers",
        entity_id=sup.id,
        after_state={"code": sup.code, "name": sup.name, "gstin": sup.gstin},
    )
    db.commit()
    db.refresh(sup)
    return _to_supplier_response(sup)


def update_supplier(
    db: Session, actor: CurrentActor, supplier_id: int, payload: SupplierUpdateRequest
) -> SupplierResponse:
    _require_admin(actor, "Only Factory Admin can update suppliers.")
    sup = purchasing_repo.get_supplier_by_id(db, supplier_id)
    if sup is None:
        raise NotFoundError(f"Supplier {supplier_id} was not found.")
    before = {
        "name": sup.name,
        "phone": sup.phone,
        "gstin": sup.gstin,
        "is_active": sup.is_active,
    }
    sup.name = payload.name.strip()
    sup.contact_person = payload.contact_person.strip() if payload.contact_person else None
    sup.phone = payload.phone.strip() if payload.phone else None
    sup.email = payload.email.strip() if payload.email else None
    sup.gstin = payload.gstin
    sup.state_name = payload.state_name.strip()
    sup.state_code = payload.state_code
    sup.address = payload.address.strip()
    sup.is_active = payload.is_active
    db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="SUPPLIER_UPDATED",
        entity_schema="purchasing",
        entity_table="suppliers",
        entity_id=sup.id,
        before_state=before,
        after_state={
            "name": sup.name,
            "phone": sup.phone,
            "gstin": sup.gstin,
            "is_active": sup.is_active,
        },
    )
    db.commit()
    db.refresh(sup)
    stats = purchasing_repo.get_supplier_stats_map(db, [sup.id]).get(sup.id)
    return _to_supplier_response(sup, stats)


# ---------------------------------------------------------------------------
# Purchase Orders
# ---------------------------------------------------------------------------


def _users_map_for_ids(db: Session, ids: set[int]) -> dict[int, User]:
    if not ids:
        return {}
    return {
        u.id: u for u in db.execute(select(User).where(User.id.in_(ids))).scalars().all()
    }


def _materials_map_for_ids(db: Session, ids: set[int]) -> dict[int, Material]:
    if not ids:
        return {}
    return {
        m.id: m
        for m in db.execute(select(Material).where(Material.id.in_(ids))).scalars().all()
    }


def _hydrate_po_summary(db: Session, po: PurchaseOrder) -> PurchaseOrderSummaryResponse:
    uids = {po.created_by}
    if po.approved_by:
        uids.add(po.approved_by)
    umap = _users_map_for_ids(db, uids)
    return PurchaseOrderSummaryResponse(
        id=po.id,
        po_number=po.po_number,
        supplier_id=po.supplier.id,
        supplier_code=po.supplier.code,
        supplier_name=po.supplier.name,
        order_date=po.order_date,
        expected_date=po.expected_date,
        status=po.status,
        subtotal_paisa=int(po.subtotal_paisa),
        tax_paisa=int(po.tax_paisa),
        total_paisa=int(po.total_paisa),
        notes=po.notes,
        rejection_reason=po.rejection_reason,
        created_by_name=umap[po.created_by].full_name,
        approved_by_name=umap[po.approved_by].full_name if po.approved_by else None,
        approved_at=po.approved_at,
        created_at=po.created_at,
        item_count=len(po.items),
    )


def _hydrate_po_detail(db: Session, po: PurchaseOrder) -> PurchaseOrderDetailResponse:
    summary = _hydrate_po_summary(db, po)
    mat_map = _materials_map_for_ids(db, {it.material_id for it in po.items})
    receipts = purchasing_repo.list_purchase_receipts(db, purchase_order_id=po.id)
    items = []
    for it in po.items:
        mat = mat_map[it.material_id]
        remaining = max(Decimal("0.000"), Decimal(it.ordered_qty_base) - Decimal(it.received_qty_base))
        items.append(
            PurchaseOrderItemResponse(
                id=it.id,
                material_id=mat.id,
                material_code=mat.code,
                material_name=mat.name,
                material_category=mat.material_category,
                base_uom=mat.base_uom,
                display_uom=mat.display_uom,
                entered_qty=Decimal(it.entered_qty),
                entered_uom=it.entered_uom,
                ordered_qty_base=Decimal(it.ordered_qty_base),
                received_qty_base=Decimal(it.received_qty_base),
                rejected_qty_base=Decimal(it.rejected_qty_base),
                remaining_qty_base=remaining.quantize(Decimal("0.001")),
                unit_rate_paisa=int(it.unit_rate_paisa),
                gst_rate_bps=it.gst_rate_bps,
                line_subtotal_paisa=int(it.line_subtotal_paisa),
                line_tax_paisa=int(it.line_tax_paisa),
                line_total_paisa=int(it.line_total_paisa),
            )
        )
    return PurchaseOrderDetailResponse(
        **summary.model_dump(),
        items=items,
        receipts=[_hydrate_receipt_summary(db, pr) for pr in receipts],
    )


def list_purchase_orders(
    db: Session,
    *,
    supplier_id: int | None = None,
    status: str | None = None,
    search: str | None = None,
) -> list[PurchaseOrderSummaryResponse]:
    pos = purchasing_repo.list_purchase_orders(
        db, supplier_id=supplier_id, status=status, search=search
    )
    return [_hydrate_po_summary(db, po) for po in pos]


def get_purchase_order_detail(db: Session, po_id: int) -> PurchaseOrderDetailResponse:
    po = purchasing_repo.get_purchase_order_by_id(db, po_id)
    if po is None:
        raise NotFoundError(f"Purchase order {po_id} was not found.")
    return _hydrate_po_detail(db, po)


def create_purchase_order(
    db: Session, actor: CurrentActor, payload: PurchaseOrderCreateRequest
) -> PurchaseOrderDetailResponse:
    _require_purchasing_operator(actor, "You do not have permission to create purchase orders.")

    sup = purchasing_repo.get_supplier_by_id(db, payload.supplier_id)
    if sup is None:
        raise NotFoundError(f"Supplier {payload.supplier_id} was not found.")
    if not sup.is_active:
        raise DomainValidationError(f"Supplier '{sup.name}' is inactive.")

    mat_ids = {it.material_id for it in payload.items}
    mat_map = _materials_map_for_ids(db, mat_ids)
    missing = [mid for mid in mat_ids if mid not in mat_map or not mat_map[mid].is_active]
    if missing:
        raise DomainValidationError(f"Unknown or inactive material IDs: {missing}")

    order_date = payload.order_date or datetime.now(IST).date()
    if payload.expected_date and payload.expected_date < order_date:
        raise DomainValidationError("Expected delivery date cannot precede order date.")

    resolved_lines: list[dict[str, Any]] = []
    subtotal_paisa = 0
    tax_paisa = 0

    for line in payload.items:
        mat = mat_map[line.material_id]
        qty_base, _mult, norm_uom = convert_to_base_qty(
            db,
            entered_qty=line.entered_qty,
            entered_uom=line.entered_uom,
            expected_dimension=mat.unit_dimension,
            expected_base_uom=mat.base_uom,
        )
        line_sub = _qty_mul_rate_paisa(line.entered_qty, line.unit_rate_paisa)
        line_tax = _bps_tax(line_sub, line.gst_rate_bps)
        line_tot = line_sub + line_tax
        subtotal_paisa += line_sub
        tax_paisa += line_tax
        resolved_lines.append(
            {
                "material_id": mat.id,
                "entered_qty": line.entered_qty.quantize(Decimal("0.001")),
                "entered_uom": norm_uom,
                "ordered_qty_base": qty_base,
                "unit_rate_paisa": line.unit_rate_paisa,
                "gst_rate_bps": line.gst_rate_bps,
                "line_subtotal_paisa": line_sub,
                "line_tax_paisa": line_tax,
                "line_total_paisa": line_tot,
            }
        )

    now_utc = datetime.now(UTC)
    initial_status = "SUBMITTED" if payload.submit_immediately else "DRAFT"

    try:
        po = PurchaseOrder(
            po_number=f"TMP-PO-{uuid4().hex[:8]}",
            supplier_id=sup.id,
            order_date=order_date,
            expected_date=payload.expected_date,
            status=initial_status,
            subtotal_paisa=subtotal_paisa,
            tax_paisa=tax_paisa,
            total_paisa=subtotal_paisa + tax_paisa,
            notes=payload.notes.strip() if payload.notes else None,
            created_by=actor.user_id,
            submitted_by=actor.user_id if payload.submit_immediately else None,
            submitted_at=now_utc if payload.submit_immediately else None,
        )
        db.add(po)
        db.flush()
        po.po_number = f"PO-{order_date.year}-{po.id:04d}"

        for rl in resolved_lines:
            db.add(PurchaseOrderItem(purchase_order_id=po.id, **rl))
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PO_CREATED",
            entity_schema="purchasing",
            entity_table="purchase_orders",
            entity_id=po.id,
            after_state={
                "po_number": po.po_number,
                "supplier_id": sup.id,
                "status": po.status,
                "total_paisa": po.total_paisa,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = purchasing_repo.get_purchase_order_by_id(db, po.id)
    assert refreshed is not None
    return _hydrate_po_detail(db, refreshed)


def submit_purchase_order(
    db: Session, actor: CurrentActor, po_id: int
) -> PurchaseOrderDetailResponse:
    _require_purchasing_operator(actor, "You do not have permission to submit purchase orders.")
    try:
        po = purchasing_repo.get_purchase_order_by_id(db, po_id, for_update=True)
        if po is None:
            raise NotFoundError(f"Purchase order {po_id} was not found.")
        if po.status != "DRAFT":
            raise ConflictError(
                f"Purchase order {po.po_number} in status '{po.status}' cannot be submitted.",
                error_code="INVALID_STATE_TRANSITION",
            )
        po.status = "SUBMITTED"
        po.submitted_by = actor.user_id
        po.submitted_at = datetime.now(UTC)
        po.version += 1
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PO_SUBMITTED",
            entity_schema="purchasing",
            entity_table="purchase_orders",
            entity_id=po.id,
            before_state={"status": "DRAFT"},
            after_state={"status": "SUBMITTED"},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    refreshed = purchasing_repo.get_purchase_order_by_id(db, po_id)
    assert refreshed is not None
    return _hydrate_po_detail(db, refreshed)


def approve_purchase_order(
    db: Session, actor: CurrentActor, po_id: int
) -> PurchaseOrderDetailResponse:
    _require_admin(actor, "Only Factory Admin can approve purchase orders.")
    try:
        po = purchasing_repo.get_purchase_order_by_id(db, po_id, for_update=True)
        if po is None:
            raise NotFoundError(f"Purchase order {po_id} was not found.")
        if po.status != "SUBMITTED":
            raise ConflictError(
                f"Purchase order {po.po_number} in status '{po.status}' cannot be approved (must be SUBMITTED).",
                error_code="INVALID_STATE_TRANSITION",
            )
        po.status = "APPROVED"
        po.approved_by = actor.user_id
        po.approved_at = datetime.now(UTC)
        po.version += 1
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PO_APPROVED",
            entity_schema="purchasing",
            entity_table="purchase_orders",
            entity_id=po.id,
            before_state={"status": "SUBMITTED"},
            after_state={"status": "APPROVED"},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    refreshed = purchasing_repo.get_purchase_order_by_id(db, po_id)
    assert refreshed is not None
    return _hydrate_po_detail(db, refreshed)


def reject_purchase_order(
    db: Session, actor: CurrentActor, po_id: int, reason: str
) -> PurchaseOrderDetailResponse:
    _require_admin(actor, "Only Factory Admin can reject purchase orders.")
    try:
        po = purchasing_repo.get_purchase_order_by_id(db, po_id, for_update=True)
        if po is None:
            raise NotFoundError(f"Purchase order {po_id} was not found.")
        if po.status not in {"DRAFT", "SUBMITTED"}:
            raise ConflictError(
                f"Purchase order {po.po_number} in status '{po.status}' cannot be rejected.",
                error_code="INVALID_STATE_TRANSITION",
            )
        prev = po.status
        po.status = "REJECTED"
        po.rejected_by = actor.user_id
        po.rejected_at = datetime.now(UTC)
        po.rejection_reason = reason.strip()
        po.version += 1
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PO_REJECTED",
            entity_schema="purchasing",
            entity_table="purchase_orders",
            entity_id=po.id,
            before_state={"status": prev},
            after_state={"status": "REJECTED", "rejection_reason": po.rejection_reason},
            reason=po.rejection_reason,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    refreshed = purchasing_repo.get_purchase_order_by_id(db, po_id)
    assert refreshed is not None
    return _hydrate_po_detail(db, refreshed)


def cancel_purchase_order(
    db: Session, actor: CurrentActor, po_id: int, reason: str
) -> PurchaseOrderDetailResponse:
    _require_admin(actor, "Only Factory Admin can cancel purchase orders.")
    try:
        po = purchasing_repo.get_purchase_order_by_id(db, po_id, for_update=True)
        if po is None:
            raise NotFoundError(f"Purchase order {po_id} was not found.")
        if po.status in {"RECEIVED", "CLOSED", "REJECTED", "CANCELLED"}:
            raise ConflictError(
                f"Purchase order {po.po_number} in status '{po.status}' cannot be cancelled.",
                error_code="INVALID_STATE_TRANSITION",
            )
        if any(Decimal(it.received_qty_base) > 0 for it in po.items):
            raise ConflictError(
                f"Purchase order {po.po_number} already has received goods posted and cannot be cancelled.",
                error_code="PO_HAS_RECEIPTS",
            )
        prev = po.status
        po.status = "CANCELLED"
        po.rejection_reason = reason.strip()
        po.version += 1
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PO_CANCELLED",
            entity_schema="purchasing",
            entity_table="purchase_orders",
            entity_id=po.id,
            before_state={"status": prev},
            after_state={"status": "CANCELLED"},
            reason=reason.strip(),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    refreshed = purchasing_repo.get_purchase_order_by_id(db, po_id)
    assert refreshed is not None
    return _hydrate_po_detail(db, refreshed)


# ---------------------------------------------------------------------------
# Goods Receipts
# ---------------------------------------------------------------------------


def _hydrate_receipt_summary(db: Session, pr: PurchaseReceipt) -> GoodsReceiptSummaryResponse:
    uids = {pr.received_by}
    if pr.verified_by:
        uids.add(pr.verified_by)
    if pr.posted_by:
        uids.add(pr.posted_by)
    umap = _users_map_for_ids(db, uids)

    po_number = None
    if pr.purchase_order_id:
        po = purchasing_repo.get_purchase_order_by_id(db, pr.purchase_order_id)
        if po:
            po_number = po.po_number

    return GoodsReceiptSummaryResponse(
        id=pr.id,
        receipt_number=pr.receipt_number,
        client_receipt_id=pr.client_receipt_id,
        purchase_order_id=pr.purchase_order_id,
        po_number=po_number,
        supplier_id=pr.supplier.id,
        supplier_code=pr.supplier.code,
        supplier_name=pr.supplier.name,
        supplier_bill_ref=pr.supplier_bill_ref,
        receipt_date=pr.receipt_date,
        status=pr.status,
        subtotal_paisa=int(pr.subtotal_paisa),
        input_gst_paisa=int(pr.input_gst_paisa),
        total_paisa=int(pr.total_paisa),
        discrepancy_notes=pr.discrepancy_notes,
        received_by_name=umap[pr.received_by].full_name,
        verified_by_name=umap[pr.verified_by].full_name if pr.verified_by else None,
        posted_by_name=umap[pr.posted_by].full_name if pr.posted_by else None,
        posted_at=pr.posted_at,
        created_at=pr.created_at,
    )


def _hydrate_receipt_detail(
    db: Session, pr: PurchaseReceipt, *, is_duplicate_replay: bool = False
) -> GoodsReceiptDetailResponse:
    summary = _hydrate_receipt_summary(db, pr)
    summary.is_duplicate_replay = is_duplicate_replay
    mat_map = _materials_map_for_ids(db, {it.material_id for it in pr.items})
    items = [
        GoodsReceiptItemResponse(
            id=it.id,
            purchase_order_item_id=it.purchase_order_item_id,
            material_id=it.material_id,
            material_code=mat_map[it.material_id].code,
            material_name=mat_map[it.material_id].name,
            base_uom=mat_map[it.material_id].base_uom,
            display_uom=mat_map[it.material_id].display_uom,
            entered_uom=it.entered_uom,
            received_qty_entered=Decimal(it.received_qty_entered),
            rejected_qty_entered=Decimal(it.rejected_qty_entered),
            accepted_qty_entered=Decimal(it.accepted_qty_entered),
            received_qty_base=Decimal(it.received_qty_base),
            rejected_qty_base=Decimal(it.rejected_qty_base),
            accepted_qty_base=Decimal(it.accepted_qty_base),
            entered_unit_rate_paisa=int(it.entered_unit_rate_paisa),
            gst_rate_bps=it.gst_rate_bps,
            unit_cost_paisa_per_base=Decimal(it.unit_cost_paisa_per_base),
            line_subtotal_paisa=int(it.line_subtotal_paisa),
            line_tax_paisa=int(it.line_tax_paisa),
            line_total_paisa=int(it.line_total_paisa),
            batch_code=it.batch_code,
            expiry_date=it.expiry_date,
            rejection_reason=it.rejection_reason,
        )
        for it in pr.items
    ]
    return GoodsReceiptDetailResponse(**summary.model_dump(), items=items)


def list_goods_receipts(
    db: Session,
    *,
    supplier_id: int | None = None,
    purchase_order_id: int | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
) -> list[GoodsReceiptSummaryResponse]:
    rows = purchasing_repo.list_purchase_receipts(
        db,
        supplier_id=supplier_id,
        purchase_order_id=purchase_order_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    return [_hydrate_receipt_summary(db, r) for r in rows]


def get_goods_receipt_detail(db: Session, receipt_id: int) -> GoodsReceiptDetailResponse:
    pr = purchasing_repo.get_receipt_by_id(db, receipt_id)
    if pr is None:
        raise NotFoundError(f"Goods receipt {receipt_id} was not found.")
    return _hydrate_receipt_detail(db, pr)


def create_goods_receipt(
    db: Session, actor: CurrentActor, payload: GoodsReceiptCreateRequest
) -> tuple[GoodsReceiptDetailResponse, bool]:
    _require_purchasing_operator(actor, "Only authorized inventory/purchasing staff can record goods receipts.")

    existing = purchasing_repo.get_receipt_by_client_id(db, payload.client_receipt_id)
    if existing is not None:
        return _hydrate_receipt_detail(db, existing, is_duplicate_replay=True), True

    po: PurchaseOrder | None = None
    po_items_by_id: dict[int, PurchaseOrderItem] = {}

    if payload.purchase_order_id is not None:
        po = purchasing_repo.get_purchase_order_by_id(db, payload.purchase_order_id, for_update=True)
        if po is None:
            raise NotFoundError(f"Purchase order {payload.purchase_order_id} was not found.")
        if po.status not in {"APPROVED", "PARTIALLY_RECEIVED"}:
            raise ConflictError(
                f"Purchase order {po.po_number} in status '{po.status}' cannot receive goods (must be APPROVED or PARTIALLY_RECEIVED).",
                error_code="INVALID_PO_STATUS",
            )
        supplier_id = po.supplier_id
        po_items_by_id = {it.id: it for it in po.items}
    else:
        if payload.supplier_id is None:
            raise DomainValidationError("supplier_id is required when creating a receipt without a PO.")
        supplier_id = payload.supplier_id

    sup = purchasing_repo.get_supplier_by_id(db, supplier_id)
    if sup is None or not sup.is_active:
        raise DomainValidationError("Supplier does not exist or is inactive.")

    mat_ids = {it.material_id for it in payload.items}
    mat_map = _materials_map_for_ids(db, mat_ids)
    missing = [mid for mid in mat_ids if mid not in mat_map or not mat_map[mid].is_active]
    if missing:
        raise DomainValidationError(f"Unknown or inactive material IDs: {missing}")

    receipt_date = payload.receipt_date or datetime.now(IST).date()
    resolved_lines: list[dict[str, Any]] = []
    subtotal_paisa = 0
    tax_paisa = 0

    for line in payload.items:
        mat = mat_map[line.material_id]
        po_item: PurchaseOrderItem | None = None

        if po is not None:
            if line.purchase_order_item_id is None:
                # Match cleanly by material if caller omitted PO line ID
                po_item = next((pi for pi in po.items if pi.material_id == line.material_id), None)
            else:
                po_item = po_items_by_id.get(line.purchase_order_item_id)
            if po_item is None or po_item.material_id != line.material_id:
                raise DomainValidationError(
                    f"Material {mat.code} does not match an ordered line on PO {po.po_number}."
                )

        rec_base, mult, norm_uom = convert_to_base_qty(
            db,
            entered_qty=line.received_qty_entered,
            entered_uom=line.entered_uom,
            expected_dimension=mat.unit_dimension,
            expected_base_uom=mat.base_uom,
        )
        rej_base, _m2, _u2 = convert_to_base_qty(
            db,
            entered_qty=line.rejected_qty_entered,
            entered_uom=norm_uom,
            expected_dimension=mat.unit_dimension,
            expected_base_uom=mat.base_uom,
        )
        acc_entered = (line.received_qty_entered - line.rejected_qty_entered).quantize(Decimal("0.001"))
        acc_base = (rec_base - rej_base).quantize(Decimal("0.001"))

        # Enforce remaining PO quantity guard against unapproved excess delivery
        if po_item is not None and acc_base > 0:
            remaining = Decimal(po_item.ordered_qty_base) - Decimal(po_item.received_qty_base)
            if acc_base > remaining and not line.allow_excess:
                raise ConflictError(
                    f"Excess delivery detected for {mat.name}: accepted {acc_base} {mat.base_uom} exceeds remaining PO qty {remaining} {mat.base_uom}. Set allow_excess=true with discrepancy notes to override.",
                    error_code="EXCESS_RECEIPT_QUANTITY",
                )

        rate = (
            line.unit_rate_paisa
            if line.unit_rate_paisa is not None
            else (int(po_item.unit_rate_paisa) if po_item else 0)
        )
        gst_bps = (
            line.gst_rate_bps
            if line.gst_rate_bps is not None
            else (int(po_item.gst_rate_bps) if po_item else 0)
        )
        unit_cost_base = unit_rate_to_base_cost(rate, mult)
        line_sub = _qty_mul_rate_paisa(acc_entered, rate)
        line_tax = _bps_tax(line_sub, gst_bps)
        line_tot = line_sub + line_tax

        subtotal_paisa += line_sub
        tax_paisa += line_tax

        resolved_lines.append(
            {
                "purchase_order_item_id": po_item.id if po_item else None,
                "material_id": mat.id,
                "entered_uom": norm_uom,
                "received_qty_entered": line.received_qty_entered.quantize(Decimal("0.001")),
                "rejected_qty_entered": line.rejected_qty_entered.quantize(Decimal("0.001")),
                "accepted_qty_entered": acc_entered,
                "received_qty_base": rec_base,
                "rejected_qty_base": rej_base,
                "accepted_qty_base": acc_base,
                "entered_unit_rate_paisa": rate,
                "gst_rate_bps": gst_bps,
                "unit_cost_paisa_per_base": unit_cost_base,
                "line_subtotal_paisa": line_sub,
                "line_tax_paisa": line_tax,
                "line_total_paisa": line_tot,
                "batch_code": line.batch_code.strip() if line.batch_code else None,
                "expiry_date": line.expiry_date,
                "rejection_reason": line.rejection_reason.strip() if line.rejection_reason else None,
            }
        )

    now_utc = datetime.now(UTC)
    initial_status = "SUBMITTED" if payload.submit_immediately else "DRAFT"

    try:
        pr = PurchaseReceipt(
            receipt_number=f"TMP-GRN-{uuid4().hex[:8]}",
            client_receipt_id=payload.client_receipt_id,
            purchase_order_id=po.id if po else None,
            supplier_id=sup.id,
            supplier_bill_ref=payload.supplier_bill_ref.strip() if payload.supplier_bill_ref else None,
            receipt_date=receipt_date,
            status=initial_status,
            subtotal_paisa=subtotal_paisa,
            input_gst_paisa=tax_paisa,
            total_paisa=subtotal_paisa + tax_paisa,
            discrepancy_notes=payload.discrepancy_notes.strip() if payload.discrepancy_notes else None,
            received_by=actor.user_id,
            submitted_by=actor.user_id if payload.submit_immediately else None,
            submitted_at=now_utc if payload.submit_immediately else None,
        )
        db.add(pr)
        db.flush()
        pr.receipt_number = f"GRN-{receipt_date.year}-{pr.id:04d}"

        for rl in resolved_lines:
            db.add(PurchaseReceiptItem(purchase_receipt_id=pr.id, **rl))
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="RECEIPT_CREATED",
            entity_schema="purchasing",
            entity_table="purchase_receipts",
            entity_id=pr.id,
            after_state={
                "receipt_number": pr.receipt_number,
                "purchase_order_id": pr.purchase_order_id,
                "status": pr.status,
                "total_paisa": pr.total_paisa,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = purchasing_repo.get_receipt_by_id(db, pr.id)
    assert refreshed is not None
    return _hydrate_receipt_detail(db, refreshed), False


def submit_goods_receipt(
    db: Session, actor: CurrentActor, receipt_id: int
) -> GoodsReceiptDetailResponse:
    _require_purchasing_operator(actor, "You do not have permission to submit goods receipts.")
    try:
        pr = purchasing_repo.get_receipt_by_id(db, receipt_id, for_update=True)
        if pr is None:
            raise NotFoundError(f"Goods receipt {receipt_id} was not found.")
        if pr.status != "DRAFT":
            raise ConflictError(
                f"Goods receipt {pr.receipt_number} in status '{pr.status}' cannot be submitted.",
                error_code="INVALID_STATE_TRANSITION",
            )
        pr.status = "SUBMITTED"
        pr.submitted_by = actor.user_id
        pr.submitted_at = datetime.now(UTC)
        pr.version += 1
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="RECEIPT_SUBMITTED",
            entity_schema="purchasing",
            entity_table="purchase_receipts",
            entity_id=pr.id,
            before_state={"status": "DRAFT"},
            after_state={"status": "SUBMITTED"},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    refreshed = purchasing_repo.get_receipt_by_id(db, receipt_id)
    assert refreshed is not None
    return _hydrate_receipt_detail(db, refreshed)


def verify_goods_receipt(
    db: Session, actor: CurrentActor, receipt_id: int
) -> GoodsReceiptDetailResponse:
    _require_purchasing_operator(actor, "Only authorized inventory/admin staff can verify receipts.")
    try:
        pr = purchasing_repo.get_receipt_by_id(db, receipt_id, for_update=True)
        if pr is None:
            raise NotFoundError(f"Goods receipt {receipt_id} was not found.")
        if pr.status != "SUBMITTED":
            raise ConflictError(
                f"Goods receipt {pr.receipt_number} in status '{pr.status}' cannot be verified (must be SUBMITTED).",
                error_code="INVALID_STATE_TRANSITION",
            )
        pr.status = "VERIFIED"
        pr.verified_by = actor.user_id
        pr.verified_at = datetime.now(UTC)
        pr.version += 1
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="RECEIPT_VERIFIED",
            entity_schema="purchasing",
            entity_table="purchase_receipts",
            entity_id=pr.id,
            before_state={"status": "SUBMITTED"},
            after_state={"status": "VERIFIED"},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    refreshed = purchasing_repo.get_receipt_by_id(db, receipt_id)
    assert refreshed is not None
    return _hydrate_receipt_detail(db, refreshed)


def post_goods_receipt(
    db: Session, actor: CurrentActor, receipt_id: int
) -> GoodsReceiptDetailResponse:
    """Atomically post VERIFIED goods receipt accepted quantities into inventory ledger & update PO."""
    _require_purchasing_operator(actor, "Only authorized inventory/admin staff can post receipts.")
    try:
        pr = purchasing_repo.get_receipt_by_id(db, receipt_id, for_update=True)
        if pr is None:
            raise NotFoundError(f"Goods receipt {receipt_id} was not found.")
        if pr.status == "POSTED":
            raise ConflictError(
                f"Goods receipt {pr.receipt_number} is already POSTED; duplicate posting is prohibited.",
                error_code="DUPLICATE_POST",
            )
        if pr.status != "VERIFIED":
            raise ConflictError(
                f"Goods receipt {pr.receipt_number} must be VERIFIED before posting to inventory (current: {pr.status}).",
                error_code="INVALID_STATE_TRANSITION",
            )

        po: PurchaseOrder | None = None
        po_items_map: dict[int, PurchaseOrderItem] = {}
        if pr.purchase_order_id is not None:
            po = purchasing_repo.get_purchase_order_by_id(db, pr.purchase_order_id, for_update=True)
            if po is None or po.status not in {"APPROVED", "PARTIALLY_RECEIVED"}:
                raise ConflictError("Linked Purchase Order is not open for receiving.")
            po_items_map = {it.id: it for it in po.items}

        mat_map = _materials_map_for_ids(db, {it.material_id for it in pr.items})

        # Post ONLY accepted quantities into InventoryMovement & CostLot
        movements = inventory_service.post_purchase_receipt_to_ledger(
            db,
            receipt_id=pr.id,
            receipt_number=pr.receipt_number,
            receipt_items=pr.items,
            materials_map=mat_map,
            actor_user_id=actor.user_id,
        )

        # Update PO received/rejected tracking
        if po is not None:
            for r_item in pr.items:
                if r_item.purchase_order_item_id and r_item.purchase_order_item_id in po_items_map:
                    p_item = po_items_map[r_item.purchase_order_item_id]
                    p_item.received_qty_base = (
                        Decimal(p_item.received_qty_base) + Decimal(r_item.accepted_qty_base)
                    ).quantize(Decimal("0.001"))
                    p_item.rejected_qty_base = (
                        Decimal(p_item.rejected_qty_base) + Decimal(r_item.rejected_qty_base)
                    ).quantize(Decimal("0.001"))

            all_done = all(
                Decimal(pi.received_qty_base) >= Decimal(pi.ordered_qty_base) for pi in po.items
            )
            any_rec = any(Decimal(pi.received_qty_base) > 0 for pi in po.items)
            if all_done:
                po.status = "RECEIVED"
            elif any_rec:
                po.status = "PARTIALLY_RECEIVED"
            po.version += 1

        pr.status = "POSTED"
        pr.posted_by = actor.user_id
        pr.posted_at = datetime.now(UTC)
        pr.version += 1
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="RECEIPT_POSTED",
            entity_schema="purchasing",
            entity_table="purchase_receipts",
            entity_id=pr.id,
            before_state={"status": "VERIFIED"},
            after_state={
                "status": "POSTED",
                "receipt_number": pr.receipt_number,
                "movements_posted": len(movements),
                "po_status": po.status if po else None,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = purchasing_repo.get_receipt_by_id(db, receipt_id)
    assert refreshed is not None
    return _hydrate_receipt_detail(db, refreshed)


def list_purchase_receipt_report_rows(
    db: Session, *, date_from: date | None = None, date_to: date | None = None
) -> list[PurchaseReceiptReportRow]:
    receipts = purchasing_repo.list_purchase_receipts(
        db, status="POSTED", date_from=date_from, date_to=date_to
    )
    if not receipts:
        return []
    mat_ids = {it.material_id for pr in receipts for it in pr.items}
    mat_map = _materials_map_for_ids(db, mat_ids)
    po_ids = {pr.purchase_order_id for pr in receipts if pr.purchase_order_id}
    po_map = (
        {
            po.id: po
            for po in db.execute(select(PurchaseOrder).where(PurchaseOrder.id.in_(po_ids))).scalars().all()
        }
        if po_ids
        else {}
    )

    rows: list[PurchaseReceiptReportRow] = []
    for pr in receipts:
        po_num = po_map[pr.purchase_order_id].po_number if pr.purchase_order_id in po_map else None
        for it in pr.items:
            mat = mat_map[it.material_id]
            rows.append(
                PurchaseReceiptReportRow(
                    receipt_id=pr.id,
                    receipt_number=pr.receipt_number,
                    receipt_date=pr.receipt_date,
                    po_number=po_num,
                    supplier_code=pr.supplier.code,
                    supplier_name=pr.supplier.name,
                    material_code=mat.code,
                    material_name=mat.name,
                    entered_uom=it.entered_uom,
                    received_qty_entered=Decimal(it.received_qty_entered),
                    rejected_qty_entered=Decimal(it.rejected_qty_entered),
                    accepted_qty_entered=Decimal(it.accepted_qty_entered),
                    accepted_qty_base=Decimal(it.accepted_qty_base),
                    base_uom=mat.base_uom,
                    entered_unit_rate_paisa=int(it.entered_unit_rate_paisa),
                    line_total_paisa=int(it.line_total_paisa),
                    batch_code=it.batch_code,
                    status=pr.status,
                )
            )
    return rows
