import math
from datetime import UTC, date, datetime
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
from app.modules.audit.service import list_order_audit_logs, record_audit_log
from app.modules.iam import repository as iam_repo
from app.modules.iam.models import User
from app.modules.iam.schemas import CurrentActor
from app.modules.inventory import service as inventory_service
from app.modules.orders import repository as orders_repo
from app.modules.orders.models import (
    SalesOrder,
    SalesOrderApproval,
    SalesOrderItem,
    SalesOrderStatusHistory,
)
from app.modules.orders.schemas import (
    AdminApproveRequest,
    AdminModifyOrderRequest,
    AdminOrdersSummaryResponse,
    AdminReasonRequest,
    AdminReviewHoldRequest,
    CreateOrderRequest,
    OrderApprovalRecord,
    OrderAuditEntry,
    OrderDetailResponse,
    OrderItemDetail,
    OrderReasonRequest,
    OrderSummaryResponse,
    PaginatedOrdersResponse,
    SalesmanResubmitRequest,
    StatusHistoryEntry,
    StockReservationRecord,
    TaxEstimateBreakdown,
)
from app.modules.orders.state_machine import (
    ADMIN_EDITABLE_STATUSES,
    PENDING_VERIFICATION_STATUSES,
    SALESMAN_CANCELLABLE_STATUSES,
    OrderStatus,
    assert_transition_allowed,
)
from app.modules.sales import repository as sales_repo
from app.modules.sales import service as sales_service
from app.modules.sales.models import Customer, PackSize

IST = ZoneInfo("Asia/Kolkata")
_RESERVED_OR_FULFILLED_STATUSES = {
    OrderStatus.APPROVED,
    OrderStatus.INVOICED,
    OrderStatus.PARTIALLY_DISPATCHED,
    OrderStatus.DISPATCHED,
}


def _round_half_up_bps(amount_paisa: int, rate_bps: int) -> int:
    return ((amount_paisa * rate_bps) + 5000) // 10000


def _effective_item_qty(item: SalesOrderItem) -> int:
    return item.approved_qty_pkts if item.approved_qty_pkts is not None else item.ordered_qty_pkts


def _compute_tax_estimate(
    *,
    factory_state_code: str,
    place_of_supply_state_code: str,
    lines: list[tuple[int, int]],
) -> TaxEstimateBreakdown:
    """Compute exact integer-paisa CGST+SGST or IGST estimate without floats."""
    supply_type = (
        "INTRA_STATE" if place_of_supply_state_code == factory_state_code else "INTER_STATE"
    )
    taxable_total = 0
    cgst_total = 0
    sgst_total = 0
    igst_total = 0

    for line_taxable, gst_bps in lines:
        taxable_total += line_taxable
        if supply_type == "INTRA_STATE":
            half_bps = gst_bps // 2
            cgst = _round_half_up_bps(line_taxable, half_bps)
            sgst = cgst
            cgst_total += cgst
            sgst_total += sgst
        else:
            igst_total += _round_half_up_bps(line_taxable, gst_bps)

    return TaxEstimateBreakdown(
        supply_type=supply_type,
        factory_state_code=factory_state_code,
        place_of_supply_state_code=place_of_supply_state_code,
        taxable_total_paisa=taxable_total,
        cgst_total_paisa=cgst_total,
        sgst_total_paisa=sgst_total,
        igst_total_paisa=igst_total,
        grand_total_paisa=taxable_total + cgst_total + sgst_total + igst_total,
    )


def _compute_stock_snapshot_for_items(
    db: Session,
    items: list[tuple[PackSize, int]],
) -> tuple[dict[str, dict[str, int]], int, int, int]:
    """Read-only per-SKU stock snapshot returning (snapshot, ordered_total, avail_total, shortage_total)."""
    sku_ids = [ps.id for ps, _ in items]
    availability = inventory_service.get_pack_size_availability_map(db, sku_ids)
    snapshot: dict[str, dict[str, int]] = {}
    ordered_total = 0
    available_total = 0
    shortage_total = 0

    for ps, req_qty in items:
        stock = availability.get(
            ps.id, {"on_hand_pkts": 0, "reserved_pkts": 0, "available_pkts": 0}
        )
        line_shortage = max(0, req_qty - stock["available_pkts"])
        ordered_total += req_qty
        available_total += stock["available_pkts"]
        shortage_total += line_shortage
        snapshot[ps.sku_code] = {
            "ordered_pkts": req_qty,
            "on_hand_pkts": stock["on_hand_pkts"],
            "reserved_pkts": stock["reserved_pkts"],
            "available_pkts": stock["available_pkts"],
            "shortage_pkts": line_shortage,
        }

    return snapshot, ordered_total, available_total, shortage_total


def _snapshot_from_order_items(
    db: Session, order: SalesOrder
) -> tuple[dict[str, dict[str, int]], int, int, int]:
    sku_ids = [i.pack_size_id for i in order.items]
    ps_map = sales_repo.get_pack_sizes_by_ids(db, sku_ids, include_inactive=True)
    pairs = [(ps_map[i.pack_size_id], _effective_item_qty(i)) for i in order.items]
    return _compute_stock_snapshot_for_items(db, pairs)


def _check_expected_version(order: SalesOrder, expected_version: int | None) -> None:
    if expected_version is not None and order.version != expected_version:
        raise ConflictError(
            f"Order {order.order_number} was modified concurrently (expected v{expected_version}, found v{order.version}). Refresh and retry.",
            error_code="VERSION_CONFLICT",
            details={"expected_version": expected_version, "current_version": order.version},
        )


def _require_factory_admin(actor: CurrentActor) -> None:
    if actor.role_code != "FACTORY_ADMIN":
        raise AuthorizationError("Only Factory Admin can verify, modify, approve, or reject orders.")


def _hydrate_order_summary(
    order: SalesOrder,
    *,
    customers_map: dict[int, Customer],
    users_map: dict[int, User],
    pack_sizes_map: dict[int, PackSize],
    factory_state_code: str,
) -> OrderSummaryResponse:
    customer = customers_map[order.customer_id]
    salesman = users_map[order.salesman_id]
    ordered_total_packets = sum(item.ordered_qty_pkts for item in order.items)
    effective_total_packets = sum(_effective_item_qty(item) for item in order.items)
    tax_lines = [
        (int(item.line_taxable_paisa), pack_sizes_map[item.pack_size_id].product.gst_rate_bps)
        for item in order.items
    ]
    tax = _compute_tax_estimate(
        factory_state_code=factory_state_code,
        place_of_supply_state_code=order.place_of_supply_state_code,
        lines=tax_lines,
    )
    return OrderSummaryResponse(
        id=order.id,
        order_number=order.order_number,
        client_order_id=order.client_order_id,
        order_date=order.order_date,
        status=order.status,
        has_shortage=order.has_shortage,
        customer_id=customer.id,
        customer_code=customer.code,
        customer_name=customer.name,
        customer_type=customer.customer_type,
        place_of_supply_state_code=order.place_of_supply_state_code,
        place_of_supply_state_name=customer.primary_state_name,
        salesman_id=salesman.id,
        salesman_name=salesman.full_name,
        total_packets=effective_total_packets,
        ordered_total_packets=ordered_total_packets,
        taxable_total_paisa=tax.taxable_total_paisa,
        estimated_grand_total_paisa=tax.grand_total_paisa,
        admin_remarks=order.admin_remarks,
        rejection_reason=order.rejection_reason,
        cancellation_reason=order.cancellation_reason,
        submitted_at=order.submitted_at,
        approved_at=order.approved_at,
        created_at=order.created_at,
    )


def _build_order_detail(
    db: Session,
    order: SalesOrder,
    *,
    actor_role: str | None = None,
    is_duplicate_replay: bool = False,
) -> OrderDetailResponse:
    company = iam_repo.get_company_profile(db)
    factory_state = company.state_code if company else "33"

    customer = sales_repo.get_customer_by_id(db, order.customer_id)
    assert customer is not None

    include_audit = actor_role != "SALESMAN"
    reservations = inventory_service.list_reservations_for_order(db, order.id) if include_audit else []
    audit_logs = list_order_audit_logs(db, order.id) if include_audit else []

    user_ids = {order.salesman_id}
    if order.approved_by:
        user_ids.add(order.approved_by)
    if order.rejected_by:
        user_ids.add(order.rejected_by)
    if order.cancelled_by:
        user_ids.add(order.cancelled_by)
    user_ids.update(h.changed_by for h in order.status_history)
    user_ids.update(a.reviewed_by for a in order.approvals)
    for res in reservations:
        user_ids.add(res.reserved_by)
        if res.released_by:
            user_ids.add(res.released_by)
    for log in audit_logs:
        if log.actor_user_id:
            user_ids.add(log.actor_user_id)

    users = db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
    users_map = {u.id: u for u in users}
    salesman = users_map[order.salesman_id]
    salesman_profile = sales_repo.get_salesman_profile_by_user_id(db, salesman.id)

    sku_ids = [item.pack_size_id for item in order.items]
    pack_sizes_map = sales_repo.get_pack_sizes_by_ids(db, sku_ids, include_inactive=True)

    availability = inventory_service.get_pack_size_availability_map(db, sku_ids)
    item_details: list[OrderItemDetail] = []
    tax_lines: list[tuple[int, int]] = []
    is_reserved_or_later = order.status in _RESERVED_OR_FULFILLED_STATUSES

    for item in order.items:
        ps = pack_sizes_map[item.pack_size_id]
        eff_qty = _effective_item_qty(item)
        stock = availability.get(
            ps.id, {"on_hand_pkts": 0, "reserved_pkts": 0, "available_pkts": 0}
        )
        shortage = 0 if is_reserved_or_later else max(0, eff_qty - stock["available_pkts"])
        line_taxable = int(item.line_taxable_paisa)
        tax_lines.append((line_taxable, ps.product.gst_rate_bps))
        item_details.append(
            OrderItemDetail(
                id=item.id,
                pack_size_id=ps.id,
                sku_code=ps.sku_code,
                display_name=ps.display_name,
                hsn_code=ps.product.hsn_code,
                gst_rate_bps=ps.product.gst_rate_bps,
                packets_per_carton=ps.packets_per_carton,
                ordered_qty_pkts=item.ordered_qty_pkts,
                approved_qty_pkts=item.approved_qty_pkts,
                effective_qty_pkts=eff_qty,
                original_unit_price_paisa=int(item.original_unit_price_paisa),
                unit_price_paisa=int(item.unit_price_paisa),
                is_qty_modified=(
                    item.approved_qty_pkts is not None and item.approved_qty_pkts != item.ordered_qty_pkts
                ),
                is_price_modified=(int(item.unit_price_paisa) != int(item.original_unit_price_paisa)),
                line_taxable_paisa=line_taxable,
                live_on_hand_pkts=stock["on_hand_pkts"],
                live_reserved_pkts=stock["reserved_pkts"],
                live_available_pkts=stock["available_pkts"],
                shortage_pkts=shortage,
            )
        )

    tax_estimate = _compute_tax_estimate(
        factory_state_code=factory_state,
        place_of_supply_state_code=order.place_of_supply_state_code,
        lines=tax_lines,
    )
    history = [
        StatusHistoryEntry(
            id=h.id,
            from_status=h.from_status,
            to_status=h.to_status,
            changed_by_name=users_map[h.changed_by].full_name,
            reason=h.reason,
            changed_at=h.changed_at,
        )
        for h in sorted(order.status_history, key=lambda x: (x.changed_at, x.id))
    ]
    approvals = [
        OrderApprovalRecord(
            id=a.id,
            decision=a.decision,
            reviewed_by_name=users_map[a.reviewed_by].full_name,
            ordered_total_pkts=a.ordered_total_pkts,
            available_total_pkts=a.available_total_pkts,
            shortage_pkts=a.shortage_pkts,
            stock_snapshot=a.stock_snapshot,
            remarks=a.remarks,
            decided_at=a.decided_at,
        )
        for a in sorted(order.approvals, key=lambda x: (x.decided_at, x.id))
    ]
    reservation_records = [
        StockReservationRecord(
            id=r.id,
            sales_order_item_id=r.sales_order_item_id,
            pack_size_id=r.pack_size_id,
            sku_code=pack_sizes_map[r.pack_size_id].sku_code,
            reserved_qty_pkts=r.reserved_qty_pkts,
            status=r.status,
            reserved_by_name=users_map[r.reserved_by].full_name,
            reserved_at=r.reserved_at,
            released_by_name=users_map[r.released_by].full_name if r.released_by else None,
            released_at=r.released_at,
            release_reason=r.release_reason,
        )
        for r in reservations
    ]
    audit_entries = [
        OrderAuditEntry(
            id=log.id,
            actor_user_id=log.actor_user_id,
            actor_name=users_map[log.actor_user_id].full_name if log.actor_user_id else "System",
            actor_role=log.actor_role,
            action=log.action,
            entity_table=log.entity_table,
            entity_id=log.entity_id,
            before_state=log.before_state,
            after_state=log.after_state,
            reason=log.reason,
            occurred_at=log.occurred_at,
        )
        for log in audit_logs
    ]

    return OrderDetailResponse(
        id=order.id,
        order_number=order.order_number,
        client_order_id=order.client_order_id,
        order_date=order.order_date,
        status=order.status,
        has_shortage=order.has_shortage,
        version=order.version,
        customer_id=customer.id,
        customer_code=customer.code,
        customer_name=customer.name,
        customer_type=customer.customer_type,
        customer_gstin=customer.gstin,
        customer_phone=customer.phone,
        place_of_supply_state_code=order.place_of_supply_state_code,
        place_of_supply_state_name=customer.primary_state_name,
        salesman_id=salesman.id,
        salesman_name=salesman.full_name,
        salesman_employee_code=salesman_profile.employee_code if salesman_profile else None,
        salesman_territory=salesman_profile.territory if salesman_profile else None,
        notes=order.notes,
        admin_remarks=order.admin_remarks,
        approved_by_name=users_map[order.approved_by].full_name if order.approved_by else None,
        approved_at=order.approved_at,
        rejected_by_name=users_map[order.rejected_by].full_name if order.rejected_by else None,
        rejected_at=order.rejected_at,
        rejection_reason=order.rejection_reason,
        cancelled_by_name=users_map[order.cancelled_by].full_name if order.cancelled_by else None,
        cancelled_at=order.cancelled_at,
        cancellation_reason=order.cancellation_reason,
        is_duplicate_replay=is_duplicate_replay,
        total_packets=sum(_effective_item_qty(i) for i in order.items),
        ordered_total_packets=sum(i.ordered_qty_pkts for i in order.items),
        taxable_total_paisa=tax_estimate.taxable_total_paisa,
        estimated_grand_total_paisa=tax_estimate.grand_total_paisa,
        submitted_at=order.submitted_at,
        created_at=order.created_at,
        tax_estimate=tax_estimate,
        items=item_details,
        status_history=history,
        approvals=approvals,
        reservations=reservation_records,
        audit_trail=audit_entries,
    )


def submit_sales_order(
    db: Session, actor: CurrentActor, payload: CreateOrderRequest
) -> tuple[OrderDetailResponse, bool]:
    """Create a salesman order transactionally without deducting/reserving FG inventory."""
    if actor.role_code != "SALESMAN":
        raise AuthorizationError("Only field salesmen can submit orders through this workflow.")

    existing = orders_repo.get_by_salesman_and_client_order_id(
        db, actor.user_id, payload.client_order_id
    )
    if existing is not None:
        return (
            _build_order_detail(
                db, existing, actor_role=actor.role_code, is_duplicate_replay=True
            ),
            True,
        )

    customer = sales_service.validate_customer_access(db, actor, payload.customer_id)
    shipping = next(
        (a for a in customer.addresses if a.address_type == "SHIPPING" and a.is_default), None
    )
    if shipping is None and customer.addresses:
        shipping = customer.addresses[0]
    pos_state_code = shipping.state_code if shipping else customer.primary_state_code

    sku_ids = [item.pack_size_id for item in payload.items]
    pack_sizes = sales_repo.get_pack_sizes_by_ids(db, sku_ids)
    missing_skus = [sid for sid in sku_ids if sid not in pack_sizes]
    if missing_skus:
        raise DomainValidationError(
            f"Inactive or unknown product pack size IDs: {missing_skus}",
            details={"missing_pack_size_ids": missing_skus},
        )

    now_utc = datetime.now(UTC)
    today_ist = datetime.now(IST).date()

    stock_snapshot, ordered_total_pkts, available_total_pkts, shortage_total_pkts = (
        _compute_stock_snapshot_for_items(
            db, [(pack_sizes[line.pack_size_id], line.ordered_qty_pkts) for line in payload.items]
        )
    )
    resolved_items: list[tuple[PackSize, int, int]] = []
    for line in payload.items:
        ps = pack_sizes[line.pack_size_id]
        unit_price_paisa = sales_service.resolve_authoritative_price_paisa(
            db,
            pack_size=ps,
            customer_id=customer.id,
            qty_pkts=line.ordered_qty_pkts,
            as_of=today_ist,
        )
        resolved_items.append((ps, line.ordered_qty_pkts, unit_price_paisa))

    has_shortage = shortage_total_pkts > 0

    try:
        temp_number = f"TMP-{uuid4().hex[:12]}"
        order = SalesOrder(
            order_number=temp_number,
            client_order_id=payload.client_order_id,
            salesman_id=actor.user_id,
            customer_id=customer.id,
            shipping_address_id=shipping.id if shipping else None,
            place_of_supply_state_code=pos_state_code,
            order_date=today_ist,
            status=OrderStatus.SUBMITTED,
            has_shortage=has_shortage,
            notes=payload.notes.strip() if payload.notes else None,
            submitted_at=now_utc,
        )
        db.add(order)
        db.flush()

        order.order_number = f"ORD-{today_ist.year}-{order.id:04d}"

        for ps, qty_pkts, unit_price_paisa in resolved_items:
            db.add(
                SalesOrderItem(
                    sales_order_id=order.id,
                    pack_size_id=ps.id,
                    ordered_qty_pkts=qty_pkts,
                    original_unit_price_paisa=unit_price_paisa,
                    unit_price_paisa=unit_price_paisa,
                )
            )

        db.add(
            SalesOrderStatusHistory(
                sales_order_id=order.id,
                from_status=None,
                to_status=OrderStatus.SUBMITTED,
                changed_by=actor.user_id,
                reason="Submitted via mobile sales workflow",
            )
        )

        db.add(
            SalesOrderApproval(
                sales_order_id=order.id,
                reviewed_by=actor.user_id,
                decision="HELD_SHORTAGE" if has_shortage else "PENDING_REVIEW",
                ordered_total_pkts=ordered_total_pkts,
                available_total_pkts=available_total_pkts,
                shortage_pkts=shortage_total_pkts,
                stock_snapshot=stock_snapshot,
                remarks=(
                    f"Initial stock check flagged shortage of {shortage_total_pkts} packets."
                    if has_shortage
                    else "Initial stock check passed; awaiting Factory Admin verification."
                ),
            )
        )

        db.flush()
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="ORDER_SUBMITTED",
            entity_schema="sales",
            entity_table="sales_orders",
            entity_id=order.id,
            after_state={
                "order_number": order.order_number,
                "customer_id": customer.id,
                "ordered_total_pkts": ordered_total_pkts,
                "has_shortage": has_shortage,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = orders_repo.get_order_by_id(db, order.id)
    assert refreshed is not None
    return _build_order_detail(
        db, refreshed, actor_role=actor.role_code, is_duplicate_replay=False
    ), False


def salesman_resubmit_order(
    db: Session, actor: CurrentActor, order_id: int, payload: SalesmanResubmitRequest
) -> OrderDetailResponse:
    """Allow owning salesman to revise and resubmit an order in CORRECTION_REQUESTED status."""
    if actor.role_code != "SALESMAN":
        raise AuthorizationError("Only field salesmen can resubmit corrected orders.")

    try:
        order = orders_repo.get_order_by_id_for_update(db, order_id)
        if order is None:
            raise NotFoundError(f"Sales order {order_id} was not found.")
        if order.salesman_id != actor.user_id:
            raise AuthorizationError("Salesmen can only modify their own orders.")

        assert_transition_allowed(
            order.status, OrderStatus.SUBMITTED, order_number=order.order_number
        )

        customer = sales_service.validate_customer_access(db, actor, order.customer_id)
        sku_ids = [line.pack_size_id for line in payload.items]
        pack_sizes = sales_repo.get_pack_sizes_by_ids(db, sku_ids)
        missing_skus = [sid for sid in sku_ids if sid not in pack_sizes]
        if missing_skus:
            raise DomainValidationError(
                f"Inactive or unknown product pack size IDs: {missing_skus}",
                details={"missing_pack_size_ids": missing_skus},
            )

        today_ist = datetime.now(IST).date()
        before_items = [
            {
                "pack_size_id": item.pack_size_id,
                "ordered_qty_pkts": item.ordered_qty_pkts,
                "unit_price_paisa": int(item.unit_price_paisa),
            }
            for item in order.items
        ]

        existing_by_sku = {item.pack_size_id: item for item in order.items}
        incoming_sku_set = set(sku_ids)
        for existing_sku, existing_item in list(existing_by_sku.items()):
            if existing_sku not in incoming_sku_set:
                db.delete(existing_item)
        db.flush()

        after_items: list[dict[str, int]] = []
        snapshot_pairs: list[tuple[PackSize, int]] = []

        for line in payload.items:
            ps = pack_sizes[line.pack_size_id]
            price_paisa = sales_service.resolve_authoritative_price_paisa(
                db,
                pack_size=ps,
                customer_id=customer.id,
                qty_pkts=line.ordered_qty_pkts,
                as_of=today_ist,
            )
            existing_item = existing_by_sku.get(line.pack_size_id)
            if existing_item is not None:
                existing_item.ordered_qty_pkts = line.ordered_qty_pkts
                existing_item.approved_qty_pkts = None
                existing_item.original_unit_price_paisa = price_paisa
                existing_item.unit_price_paisa = price_paisa
            else:
                db.add(
                    SalesOrderItem(
                        sales_order_id=order.id,
                        pack_size_id=ps.id,
                        ordered_qty_pkts=line.ordered_qty_pkts,
                        approved_qty_pkts=None,
                        original_unit_price_paisa=price_paisa,
                        unit_price_paisa=price_paisa,
                    )
                )
            snapshot_pairs.append((ps, line.ordered_qty_pkts))
            after_items.append(
                {
                    "pack_size_id": ps.id,
                    "ordered_qty_pkts": line.ordered_qty_pkts,
                    "unit_price_paisa": price_paisa,
                }
            )

        stock_snapshot, ordered_total, available_total, shortage_total = (
            _compute_stock_snapshot_for_items(db, snapshot_pairs)
        )
        has_shortage = shortage_total > 0
        prev_status = order.status

        order.status = OrderStatus.SUBMITTED
        order.has_shortage = has_shortage
        order.notes = payload.notes.strip() if payload.notes is not None else order.notes
        order.submitted_at = datetime.now(UTC)
        order.version += 1

        db.add(
            SalesOrderStatusHistory(
                sales_order_id=order.id,
                from_status=prev_status,
                to_status=OrderStatus.SUBMITTED,
                changed_by=actor.user_id,
                reason="Resubmitted by salesman after correction request",
            )
        )
        db.add(
            SalesOrderApproval(
                sales_order_id=order.id,
                reviewed_by=actor.user_id,
                decision="HELD_SHORTAGE" if has_shortage else "PENDING_REVIEW",
                ordered_total_pkts=ordered_total,
                available_total_pkts=available_total,
                shortage_pkts=shortage_total,
                stock_snapshot=stock_snapshot,
                remarks="Salesman revised and resubmitted order for Admin review.",
            )
        )
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="ORDER_RESUBMITTED",
            entity_schema="sales",
            entity_table="sales_orders",
            entity_id=order.id,
            before_state={"status": prev_status, "items": before_items},
            after_state={"status": OrderStatus.SUBMITTED, "items": after_items, "has_shortage": has_shortage},
            reason="Salesman correction resubmission",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = orders_repo.get_order_by_id(db, order_id)
    assert refreshed is not None
    return _build_order_detail(db, refreshed, actor_role=actor.role_code)


def admin_modify_order(
    db: Session, actor: CurrentActor, order_id: int, payload: AdminModifyOrderRequest
) -> OrderDetailResponse:
    """Allow Factory Admin to adjust quantities, unit prices, and remarks pre-approval."""
    _require_factory_admin(actor)

    try:
        order = orders_repo.get_order_by_id_for_update(db, order_id)
        if order is None:
            raise NotFoundError(f"Sales order {order_id} was not found.")
        _check_expected_version(order, payload.expected_version)

        if order.status not in ADMIN_EDITABLE_STATUSES:
            raise ConflictError(
                f"Order {order.order_number} in status '{order.status}' is locked and cannot be modified.",
                error_code="ORDER_LOCKED",
                details={"status": order.status},
            )

        items_by_id = {item.id: item for item in order.items}
        sku_ids = [item.pack_size_id for item in order.items]
        ps_map = sales_repo.get_pack_sizes_by_ids(db, sku_ids, include_inactive=True)

        qty_changes: list[dict[str, Any]] = []
        price_changes: list[dict[str, Any]] = []

        for adj in payload.items:
            item = items_by_id.get(adj.id)
            if item is None:
                raise DomainValidationError(f"Order item {adj.id} does not belong to this order.")
            ps = ps_map[item.pack_size_id]
            old_eff_qty = _effective_item_qty(item)
            old_price = int(item.unit_price_paisa)

            if adj.approved_qty_pkts != old_eff_qty:
                qty_changes.append(
                    {
                        "item_id": item.id,
                        "sku_code": ps.sku_code,
                        "ordered_qty_pkts": item.ordered_qty_pkts,
                        "before_qty_pkts": old_eff_qty,
                        "after_qty_pkts": adj.approved_qty_pkts,
                    }
                )
                item.approved_qty_pkts = adj.approved_qty_pkts

            if adj.unit_price_paisa != old_price:
                price_changes.append(
                    {
                        "item_id": item.id,
                        "sku_code": ps.sku_code,
                        "original_unit_price_paisa": int(item.original_unit_price_paisa),
                        "before_unit_price_paisa": old_price,
                        "after_unit_price_paisa": adj.unit_price_paisa,
                    }
                )
                item.unit_price_paisa = adj.unit_price_paisa

        reason_clean = payload.reason.strip() if payload.reason else ""
        if (qty_changes or price_changes) and len(reason_clean) < 5:
            raise DomainValidationError(
                "A reason of at least 5 characters is required whenever modifying quantities or prices."
            )

        new_total_qty = sum(_effective_item_qty(i) for i in order.items)
        if new_total_qty <= 0:
            raise DomainValidationError(
                "Order total quantity after modification must be greater than zero packets (reject or cancel instead)."
            )

        old_remarks = order.admin_remarks
        remarks_changed = (
            payload.admin_remarks is not None and payload.admin_remarks.strip() != (old_remarks or "")
        )
        if payload.admin_remarks is not None:
            cleaned_remark = payload.admin_remarks.strip()
            order.admin_remarks = cleaned_remark if cleaned_remark else None

        stock_snapshot, ordered_total, available_total, shortage_total = (
            _snapshot_from_order_items(db, order)
        )
        order.has_shortage = shortage_total > 0

        prev_status = order.status
        if prev_status == OrderStatus.SUBMITTED and (qty_changes or price_changes or remarks_changed):
            order.status = OrderStatus.UNDER_REVIEW
            db.add(
                SalesOrderStatusHistory(
                    sales_order_id=order.id,
                    from_status=prev_status,
                    to_status=OrderStatus.UNDER_REVIEW,
                    changed_by=actor.user_id,
                    reason=reason_clean or "Admin opened order verification and revised details",
                )
            )

        order.version += 1
        db.flush()

        if qty_changes:
            record_audit_log(
                db,
                actor_user_id=actor.user_id,
                actor_role=actor.role_code,
                action="ORDER_QTY_MODIFIED",
                entity_schema="sales",
                entity_table="sales_orders",
                entity_id=order.id,
                before_state={"items": [{k: v for k, v in c.items() if k != "after_qty_pkts"} for c in qty_changes]},
                after_state={"items": qty_changes, "has_shortage": order.has_shortage},
                reason=reason_clean,
            )
        if price_changes:
            record_audit_log(
                db,
                actor_user_id=actor.user_id,
                actor_role=actor.role_code,
                action="ORDER_PRICE_MODIFIED",
                entity_schema="sales",
                entity_table="sales_orders",
                entity_id=order.id,
                before_state={"items": [{k: v for k, v in c.items() if k != "after_unit_price_paisa"} for c in price_changes]},
                after_state={"items": price_changes},
                reason=reason_clean,
            )
        if remarks_changed:
            record_audit_log(
                db,
                actor_user_id=actor.user_id,
                actor_role=actor.role_code,
                action="ORDER_REMARK_UPDATED",
                entity_schema="sales",
                entity_table="sales_orders",
                entity_id=order.id,
                before_state={"admin_remarks": old_remarks},
                after_state={"admin_remarks": order.admin_remarks},
                reason=reason_clean or "Admin remark updated",
            )

        if qty_changes or price_changes:
            db.add(
                SalesOrderApproval(
                    sales_order_id=order.id,
                    reviewed_by=actor.user_id,
                    decision="HELD_SHORTAGE" if order.has_shortage else "PENDING_REVIEW",
                    ordered_total_pkts=ordered_total,
                    available_total_pkts=available_total,
                    shortage_pkts=shortage_total,
                    stock_snapshot=stock_snapshot,
                    remarks=reason_clean or order.admin_remarks,
                )
            )

        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = orders_repo.get_order_by_id(db, order_id)
    assert refreshed is not None
    return _build_order_detail(db, refreshed, actor_role=actor.role_code)


def admin_mark_under_review(
    db: Session, actor: CurrentActor, order_id: int, payload: AdminReviewHoldRequest
) -> OrderDetailResponse:
    """Move SUBMITTED -> UNDER_REVIEW (or refresh stock check if already UNDER_REVIEW without duplicate history)."""
    _require_factory_admin(actor)

    try:
        order = orders_repo.get_order_by_id_for_update(db, order_id)
        if order is None:
            raise NotFoundError(f"Sales order {order_id} was not found.")
        _check_expected_version(order, payload.expected_version)

        prev_status = order.status
        if prev_status == OrderStatus.SUBMITTED:
            assert_transition_allowed(
                prev_status, OrderStatus.UNDER_REVIEW, order_number=order.order_number
            )
            order.status = OrderStatus.UNDER_REVIEW
            db.add(
                SalesOrderStatusHistory(
                    sales_order_id=order.id,
                    from_status=prev_status,
                    to_status=OrderStatus.UNDER_REVIEW,
                    changed_by=actor.user_id,
                    reason=(payload.reason or payload.admin_remarks or "Marked under factory verification"),
                )
            )
        elif prev_status != OrderStatus.UNDER_REVIEW:
            assert_transition_allowed(
                prev_status, OrderStatus.UNDER_REVIEW, order_number=order.order_number
            )

        stock_snapshot, ordered_total, available_total, shortage_total = (
            _snapshot_from_order_items(db, order)
        )
        order.has_shortage = shortage_total > 0
        if payload.admin_remarks is not None:
            cleaned = payload.admin_remarks.strip()
            order.admin_remarks = cleaned if cleaned else None
        order.version += 1

        db.add(
            SalesOrderApproval(
                sales_order_id=order.id,
                reviewed_by=actor.user_id,
                decision="HELD_SHORTAGE" if order.has_shortage else "PENDING_REVIEW",
                ordered_total_pkts=ordered_total,
                available_total_pkts=available_total,
                shortage_pkts=shortage_total,
                stock_snapshot=stock_snapshot,
                remarks=payload.admin_remarks or payload.reason or (
                    f"Held under review; shortage {shortage_total} packets."
                    if order.has_shortage
                    else "Marked under verification review."
                ),
            )
        )
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="ORDER_MARKED_UNDER_REVIEW",
            entity_schema="sales",
            entity_table="sales_orders",
            entity_id=order.id,
            before_state={"status": prev_status},
            after_state={
                "status": order.status,
                "has_shortage": order.has_shortage,
                "shortage_pkts": shortage_total,
                "admin_remarks": order.admin_remarks,
            },
            reason=payload.reason or payload.admin_remarks or "Order review check",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = orders_repo.get_order_by_id(db, order_id)
    assert refreshed is not None
    return _build_order_detail(db, refreshed, actor_role=actor.role_code)


def admin_request_correction(
    db: Session, actor: CurrentActor, order_id: int, payload: AdminReasonRequest
) -> OrderDetailResponse:
    """Return an order from SUBMITTED/UNDER_REVIEW to CORRECTION_REQUESTED for salesman revision."""
    _require_factory_admin(actor)

    try:
        order = orders_repo.get_order_by_id_for_update(db, order_id)
        if order is None:
            raise NotFoundError(f"Sales order {order_id} was not found.")
        _check_expected_version(order, payload.expected_version)
        assert_transition_allowed(
            order.status, OrderStatus.CORRECTION_REQUESTED, order_number=order.order_number
        )

        stock_snapshot, ordered_total, available_total, shortage_total = (
            _snapshot_from_order_items(db, order)
        )
        prev_status = order.status
        order.status = OrderStatus.CORRECTION_REQUESTED
        order.admin_remarks = (
            payload.admin_remarks.strip() if payload.admin_remarks else payload.reason
        )
        order.version += 1

        db.add(
            SalesOrderStatusHistory(
                sales_order_id=order.id,
                from_status=prev_status,
                to_status=OrderStatus.CORRECTION_REQUESTED,
                changed_by=actor.user_id,
                reason=payload.reason,
            )
        )
        db.add(
            SalesOrderApproval(
                sales_order_id=order.id,
                reviewed_by=actor.user_id,
                decision="CORRECTION_REQUESTED",
                ordered_total_pkts=ordered_total,
                available_total_pkts=available_total,
                shortage_pkts=shortage_total,
                stock_snapshot=stock_snapshot,
                remarks=payload.reason,
            )
        )
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="ORDER_CORRECTION_REQ",
            entity_schema="sales",
            entity_table="sales_orders",
            entity_id=order.id,
            before_state={"status": prev_status},
            after_state={"status": OrderStatus.CORRECTION_REQUESTED, "admin_remarks": order.admin_remarks},
            reason=payload.reason,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = orders_repo.get_order_by_id(db, order_id)
    assert refreshed is not None
    return _build_order_detail(db, refreshed, actor_role=actor.role_code)


def admin_approve_order(
    db: Session, actor: CurrentActor, order_id: int, payload: AdminApproveRequest
) -> OrderDetailResponse:
    """Atomically verify FG availability (FOR UPDATE), reserve stock, and approve order."""
    _require_factory_admin(actor)

    try:
        order = orders_repo.get_order_by_id_for_update(db, order_id)
        if order is None:
            raise NotFoundError(f"Sales order {order_id} was not found.")
        _check_expected_version(order, payload.expected_version)

        assert_transition_allowed(
            order.status, OrderStatus.APPROVED, order_number=order.order_number
        )

        customer = sales_repo.get_customer_by_id(db, order.customer_id)
        if customer is None or not customer.is_active:
            raise DomainValidationError("Cannot approve order for an inactive customer account.")

        sku_ids = [item.pack_size_id for item in order.items]
        ps_map = sales_repo.get_pack_sizes_by_ids(db, sku_ids, include_inactive=True)

        reservation_lines: list[dict[str, Any]] = []
        total_effective_qty = 0
        for item in order.items:
            eff_qty = _effective_item_qty(item)
            total_effective_qty += eff_qty
            if eff_qty > 0:
                ps = ps_map[item.pack_size_id]
                reservation_lines.append(
                    {
                        "sales_order_item_id": item.id,
                        "pack_size_id": ps.id,
                        "sku_code": ps.sku_code,
                        "display_name": ps.display_name,
                        "qty_pkts": eff_qty,
                    }
                )

        if total_effective_qty <= 0 or not reservation_lines:
            raise DomainValidationError(
                "Order must contain at least one positive approved packet quantity."
            )

        reservations, stock_snapshot, ordered_total, available_total = (
            inventory_service.reserve_order_stock(
                db,
                order_id=order.id,
                lines=reservation_lines,
                actor_user_id=actor.user_id,
            )
        )

        now_utc = datetime.now(UTC)
        prev_status = order.status
        for item in order.items:
            if item.approved_qty_pkts is None:
                item.approved_qty_pkts = item.ordered_qty_pkts

        order.status = OrderStatus.APPROVED
        order.has_shortage = False
        order.approved_by = actor.user_id
        order.approved_at = now_utc
        if payload.admin_remarks is not None:
            cleaned = payload.admin_remarks.strip()
            order.admin_remarks = cleaned if cleaned else None
        order.version += 1

        approval_reason = (
            (payload.reason.strip() if payload.reason else None)
            or order.admin_remarks
            or "Verified stock coverage and approved by Factory Admin"
        )

        db.add(
            SalesOrderStatusHistory(
                sales_order_id=order.id,
                from_status=prev_status,
                to_status=OrderStatus.APPROVED,
                changed_by=actor.user_id,
                reason=approval_reason,
            )
        )
        db.add(
            SalesOrderApproval(
                sales_order_id=order.id,
                reviewed_by=actor.user_id,
                decision="APPROVED",
                ordered_total_pkts=ordered_total,
                available_total_pkts=available_total,
                shortage_pkts=0,
                stock_snapshot=stock_snapshot,
                remarks=approval_reason,
            )
        )
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="ORDER_APPROVED",
            entity_schema="sales",
            entity_table="sales_orders",
            entity_id=order.id,
            before_state={"status": prev_status},
            after_state={
                "status": OrderStatus.APPROVED,
                "approved_total_pkts": ordered_total,
                "admin_remarks": order.admin_remarks,
            },
            reason=approval_reason,
        )
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="STOCK_RESERVED",
            entity_schema="inventory",
            entity_table="inventory_balances",
            entity_id=order.id,
            after_state={
                "sales_order_id": order.id,
                "order_number": order.order_number,
                "items": [
                    {
                        "pack_size_id": res.pack_size_id,
                        "reserved_qty_pkts": res.reserved_qty_pkts,
                        "reservation_id": res.id,
                    }
                    for res in reservations
                ],
            },
            reason=approval_reason,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = orders_repo.get_order_by_id(db, order_id)
    assert refreshed is not None
    return _build_order_detail(db, refreshed, actor_role=actor.role_code)


def admin_reject_order(
    db: Session, actor: CurrentActor, order_id: int, payload: AdminReasonRequest
) -> OrderDetailResponse:
    """Reject a pre-approval order permanently with a mandatory reason."""
    _require_factory_admin(actor)

    try:
        order = orders_repo.get_order_by_id_for_update(db, order_id)
        if order is None:
            raise NotFoundError(f"Sales order {order_id} was not found.")
        _check_expected_version(order, payload.expected_version)

        assert_transition_allowed(
            order.status, OrderStatus.REJECTED, order_number=order.order_number
        )

        stock_snapshot, ordered_total, available_total, shortage_total = (
            _snapshot_from_order_items(db, order)
        )
        now_utc = datetime.now(UTC)
        prev_status = order.status

        order.status = OrderStatus.REJECTED
        order.rejected_by = actor.user_id
        order.rejected_at = now_utc
        order.rejection_reason = payload.reason
        order.admin_remarks = (
            payload.admin_remarks.strip() if payload.admin_remarks else payload.reason
        )
        order.version += 1

        db.add(
            SalesOrderStatusHistory(
                sales_order_id=order.id,
                from_status=prev_status,
                to_status=OrderStatus.REJECTED,
                changed_by=actor.user_id,
                reason=payload.reason,
            )
        )
        db.add(
            SalesOrderApproval(
                sales_order_id=order.id,
                reviewed_by=actor.user_id,
                decision="REJECTED",
                ordered_total_pkts=ordered_total,
                available_total_pkts=available_total,
                shortage_pkts=shortage_total,
                stock_snapshot=stock_snapshot,
                remarks=payload.reason,
            )
        )
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="ORDER_REJECTED",
            entity_schema="sales",
            entity_table="sales_orders",
            entity_id=order.id,
            before_state={"status": prev_status},
            after_state={
                "status": OrderStatus.REJECTED,
                "rejection_reason": payload.reason,
                "admin_remarks": order.admin_remarks,
            },
            reason=payload.reason,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = orders_repo.get_order_by_id(db, order_id)
    assert refreshed is not None
    return _build_order_detail(db, refreshed, actor_role=actor.role_code)


def cancel_order(
    db: Session,
    actor: CurrentActor,
    order_id: int,
    payload: OrderReasonRequest | AdminReasonRequest,
) -> OrderDetailResponse:
    """Cancel an order pre-invoice; releases stock reservation atomically if APPROVED."""
    try:
        order = orders_repo.get_order_by_id_for_update(db, order_id)
        if order is None:
            raise NotFoundError(f"Sales order {order_id} was not found.")

        if isinstance(payload, AdminReasonRequest):
            _check_expected_version(order, payload.expected_version)

        if actor.role_code == "SALESMAN":
            if order.salesman_id != actor.user_id:
                raise AuthorizationError("Salesmen can only cancel their own orders.")
            if order.status not in SALESMAN_CANCELLABLE_STATUSES:
                raise ConflictError(
                    f"Order {order.order_number} in status '{order.status}' cannot be cancelled by Salesman.",
                    error_code="INVALID_STATE_TRANSITION",
                    details={"status": order.status},
                )
        elif actor.role_code != "FACTORY_ADMIN":
            raise AuthorizationError("You do not have permission to cancel this order.")

        assert_transition_allowed(
            order.status, OrderStatus.CANCELLED, order_number=order.order_number
        )

        stock_snapshot, ordered_total, available_total, shortage_total = (
            _snapshot_from_order_items(db, order)
        )
        prev_status = order.status
        now_utc = datetime.now(UTC)

        released_pairs = []
        if prev_status == OrderStatus.APPROVED:
            released_pairs = inventory_service.release_order_reservations(
                db,
                order_id=order.id,
                actor_user_id=actor.user_id,
                reason=payload.reason,
            )

        order.status = OrderStatus.CANCELLED
        order.cancelled_by = actor.user_id
        order.cancelled_at = now_utc
        order.cancellation_reason = payload.reason
        if isinstance(payload, AdminReasonRequest) and payload.admin_remarks:
            order.admin_remarks = payload.admin_remarks.strip()
        order.version += 1

        db.add(
            SalesOrderStatusHistory(
                sales_order_id=order.id,
                from_status=prev_status,
                to_status=OrderStatus.CANCELLED,
                changed_by=actor.user_id,
                reason=payload.reason,
            )
        )
        db.add(
            SalesOrderApproval(
                sales_order_id=order.id,
                reviewed_by=actor.user_id,
                decision="CANCELLED",
                ordered_total_pkts=ordered_total,
                available_total_pkts=available_total,
                shortage_pkts=shortage_total,
                stock_snapshot=stock_snapshot,
                remarks=payload.reason,
            )
        )
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="ORDER_CANCELLED",
            entity_schema="sales",
            entity_table="sales_orders",
            entity_id=order.id,
            before_state={"status": prev_status},
            after_state={
                "status": OrderStatus.CANCELLED,
                "cancellation_reason": payload.reason,
                "released_reservations": len(released_pairs),
            },
            reason=payload.reason,
        )
        if released_pairs:
            record_audit_log(
                db,
                actor_user_id=actor.user_id,
                actor_role=actor.role_code,
                action="STOCK_RESERVATION_RELEASED",
                entity_schema="inventory",
                entity_table="inventory_balances",
                entity_id=order.id,
                after_state={
                    "sales_order_id": order.id,
                    "order_number": order.order_number,
                    "items": [
                        {
                            "reservation_id": res.id,
                            "pack_size_id": res.pack_size_id,
                            "released_qty_pkts": res.reserved_qty_pkts,
                            "new_reserved_qty_base": int(bal.reserved_qty_base),
                        }
                        for res, bal in released_pairs
                    ],
                },
                reason=payload.reason,
            )

        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = orders_repo.get_order_by_id(db, order_id)
    assert refreshed is not None
    return _build_order_detail(db, refreshed, actor_role=actor.role_code)


def get_admin_orders_summary(db: Session) -> AdminOrdersSummaryResponse:
    """Compute real PostgreSQL queue KPI counts across all sales_orders."""
    orders = orders_repo.list_all_orders_for_summary(db)
    if not orders:
        return AdminOrdersSummaryResponse(
            total_count=0,
            submitted_count=0,
            under_review_count=0,
            correction_requested_count=0,
            pending_verification_count=0,
            approved_count=0,
            rejected_count=0,
            cancelled_count=0,
            shortage_count=0,
            pending_value_paisa=0,
            approved_value_paisa=0,
        )

    company = iam_repo.get_company_profile(db)
    factory_state = company.state_code if company else "33"
    sku_ids = list({item.pack_size_id for o in orders for item in o.items})
    ps_map = sales_repo.get_pack_sizes_by_ids(db, sku_ids, include_inactive=True)

    counts = {
        OrderStatus.SUBMITTED: 0,
        OrderStatus.UNDER_REVIEW: 0,
        OrderStatus.CORRECTION_REQUESTED: 0,
        OrderStatus.APPROVED: 0,
        OrderStatus.REJECTED: 0,
        OrderStatus.CANCELLED: 0,
    }
    shortage_count = 0
    pending_value_paisa = 0
    approved_value_paisa = 0
    pending_set = set(PENDING_VERIFICATION_STATUSES)

    for order in orders:
        if order.status in counts:
            counts[order.status] += 1
        if order.has_shortage and order.status in pending_set:
            shortage_count += 1
        tax_lines = [
            (int(item.line_taxable_paisa), ps_map[item.pack_size_id].product.gst_rate_bps)
            for item in order.items
        ]
        grand_total = _compute_tax_estimate(
            factory_state_code=factory_state,
            place_of_supply_state_code=order.place_of_supply_state_code,
            lines=tax_lines,
        ).grand_total_paisa
        if order.status in pending_set:
            pending_value_paisa += grand_total
        elif order.status == OrderStatus.APPROVED:
            approved_value_paisa += grand_total

    return AdminOrdersSummaryResponse(
        total_count=len(orders),
        submitted_count=counts[OrderStatus.SUBMITTED],
        under_review_count=counts[OrderStatus.UNDER_REVIEW],
        correction_requested_count=counts[OrderStatus.CORRECTION_REQUESTED],
        pending_verification_count=(
            counts[OrderStatus.SUBMITTED]
            + counts[OrderStatus.UNDER_REVIEW]
            + counts[OrderStatus.CORRECTION_REQUESTED]
        ),
        approved_count=counts[OrderStatus.APPROVED],
        rejected_count=counts[OrderStatus.REJECTED],
        cancelled_count=counts[OrderStatus.CANCELLED],
        shortage_count=shortage_count,
        pending_value_paisa=pending_value_paisa,
        approved_value_paisa=approved_value_paisa,
    )


def list_paginated_orders(
    db: Session,
    *,
    salesman_id: int | None = None,
    customer_id: int | None = None,
    statuses: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    has_shortage: bool | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedOrdersResponse:
    orders, total = orders_repo.list_orders(
        db,
        salesman_id=salesman_id,
        customer_id=customer_id,
        statuses=statuses,
        date_from=date_from,
        date_to=date_to,
        has_shortage=has_shortage,
        search=search,
        page=page,
        page_size=page_size,
    )
    if not orders:
        return PaginatedOrdersResponse(
            items=[], total=total, page=page, page_size=page_size, total_pages=0
        )

    company = iam_repo.get_company_profile(db)
    factory_state = company.state_code if company else "33"

    cust_ids = {o.customer_id for o in orders}
    user_ids = {o.salesman_id for o in orders}
    sku_ids = {item.pack_size_id for o in orders for item in o.items}

    customers_map = {
        c.id: c
        for c in db.execute(select(Customer).where(Customer.id.in_(cust_ids))).scalars().all()
    }
    users_map = {
        u.id: u for u in db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
    }
    pack_sizes_map = sales_repo.get_pack_sizes_by_ids(db, list(sku_ids), include_inactive=True)

    items = [
        _hydrate_order_summary(
            o,
            customers_map=customers_map,
            users_map=users_map,
            pack_sizes_map=pack_sizes_map,
            factory_state_code=factory_state,
        )
        for o in orders
    ]
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return PaginatedOrdersResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def get_order_detail(db: Session, actor: CurrentActor, order_id: int) -> OrderDetailResponse:
    order = orders_repo.get_order_by_id(db, order_id)
    if order is None:
        raise NotFoundError(f"Sales order {order_id} was not found.")
    if actor.role_code == "SALESMAN" and order.salesman_id != actor.user_id:
        raise AuthorizationError("Salesmen can only view their own orders.")
    return _build_order_detail(db, order, actor_role=actor.role_code)
