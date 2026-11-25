from datetime import UTC, date, datetime, time
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
from app.modules.inventory import repository as inventory_repo
from app.modules.inventory.models import (
    CostLot,
    InventoryBalance,
    InventoryMovement,
    Material,
    OpeningBalance,
    StockAdjustment,
    StockReservation,
)
from app.modules.inventory.schemas import (
    InventoryBalanceSummaryResponse,
    InventoryDashboardResponse,
    InventoryLedgerEntryResponse,
    MaterialSummaryResponse,
    StockAdjustmentCreateRequest,
    StockAdjustmentResponse,
)
from app.modules.inventory.uom import convert_to_base_qty
from app.modules.sales import repository as sales_repo
from app.modules.sales.models import PackSize

IST = ZoneInfo("Asia/Kolkata")
_NEGATIVE_ONLY_ADJUSTMENT_TYPES = {"DAMAGED", "EXPIRED", "MISSING", "SUPPLIER_RETURN"}
_INBOUND_MOVEMENT_TYPES = {
    "PURCHASE_IN",
    "PROD_OUTPUT_IN",
    "CREDIT_RETURN_IN",
}
_ISSUED_MOVEMENT_TYPES = {
    "PROD_ISSUE_OUT",
    "PACKAGING_DAMAGE_OUT",
}
_PRODUCTION_RETURN_MOVEMENT_TYPES = {
    "PROD_RETURN_IN",
}
_ADJUSTED_MOVEMENT_TYPES = {
    "ADJUSTMENT",
    "DAMAGE_WASTAGE",
    "SUPPLIER_RETURN",
}


def _balance_snapshot(bal: InventoryBalance | None) -> dict[str, int]:
    if bal is None:
        return {"on_hand_pkts": 0, "reserved_pkts": 0, "available_pkts": 0}
    on_hand = int(bal.on_hand_qty_base)
    reserved = int(bal.reserved_qty_base)
    available = on_hand - reserved
    return {
        "on_hand_pkts": on_hand,
        "reserved_pkts": reserved,
        "available_pkts": available,
    }


def get_pack_size_availability_map(db: Session, pack_size_ids: list[int]) -> dict[int, dict[str, int]]:
    """Read-only availability summary per pack_size_id without mutating stock."""
    balances = inventory_repo.get_balances_by_pack_size_ids(db, pack_size_ids)
    return {sku_id: _balance_snapshot(balances.get(sku_id)) for sku_id in pack_size_ids}


def reserve_order_stock(
    db: Session,
    *,
    order_id: int,
    lines: list[dict],
    actor_user_id: int,
) -> tuple[list[StockReservation], dict[str, dict[str, int]], int, int]:
    """Atomically lock InventoryBalance rows in ascending ID order and reserve FG stock."""
    pack_ids = [line["pack_size_id"] for line in lines]
    locked_balances = inventory_repo.lock_balances_by_pack_size_ids(db, pack_ids)

    shortages: list[dict] = []
    stock_snapshot: dict[str, dict[str, int]] = {}
    ordered_total = 0
    available_total = 0

    for line in lines:
        ps_id = line["pack_size_id"]
        req_qty = int(line["qty_pkts"])
        bal = locked_balances.get(ps_id)
        snap = _balance_snapshot(bal)
        shortage_qty = max(0, req_qty - snap["available_pkts"])
        ordered_total += req_qty
        available_total += snap["available_pkts"]
        stock_snapshot[line["sku_code"]] = {
            "ordered_pkts": req_qty,
            "on_hand_pkts": snap["on_hand_pkts"],
            "reserved_pkts": snap["reserved_pkts"],
            "available_pkts": snap["available_pkts"],
            "shortage_pkts": shortage_qty,
        }
        if shortage_qty > 0:
            shortages.append(
                {
                    "pack_size_id": ps_id,
                    "sku_code": line["sku_code"],
                    "display_name": line["display_name"],
                    "requested_qty_pkts": req_qty,
                    "on_hand_qty_pkts": snap["on_hand_pkts"],
                    "reserved_qty_pkts": snap["reserved_pkts"],
                    "available_qty_pkts": snap["available_pkts"],
                    "shortage_pkts": shortage_qty,
                }
            )

    if shortages:
        summary = "; ".join(
            f"{s['display_name']}: requested {s['requested_qty_pkts']}, available {s['available_qty_pkts']} (short by {s['shortage_pkts']})"
            for s in shortages
        )
        raise ConflictError(
            f"Insufficient available finished-goods stock for approval ({summary}).",
            error_code="INSUFFICIENT_STOCK",
            details={
                "items": shortages,
                "stock_snapshot": stock_snapshot,
                "policy": (
                    "BR-AVL-02 / BR-AVL-03: Available stock = Physical On-Hand - Active Reservations. "
                    "Approval cannot exceed available stock or drive stock negative. "
                    "Reduce approved quantity, mark Under Review awaiting production, request correction, or reject order."
                ),
            },
        )

    now_utc = datetime.now(UTC)
    created_reservations: list[StockReservation] = []
    for line in lines:
        req_qty = int(line["qty_pkts"])
        bal = locked_balances[line["pack_size_id"]]
        bal.reserved_qty_base = (
            Decimal(bal.reserved_qty_base) + Decimal(req_qty)
        ).quantize(Decimal("0.001"))

        res = StockReservation(
            sales_order_id=order_id,
            sales_order_item_id=line["sales_order_item_id"],
            pack_size_id=line["pack_size_id"],
            reserved_qty_pkts=req_qty,
            status="ACTIVE",
            reserved_by=actor_user_id,
            reserved_at=now_utc,
        )
        db.add(res)
        created_reservations.append(res)

    db.flush()
    return created_reservations, stock_snapshot, ordered_total, available_total


def release_order_reservations(
    db: Session,
    *,
    order_id: int,
    actor_user_id: int,
    reason: str,
) -> list[tuple[StockReservation, InventoryBalance]]:
    """Release all ACTIVE stock reservations for a cancelled pre-invoice order atomically."""
    active_rows = inventory_repo.list_active_reservations_for_order_for_update(db, order_id)
    if not active_rows:
        return []

    locked_balances = inventory_repo.lock_balances_by_pack_size_ids(
        db, [r.pack_size_id for r in active_rows]
    )
    now_utc = datetime.now(UTC)
    released_pairs: list[tuple[StockReservation, InventoryBalance]] = []

    for res in active_rows:
        bal = locked_balances[res.pack_size_id]
        bal.reserved_qty_base = max(
            Decimal("0.000"),
            (Decimal(bal.reserved_qty_base) - Decimal(res.reserved_qty_pkts)).quantize(
                Decimal("0.001")
            ),
        )
        res.status = "RELEASED"
        res.released_by = actor_user_id
        res.released_at = now_utc
        res.release_reason = reason
        released_pairs.append((res, bal))

    db.flush()
    return released_pairs


def list_reservations_for_order(db: Session, order_id: int) -> list[StockReservation]:
    return inventory_repo.list_reservations_for_order(db, order_id)


def seed_opening_finished_goods(
    db: Session,
    *,
    batch_ref: str,
    pack_size_id: int,
    opening_qty_pkts: int,
    unit_cost_paisa: int,
    as_of_date: date,
    created_by: int,
) -> OpeningBalance:
    """Create opening FG stock via ledger movement; DB trigger updates inventory_balances."""
    return inventory_repo.create_opening_fg_ledger_entry(
        db,
        batch_ref=batch_ref,
        pack_size_id=pack_size_id,
        opening_qty_pkts=opening_qty_pkts,
        unit_cost_paisa=unit_cost_paisa,
        as_of_date=as_of_date,
        created_by=created_by,
    )


def seed_opening_material(
    db: Session,
    *,
    batch_ref: str,
    material: Material,
    entered_qty: Decimal,
    entered_uom: str,
    unit_rate_paisa_per_entered_uom: int,
    as_of_date: date,
    created_by: int,
) -> OpeningBalance:
    """Create opening RM/Packaging stock via ledger movement + CostLot; trigger updates balances."""
    qty_base, multiplier, norm_uom = convert_to_base_qty(
        db,
        entered_qty=entered_qty,
        entered_uom=entered_uom,
        expected_dimension=material.unit_dimension,
        expected_base_uom=material.base_uom,
    )
    unit_cost_base = (Decimal(unit_rate_paisa_per_entered_uom) / multiplier).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    total_cost_paisa = int(
        (entered_qty * Decimal(unit_rate_paisa_per_entered_uom)).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )
    return inventory_repo.create_opening_material_ledger_entry(
        db,
        batch_ref=batch_ref,
        material=material,
        opening_qty_base=qty_base,
        entered_qty=entered_qty,
        entered_uom=norm_uom,
        unit_cost_paisa_per_base=unit_cost_base,
        total_cost_paisa=total_cost_paisa,
        as_of_date=as_of_date,
        created_by=created_by,
    )


def post_purchase_receipt_to_ledger(
    db: Session,
    *,
    receipt_id: int,
    receipt_number: str,
    receipt_items: list[Any],
    materials_map: dict[int, Material],
    actor_user_id: int,
) -> list[InventoryMovement]:
    """Post accepted quantities of a verified Purchase Receipt into InventoryMovement & CostLot."""
    accepted_items = [it for it in receipt_items if Decimal(it.accepted_qty_base) > 0]
    if not accepted_items:
        return []

    # Acquire deterministic locks on existing balances (missing rows inserted cleanly via AFTER INSERT trigger)
    inventory_repo.lock_balances_by_material_ids(db, [it.material_id for it in accepted_items])

    created_movements: list[InventoryMovement] = []
    for item in accepted_items:
        mat = materials_map[item.material_id]
        qty_base = Decimal(item.accepted_qty_base).quantize(Decimal("0.001"))
        cost_base = Decimal(item.unit_cost_paisa_per_base).quantize(Decimal("0.000001"))
        total_cost = int(
            (qty_base * cost_base).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        )

        mov = InventoryMovement(
            item_category=mat.material_category,
            material_id=mat.id,
            movement_type="PURCHASE_IN",
            entered_qty=Decimal(item.accepted_qty_entered).quantize(Decimal("0.001")),
            entered_uom=item.entered_uom,
            signed_qty_base=qty_base,
            unit_cost_paisa_per_base=cost_base,
            total_cost_paisa=total_cost,
            source_doc_type="PURCHASE_RECEIPT",
            reference_code=receipt_number,
            notes=f"Accepted against {receipt_number}"
            + (f" (batch {item.batch_code})" if item.batch_code else ""),
            purchase_receipt_item_id=item.id,
            created_by=actor_user_id,
        )
        db.add(mov)
        created_movements.append(mov)

        db.add(
            CostLot(
                item_category=mat.material_category,
                material_id=mat.id,
                source_doc_type="PURCHASE_RECEIPT",
                source_doc_id=receipt_id,
                batch_code=item.batch_code,
                expiry_date=item.expiry_date,
                original_qty_base=qty_base,
                remaining_qty_base=qty_base,
                unit_cost_paisa_per_base=cost_base,
            )
        )

    db.flush()
    return created_movements


def list_materials(
    db: Session, *, category: str | None = None, search: str | None = None
) -> list[MaterialSummaryResponse]:
    rows = inventory_repo.list_all_materials(db, category=category, active_only=True, search=search)
    return [
        MaterialSummaryResponse(
            id=m.id,
            code=m.code,
            name=m.name,
            material_category=m.material_category,
            unit_dimension=m.unit_dimension,
            base_uom=m.base_uom,
            display_uom=m.display_uom,
            reorder_level_base=Decimal(m.reorder_level_base),
            is_active=m.is_active,
        )
        for m in rows
    ]


def _display_factor(display_uom: str, base_uom: str) -> Decimal:
    if display_uom == "kg" and base_uom == "g":
        return Decimal(1000)
    if display_uom == "L" and base_uom == "ml":
        return Decimal(1000)
    return Decimal(1)


def get_inventory_overview(
    db: Session,
    *,
    item_category: str | None = None,
    low_stock_only: bool = False,
    search: str | None = None,
) -> InventoryDashboardResponse:
    materials = inventory_repo.list_all_materials(db, active_only=True, search=search)
    pack_sizes = inventory_repo.list_all_active_pack_sizes(db, search=search)
    mat_balances = inventory_repo.get_balances_by_material_ids(db, [m.id for m in materials])
    ps_balances = inventory_repo.get_balances_by_pack_size_ids(db, [ps.id for ps in pack_sizes])

    movements = inventory_repo.list_all_movements_for_aggregation(db)
    open_lots = inventory_repo.list_all_open_cost_lots(db)

    mov_agg_mat: dict[int, dict[str, Decimal]] = {}
    mov_agg_ps: dict[int, dict[str, Decimal]] = {}

    def _empty_bucket() -> dict[str, Decimal]:
        return {
            "opening": Decimal(0),
            "received": Decimal(0),
            "issued": Decimal(0),
            "dispatched": Decimal(0),
            "adjusted": Decimal(0),
        }

    for mov in movements:
        if mov.material_id is not None:
            bucket = mov_agg_mat.setdefault(mov.material_id, _empty_bucket())
        elif mov.pack_size_id is not None:
            bucket = mov_agg_ps.setdefault(mov.pack_size_id, _empty_bucket())
        else:
            continue

        qty = Decimal(mov.signed_qty_base)
        if mov.movement_type == "OPENING":
            bucket["opening"] += qty
        elif mov.movement_type in _INBOUND_MOVEMENT_TYPES:
            bucket["received"] += qty
        elif mov.movement_type in _ISSUED_MOVEMENT_TYPES:
            bucket["issued"] += abs(qty)
        elif mov.movement_type in _PRODUCTION_RETURN_MOVEMENT_TYPES:
            bucket["issued"] -= qty
        elif mov.movement_type == "DISPATCH_OUT":
            bucket["dispatched"] += abs(qty)
        elif mov.movement_type in _ADJUSTED_MOVEMENT_TYPES:
            bucket["adjusted"] += qty

    lot_val_mat: dict[int, int] = {}
    lot_val_ps: dict[int, int] = {}
    for lot in open_lots:
        val = int(
            (Decimal(lot.remaining_qty_base) * Decimal(lot.unit_cost_paisa_per_base)).quantize(
                Decimal(1), rounding=ROUND_HALF_UP
            )
        )
        if lot.material_id is not None:
            lot_val_mat[lot.material_id] = lot_val_mat.get(lot.material_id, 0) + val
        elif lot.pack_size_id is not None:
            lot_val_ps[lot.pack_size_id] = lot_val_ps.get(lot.pack_size_id, 0) + val

    all_items: list[InventoryBalanceSummaryResponse] = []

    for m in materials:
        bal = mat_balances.get(m.id)
        phys = Decimal(bal.on_hand_qty_base) if bal else Decimal("0.000")
        res = Decimal(bal.reserved_qty_base) if bal else Decimal("0.000")
        avail = (phys - res).quantize(Decimal("0.001"))
        agg = mov_agg_mat.get(m.id, _empty_bucket())
        is_low = avail <= Decimal(m.reorder_level_base)
        all_items.append(
            InventoryBalanceSummaryResponse(
                item_type="MATERIAL",
                item_id=m.id,
                item_category=m.material_category,
                code=m.code,
                name=m.name,
                unit_dimension=m.unit_dimension,
                base_uom=m.base_uom,
                display_uom=m.display_uom,
                display_factor=_display_factor(m.display_uom, m.base_uom),
                reorder_level_base=Decimal(m.reorder_level_base),
                opening_qty_base=agg["opening"].quantize(Decimal("0.001")),
                received_qty_base=agg["received"].quantize(Decimal("0.001")),
                issued_qty_base=agg["issued"].quantize(Decimal("0.001")),
                dispatched_qty_base=agg["dispatched"].quantize(Decimal("0.001")),
                adjusted_qty_base=agg["adjusted"].quantize(Decimal("0.001")),
                physical_qty_base=phys.quantize(Decimal("0.001")),
                reserved_qty_base=res.quantize(Decimal("0.001")),
                available_qty_base=avail,
                is_low_stock=is_low,
                open_lot_value_paisa=lot_val_mat.get(m.id, 0),
            )
        )

    for ps in pack_sizes:
        bal = ps_balances.get(ps.id)
        phys = Decimal(bal.on_hand_qty_base) if bal else Decimal("0.000")
        res = Decimal(bal.reserved_qty_base) if bal else Decimal("0.000")
        avail = (phys - res).quantize(Decimal("0.001"))
        agg = mov_agg_ps.get(ps.id, _empty_bucket())
        reorder_fg = Decimal("20.000")
        is_low = avail <= reorder_fg
        all_items.append(
            InventoryBalanceSummaryResponse(
                item_type="PACK_SIZE",
                item_id=ps.id,
                item_category="FINISHED_GOOD",
                code=ps.sku_code,
                name=ps.display_name,
                unit_dimension="COUNT",
                base_uom="packet",
                display_uom="packet",
                display_factor=Decimal(1),
                reorder_level_base=reorder_fg,
                opening_qty_base=agg["opening"].quantize(Decimal("0.001")),
                received_qty_base=agg["received"].quantize(Decimal("0.001")),
                issued_qty_base=agg["issued"].quantize(Decimal("0.001")),
                dispatched_qty_base=agg["dispatched"].quantize(Decimal("0.001")),
                adjusted_qty_base=agg["adjusted"].quantize(Decimal("0.001")),
                physical_qty_base=phys.quantize(Decimal("0.001")),
                reserved_qty_base=res.quantize(Decimal("0.001")),
                available_qty_base=avail,
                is_low_stock=is_low,
                open_lot_value_paisa=lot_val_ps.get(ps.id, 0),
            )
        )

    rm_count = sum(1 for i in all_items if i.item_category == "RAW_MATERIAL")
    pkg_count = sum(1 for i in all_items if i.item_category == "PACKAGING_MATERIAL")
    fg_count = sum(1 for i in all_items if i.item_category == "FINISHED_GOOD")
    low_count = sum(1 for i in all_items if i.is_low_stock)
    total_value = sum(i.open_lot_value_paisa for i in all_items)

    filtered = all_items
    if item_category:
        filtered = [i for i in filtered if i.item_category == item_category]
    if low_stock_only:
        filtered = [i for i in filtered if i.is_low_stock]

    return InventoryDashboardResponse(
        total_items=len(all_items),
        raw_material_count=rm_count,
        packaging_material_count=pkg_count,
        finished_good_count=fg_count,
        low_stock_count=low_count,
        pending_adjustments_count=inventory_repo.count_pending_adjustments(db),
        total_stock_value_paisa=total_value,
        items=filtered,
    )


def list_ledger_entries(
    db: Session,
    *,
    item_category: str | None = None,
    material_id: int | None = None,
    pack_size_id: int | None = None,
    production_run_id: int | None = None,
    movement_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 200,
) -> list[InventoryLedgerEntryResponse]:
    start_dt = (
        datetime.combine(date_from, time.min, tzinfo=IST).astimezone(UTC) if date_from else None
    )
    end_dt = datetime.combine(date_to, time.max, tzinfo=IST).astimezone(UTC) if date_to else None

    rows = inventory_repo.list_inventory_movements(
        db,
        item_category=item_category,
        material_id=material_id,
        pack_size_id=pack_size_id,
        production_run_id=production_run_id,
        movement_type=movement_type,
        date_from=start_dt,
        date_to=end_dt,
        limit=limit,
    )
    if not rows:
        return []

    mat_ids = {r.material_id for r in rows if r.material_id is not None}
    ps_ids = {r.pack_size_id for r in rows if r.pack_size_id is not None}
    user_ids = {r.created_by for r in rows}

    materials_map = (
        {
            m.id: m
            for m in db.execute(select(Material).where(Material.id.in_(mat_ids))).scalars().all()
        }
        if mat_ids
        else {}
    )
    ps_map = sales_repo.get_pack_sizes_by_ids(db, list(ps_ids), include_inactive=True) if ps_ids else {}
    users_map = {
        u.id: u for u in db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
    }

    dispatch_item_ids = {r.dispatch_item_id for r in rows if r.dispatch_item_id is not None}
    dispatch_link_map: dict[int, tuple[int, int]] = {}
    if dispatch_item_ids:
        from app.modules.billing.models import Dispatch, DispatchItem

        d_rows = db.execute(
            select(DispatchItem.id, Dispatch.id, Dispatch.invoice_id)
            .join(Dispatch, Dispatch.id == DispatchItem.dispatch_id)
            .where(DispatchItem.id.in_(dispatch_item_ids))
        ).all()
        dispatch_link_map = {row[0]: (int(row[1]), int(row[2])) for row in d_rows}

    cn_item_ids = {r.credit_note_item_id for r in rows if r.credit_note_item_id is not None}
    cn_invoice_map: dict[int, int] = {}
    if cn_item_ids:
        from app.modules.billing.models import CreditNote, CreditNoteItem

        c_rows = db.execute(
            select(CreditNoteItem.id, CreditNote.original_invoice_id)
            .join(CreditNote, CreditNote.id == CreditNoteItem.credit_note_id)
            .where(CreditNoteItem.id.in_(cn_item_ids))
        ).all()
        cn_invoice_map = {row[0]: int(row[1]) for row in c_rows}

    result: list[InventoryLedgerEntryResponse] = []
    for mov in rows:
        if mov.material_id is not None:
            mat = materials_map[mov.material_id]
            item_type = "MATERIAL"
            item_id = mat.id
            code = mat.code
            name = mat.name
            base_uom = mat.base_uom
            display_uom = mat.display_uom
        else:
            assert mov.pack_size_id is not None
            ps = ps_map[mov.pack_size_id]
            item_type = "PACK_SIZE"
            item_id = ps.id
            code = ps.sku_code
            name = ps.display_name
            base_uom = "packet"
            display_uom = "packet"

        result.append(
            InventoryLedgerEntryResponse(
                id=mov.id,
                occurred_at=mov.occurred_at,
                item_category=mov.item_category,
                item_type=item_type,
                item_id=item_id,
                item_code=code,
                item_name=name,
                base_uom=base_uom,
                display_uom=display_uom,
                movement_type=mov.movement_type,
                entered_qty=Decimal(mov.entered_qty) if mov.entered_qty is not None else None,
                entered_uom=mov.entered_uom,
                signed_qty_base=Decimal(mov.signed_qty_base),
                unit_cost_paisa_per_base=Decimal(mov.unit_cost_paisa_per_base),
                total_cost_paisa=int(mov.total_cost_paisa),
                source_doc_type=mov.source_doc_type,
                reference_code=mov.reference_code,
                notes=mov.notes,
                actor_name=users_map[mov.created_by].full_name,
                opening_balance_id=mov.opening_balance_id,
                purchase_receipt_item_id=mov.purchase_receipt_item_id,
                stock_adjustment_id=mov.stock_adjustment_id,
                production_run_id=mov.production_run_id,
                dispatch_item_id=mov.dispatch_item_id,
                credit_note_item_id=mov.credit_note_item_id,
                dispatch_id=(
                    dispatch_link_map[mov.dispatch_item_id][0]
                    if mov.dispatch_item_id in dispatch_link_map
                    else None
                ),
                invoice_id=(
                    dispatch_link_map[mov.dispatch_item_id][1]
                    if mov.dispatch_item_id in dispatch_link_map
                    else cn_invoice_map.get(mov.credit_note_item_id)
                ),
            )
        )
    return result


def _hydrate_adjustments(db: Session, rows: list[StockAdjustment]) -> list[StockAdjustmentResponse]:
    if not rows:
        return []
    mat_ids = {r.material_id for r in rows if r.material_id is not None}
    ps_ids = {r.pack_size_id for r in rows if r.pack_size_id is not None}
    user_ids = {r.requested_by for r in rows} | {r.approved_by for r in rows if r.approved_by}

    materials_map = (
        {
            m.id: m
            for m in db.execute(select(Material).where(Material.id.in_(mat_ids))).scalars().all()
        }
        if mat_ids
        else {}
    )
    ps_map = sales_repo.get_pack_sizes_by_ids(db, list(ps_ids), include_inactive=True) if ps_ids else {}
    users_map = {
        u.id: u for u in db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
    }

    res: list[StockAdjustmentResponse] = []
    for adj in rows:
        if adj.material_id is not None:
            mat = materials_map[adj.material_id]
            item_type, item_id, code, name = "MATERIAL", mat.id, mat.code, mat.name
            base_uom, display_uom = mat.base_uom, mat.display_uom
        else:
            assert adj.pack_size_id is not None
            ps = ps_map[adj.pack_size_id]
            item_type, item_id, code, name = "PACK_SIZE", ps.id, ps.sku_code, ps.display_name
            base_uom, display_uom = "packet", "packet"

        res.append(
            StockAdjustmentResponse(
                id=adj.id,
                adjustment_number=adj.adjustment_number,
                item_category=adj.item_category,
                item_type=item_type,
                item_id=item_id,
                item_code=code,
                item_name=name,
                base_uom=base_uom,
                display_uom=display_uom,
                adjustment_type=adj.adjustment_type,
                entered_qty=Decimal(adj.entered_qty),
                entered_uom=adj.entered_uom,
                delta_qty_base=Decimal(adj.delta_qty_base),
                unit_cost_paisa_per_base=Decimal(adj.unit_cost_paisa_per_base),
                reason=adj.reason,
                status=adj.status,
                requested_by_name=users_map[adj.requested_by].full_name,
                approved_by_name=users_map[adj.approved_by].full_name if adj.approved_by else None,
                rejection_reason=adj.rejection_reason,
                requested_at=adj.requested_at,
                posted_at=adj.posted_at,
            )
        )
    return res


def _apply_adjustment_posting(
    db: Session, adj: StockAdjustment, *, approver: CurrentActor
) -> None:
    if adj.status == "POSTED":
        raise ConflictError(
            f"Adjustment {adj.adjustment_number} is already posted.",
            error_code="DUPLICATE_POST",
        )
    if adj.status == "REJECTED":
        raise ConflictError(
            f"Adjustment {adj.adjustment_number} is already rejected.",
            error_code="INVALID_STATE_TRANSITION",
        )

    delta = Decimal(adj.delta_qty_base).quantize(Decimal("0.001"))

    if adj.material_id is not None:
        bal = inventory_repo.lock_balances_by_material_ids(db, [adj.material_id]).get(adj.material_id)
    else:
        assert adj.pack_size_id is not None
        bal = inventory_repo.lock_balances_by_pack_size_ids(db, [adj.pack_size_id]).get(adj.pack_size_id)

    on_hand = Decimal(bal.on_hand_qty_base) if bal else Decimal("0.000")
    reserved = Decimal(bal.reserved_qty_base) if bal else Decimal("0.000")
    available = on_hand - reserved

    if delta < 0:
        reduction = abs(delta)
        if on_hand - reduction < 0:
            raise ConflictError(
                f"Adjustment blocked: cannot reduce physical stock below 0 (on-hand {on_hand}, requested reduction {reduction}).",
                error_code="INSUFFICIENT_STOCK",
            )
        if on_hand - reduction < reserved:
            raise ConflictError(
                f"Adjustment blocked: reducing by {reduction} leaves {on_hand - reduction}, below active Sales Order reservations ({reserved}; only {available} unreserved).",
                error_code="INSUFFICIENT_AVAILABLE_STOCK",
            )

    if adj.adjustment_type in {"DAMAGED", "EXPIRED"} and delta < 0:
        movement_type = "DAMAGE_WASTAGE"
        source_doc_type = "STOCK_ADJUSTMENT"
    elif adj.adjustment_type == "SUPPLIER_RETURN" and delta < 0:
        movement_type = "SUPPLIER_RETURN"
        source_doc_type = "SUPPLIER_RETURN"
    else:
        movement_type = "ADJUSTMENT"
        source_doc_type = "STOCK_ADJUSTMENT"

    total_cost = int(
        (abs(delta) * Decimal(adj.unit_cost_paisa_per_base)).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )

    # Maintain open CostLot valuation symmetrically
    if delta > 0:
        db.add(
            CostLot(
                item_category=adj.item_category,
                material_id=adj.material_id,
                pack_size_id=adj.pack_size_id,
                source_doc_type="STOCK_ADJUSTMENT",
                source_doc_id=adj.id,
                batch_code=adj.adjustment_number,
                original_qty_base=delta,
                remaining_qty_base=delta,
                unit_cost_paisa_per_base=Decimal(adj.unit_cost_paisa_per_base),
            )
        )
    else:
        remaining_to_deplete = abs(delta)
        open_lots = inventory_repo.list_open_cost_lots_for_update(
            db, material_id=adj.material_id, pack_size_id=adj.pack_size_id
        )
        for lot in open_lots:
            if remaining_to_deplete <= 0:
                break
            take = min(Decimal(lot.remaining_qty_base), remaining_to_deplete)
            lot.remaining_qty_base = (Decimal(lot.remaining_qty_base) - take).quantize(Decimal("0.001"))
            remaining_to_deplete -= take

    now_utc = datetime.now(UTC)
    db.add(
        InventoryMovement(
            item_category=adj.item_category,
            material_id=adj.material_id,
            pack_size_id=adj.pack_size_id,
            movement_type=movement_type,
            entered_qty=Decimal(adj.entered_qty),
            entered_uom=adj.entered_uom,
            signed_qty_base=delta,
            unit_cost_paisa_per_base=Decimal(adj.unit_cost_paisa_per_base),
            total_cost_paisa=total_cost,
            source_doc_type=source_doc_type,
            reference_code=adj.adjustment_number,
            notes=f"{adj.adjustment_type}: {adj.reason}",
            stock_adjustment_id=adj.id,
            created_by=approver.user_id,
        )
    )

    adj.status = "POSTED"
    adj.approved_by = approver.user_id
    adj.posted_at = now_utc
    db.flush()


def create_stock_adjustment(
    db: Session, actor: CurrentActor, payload: StockAdjustmentCreateRequest
) -> StockAdjustmentResponse:
    """Create a controlled stock adjustment request (Admin may post immediately; Supervisor submits for approval)."""
    if actor.role_code not in {"FACTORY_ADMIN", "PRODUCTION_SUPERVISOR"}:
        raise AuthorizationError("Only Factory Admin or Production Supervisor can request stock adjustments.")
    if payload.post_immediately and actor.role_code != "FACTORY_ADMIN":
        raise AuthorizationError(
            "Only Factory Admin can approve and post stock adjustments directly. Submit for approval instead."
        )

    if payload.adjustment_type in _NEGATIVE_ONLY_ADJUSTMENT_TYPES and payload.entered_qty > 0:
        raise DomainValidationError(
            f"Adjustment type '{payload.adjustment_type}' reduces stock and must use a negative quantity."
        )

    if payload.item_type == "MATERIAL":
        mat = inventory_repo.get_material_by_id(db, payload.item_id)
        if mat is None or not mat.is_active:
            raise NotFoundError(f"Active material {payload.item_id} was not found.")
        delta_base, multiplier, norm_uom = convert_to_base_qty(
            db,
            entered_qty=payload.entered_qty,
            entered_uom=payload.entered_uom,
            expected_dimension=mat.unit_dimension,
            expected_base_uom=mat.base_uom,
        )
        item_category = mat.material_category
        mat_id: int | None = mat.id
        ps_id: int | None = None
        lots = inventory_repo.list_open_cost_lots_for_update(db, material_id=mat.id)
        default_cost = Decimal(lots[0].unit_cost_paisa_per_base) if lots else Decimal("0.000000")
    else:
        ps_map = sales_repo.get_pack_sizes_by_ids(db, [payload.item_id])
        ps: PackSize | None = ps_map.get(payload.item_id)
        if ps is None:
            raise NotFoundError(f"Active finished SKU {payload.item_id} was not found.")
        delta_base, multiplier, norm_uom = convert_to_base_qty(
            db,
            entered_qty=payload.entered_qty,
            entered_uom=payload.entered_uom,
            expected_dimension="COUNT",
            expected_base_uom="packet",
            packets_per_carton=ps.packets_per_carton,
        )
        item_category = "FINISHED_GOOD"
        mat_id = None
        ps_id = ps.id
        lots = inventory_repo.list_open_cost_lots_for_update(db, pack_size_id=ps.id)
        default_cost = Decimal(lots[0].unit_cost_paisa_per_base) if lots else Decimal("2885.000000")

    unit_cost_base = (
        (Decimal(payload.unit_cost_paisa_per_base) / multiplier).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
        if payload.unit_cost_paisa_per_base is not None
        else default_cost
    )

    try:
        adj = StockAdjustment(
            adjustment_number=f"TMP-ADJ-{uuid4().hex[:8]}",
            item_category=item_category,
            material_id=mat_id,
            pack_size_id=ps_id,
            adjustment_type=payload.adjustment_type,
            entered_qty=payload.entered_qty.quantize(Decimal("0.001")),
            entered_uom=norm_uom,
            delta_qty_base=delta_base,
            unit_cost_paisa_per_base=unit_cost_base,
            reason=payload.reason.strip(),
            status="PENDING_APPROVAL",
            requested_by=actor.user_id,
        )
        db.add(adj)
        db.flush()
        adj.adjustment_number = f"ADJ-{datetime.now(IST).year}-{adj.id:04d}"
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="STOCK_ADJUSTMENT_CREATED",
            entity_schema="inventory",
            entity_table="stock_adjustments",
            entity_id=adj.id,
            after_state={
                "adjustment_number": adj.adjustment_number,
                "adjustment_type": adj.adjustment_type,
                "delta_qty_base": str(adj.delta_qty_base),
                "post_immediately": payload.post_immediately,
            },
            reason=adj.reason,
        )

        if payload.post_immediately:
            _apply_adjustment_posting(db, adj, approver=actor)
            record_audit_log(
                db,
                actor_user_id=actor.user_id,
                actor_role=actor.role_code,
                action="STOCK_ADJUSTMENT_POSTED",
                entity_schema="inventory",
                entity_table="stock_adjustments",
                entity_id=adj.id,
                after_state={"status": "POSTED", "delta_qty_base": str(adj.delta_qty_base)},
                reason=adj.reason,
            )

        db.commit()
    except Exception:
        db.rollback()
        raise

    return _hydrate_adjustments(db, [adj])[0]


def approve_stock_adjustment(
    db: Session, actor: CurrentActor, adjustment_id: int
) -> StockAdjustmentResponse:
    if actor.role_code != "FACTORY_ADMIN":
        raise AuthorizationError("Only Factory Admin can approve and post stock adjustments.")
    try:
        adj = inventory_repo.get_adjustment_by_id(db, adjustment_id, for_update=True)
        if adj is None:
            raise NotFoundError(f"Stock adjustment {adjustment_id} was not found.")
        _apply_adjustment_posting(db, adj, approver=actor)
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="STOCK_ADJUSTMENT_POSTED",
            entity_schema="inventory",
            entity_table="stock_adjustments",
            entity_id=adj.id,
            after_state={"status": "POSTED", "delta_qty_base": str(adj.delta_qty_base)},
            reason=adj.reason,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _hydrate_adjustments(db, [adj])[0]


def reject_stock_adjustment(
    db: Session, actor: CurrentActor, adjustment_id: int, reason: str
) -> StockAdjustmentResponse:
    if actor.role_code != "FACTORY_ADMIN":
        raise AuthorizationError("Only Factory Admin can reject stock adjustments.")
    try:
        adj = inventory_repo.get_adjustment_by_id(db, adjustment_id, for_update=True)
        if adj is None:
            raise NotFoundError(f"Stock adjustment {adjustment_id} was not found.")
        if adj.status in {"POSTED", "REJECTED"}:
            raise ConflictError(
                f"Adjustment {adj.adjustment_number} is already {adj.status}.",
                error_code="INVALID_STATE_TRANSITION",
            )
        adj.status = "REJECTED"
        adj.approved_by = actor.user_id
        adj.rejection_reason = reason.strip()
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="STOCK_ADJUSTMENT_REJECTED",
            entity_schema="inventory",
            entity_table="stock_adjustments",
            entity_id=adj.id,
            after_state={"status": "REJECTED", "rejection_reason": adj.rejection_reason},
            reason=adj.rejection_reason,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _hydrate_adjustments(db, [adj])[0]


def list_adjustments(
    db: Session, *, status: str | None = None, item_category: str | None = None
) -> list[StockAdjustmentResponse]:
    rows = inventory_repo.list_stock_adjustments(db, status=status, item_category=item_category)
    return _hydrate_adjustments(db, rows)
