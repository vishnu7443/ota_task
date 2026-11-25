from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.inventory.models import (
    CostLot,
    InventoryBalance,
    InventoryMovement,
    Material,
    OpeningBalance,
    StockAdjustment,
    StockReservation,
)
from app.modules.sales.models import PackSize


def get_balances_by_pack_size_ids(
    db: Session, pack_size_ids: list[int]
) -> dict[int, InventoryBalance]:
    if not pack_size_ids:
        return {}
    stmt = select(InventoryBalance).where(InventoryBalance.pack_size_id.in_(pack_size_ids))
    rows = db.execute(stmt).scalars().all()
    return {row.pack_size_id: row for row in rows if row.pack_size_id is not None}


def get_balances_by_material_ids(
    db: Session, material_ids: list[int]
) -> dict[int, InventoryBalance]:
    if not material_ids:
        return {}
    stmt = select(InventoryBalance).where(InventoryBalance.material_id.in_(material_ids))
    rows = db.execute(stmt).scalars().all()
    return {row.material_id: row for row in rows if row.material_id is not None}


def lock_balances_by_pack_size_ids(
    db: Session, pack_size_ids: list[int]
) -> dict[int, InventoryBalance]:
    """Acquire deterministic row locks (ORDER BY id ASC FOR UPDATE) to prevent deadlocks and overselling."""
    unique_ids = sorted(set(pack_size_ids))
    if not unique_ids:
        return {}
    stmt = (
        select(InventoryBalance)
        .where(InventoryBalance.pack_size_id.in_(unique_ids))
        .order_by(InventoryBalance.id.asc())
        .with_for_update()
    )
    rows = db.execute(stmt).scalars().all()
    return {row.pack_size_id: row for row in rows if row.pack_size_id is not None}


def lock_balances_by_material_ids(
    db: Session, material_ids: list[int]
) -> dict[int, InventoryBalance]:
    """Acquire deterministic row locks (ORDER BY id ASC FOR UPDATE) on material balances."""
    unique_ids = sorted(set(material_ids))
    if not unique_ids:
        return {}
    stmt = (
        select(InventoryBalance)
        .where(InventoryBalance.material_id.in_(unique_ids))
        .order_by(InventoryBalance.id.asc())
        .with_for_update()
    )
    rows = db.execute(stmt).scalars().all()
    return {row.material_id: row for row in rows if row.material_id is not None}


def list_active_reservations_for_order_for_update(
    db: Session, order_id: int
) -> list[StockReservation]:
    stmt = (
        select(StockReservation)
        .where(StockReservation.sales_order_id == order_id, StockReservation.status == "ACTIVE")
        .order_by(StockReservation.id.asc())
        .with_for_update()
    )
    return list(db.execute(stmt).scalars().all())


def list_reservations_for_order(db: Session, order_id: int) -> list[StockReservation]:
    stmt = (
        select(StockReservation)
        .where(StockReservation.sales_order_id == order_id)
        .order_by(StockReservation.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def get_opening_balance_by_batch_and_pack(
    db: Session, batch_ref: str, pack_size_id: int
) -> OpeningBalance | None:
    stmt = select(OpeningBalance).where(
        OpeningBalance.batch_ref == batch_ref,
        OpeningBalance.pack_size_id == pack_size_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def get_opening_balance_by_batch_and_material(
    db: Session, batch_ref: str, material_id: int
) -> OpeningBalance | None:
    stmt = select(OpeningBalance).where(
        OpeningBalance.batch_ref == batch_ref,
        OpeningBalance.material_id == material_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def create_opening_fg_ledger_entry(
    db: Session,
    *,
    batch_ref: str,
    pack_size_id: int,
    opening_qty_pkts: int,
    unit_cost_paisa: int,
    as_of_date: date,
    created_by: int,
) -> OpeningBalance:
    existing = get_opening_balance_by_batch_and_pack(db, batch_ref, pack_size_id)
    if existing is not None:
        return existing

    qty_decimal = Decimal(opening_qty_pkts).quantize(Decimal("0.001"))
    unit_cost_decimal = Decimal(unit_cost_paisa).quantize(Decimal("0.000001"))
    total_cost_paisa = opening_qty_pkts * unit_cost_paisa

    opening = OpeningBalance(
        batch_ref=batch_ref,
        item_category="FINISHED_GOOD",
        pack_size_id=pack_size_id,
        opening_qty_base=qty_decimal,
        unit_cost_paisa_per_base=unit_cost_decimal,
        as_of_date=as_of_date,
        created_by=created_by,
    )
    db.add(opening)
    db.flush()

    movement = InventoryMovement(
        item_category="FINISHED_GOOD",
        pack_size_id=pack_size_id,
        movement_type="OPENING",
        entered_qty=qty_decimal,
        entered_uom="packet",
        signed_qty_base=qty_decimal,
        unit_cost_paisa_per_base=unit_cost_decimal,
        total_cost_paisa=total_cost_paisa,
        source_doc_type="OPENING_BALANCE",
        reference_code=batch_ref,
        notes=f"Opening finished goods balance ({batch_ref})",
        opening_balance_id=opening.id,
        created_by=created_by,
    )
    db.add(movement)
    db.add(
        CostLot(
            item_category="FINISHED_GOOD",
            pack_size_id=pack_size_id,
            source_doc_type="OPENING_BALANCE",
            source_doc_id=opening.id,
            batch_code=batch_ref,
            original_qty_base=qty_decimal,
            remaining_qty_base=qty_decimal,
            unit_cost_paisa_per_base=unit_cost_decimal,
        )
    )
    db.flush()
    return opening


def create_opening_material_ledger_entry(
    db: Session,
    *,
    batch_ref: str,
    material: Material,
    opening_qty_base: Decimal,
    entered_qty: Decimal,
    entered_uom: str,
    unit_cost_paisa_per_base: Decimal,
    total_cost_paisa: int,
    as_of_date: date,
    created_by: int,
) -> OpeningBalance:
    existing = get_opening_balance_by_batch_and_material(db, batch_ref, material.id)
    if existing is not None:
        return existing

    qty_base_q = opening_qty_base.quantize(Decimal("0.001"))
    cost_q = unit_cost_paisa_per_base.quantize(Decimal("0.000001"))

    opening = OpeningBalance(
        batch_ref=batch_ref,
        item_category=material.material_category,
        material_id=material.id,
        opening_qty_base=qty_base_q,
        unit_cost_paisa_per_base=cost_q,
        as_of_date=as_of_date,
        created_by=created_by,
    )
    db.add(opening)
    db.flush()

    db.add(
        InventoryMovement(
            item_category=material.material_category,
            material_id=material.id,
            movement_type="OPENING",
            entered_qty=entered_qty.quantize(Decimal("0.001")),
            entered_uom=entered_uom,
            signed_qty_base=qty_base_q,
            unit_cost_paisa_per_base=cost_q,
            total_cost_paisa=total_cost_paisa,
            source_doc_type="OPENING_BALANCE",
            reference_code=batch_ref,
            notes=f"Opening stock ({batch_ref})",
            opening_balance_id=opening.id,
            created_by=created_by,
        )
    )
    db.add(
        CostLot(
            item_category=material.material_category,
            material_id=material.id,
            source_doc_type="OPENING_BALANCE",
            source_doc_id=opening.id,
            batch_code=batch_ref,
            original_qty_base=qty_base_q,
            remaining_qty_base=qty_base_q,
            unit_cost_paisa_per_base=cost_q,
        )
    )
    db.flush()
    return opening


def list_all_materials(
    db: Session,
    *,
    category: str | None = None,
    active_only: bool = True,
    search: str | None = None,
) -> list[Material]:
    stmt = select(Material)
    if active_only:
        stmt = stmt.where(Material.is_active.is_(True))
    if category:
        stmt = stmt.where(Material.material_category == category)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(or_(Material.name.ilike(pattern), Material.code.ilike(pattern)))
    stmt = stmt.order_by(Material.material_category.asc(), Material.name.asc())
    return list(db.execute(stmt).scalars().all())


def list_all_active_pack_sizes(db: Session, *, search: str | None = None) -> list[PackSize]:
    stmt = select(PackSize).where(PackSize.is_active.is_(True))
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(or_(PackSize.display_name.ilike(pattern), PackSize.sku_code.ilike(pattern)))
    stmt = stmt.order_by(PackSize.display_name.asc())
    return list(db.execute(stmt).scalars().all())


def get_material_by_id(db: Session, material_id: int) -> Material | None:
    return db.execute(select(Material).where(Material.id == material_id)).scalar_one_or_none()


def list_open_cost_lots_for_update(
    db: Session, *, material_id: int | None = None, pack_size_id: int | None = None
) -> list[CostLot]:
    stmt = select(CostLot).where(CostLot.remaining_qty_base > 0)
    if material_id is not None:
        stmt = stmt.where(CostLot.material_id == material_id)
    if pack_size_id is not None:
        stmt = stmt.where(CostLot.pack_size_id == pack_size_id)
    stmt = stmt.order_by(CostLot.received_at.asc(), CostLot.id.asc()).with_for_update()
    return list(db.execute(stmt).scalars().all())


def list_all_open_cost_lots(db: Session) -> list[CostLot]:
    stmt = select(CostLot).where(CostLot.remaining_qty_base > 0)
    return list(db.execute(stmt).scalars().all())


def list_inventory_movements(
    db: Session,
    *,
    item_category: str | None = None,
    material_id: int | None = None,
    pack_size_id: int | None = None,
    movement_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 200,
) -> list[InventoryMovement]:
    stmt = select(InventoryMovement)
    if item_category:
        stmt = stmt.where(InventoryMovement.item_category == item_category)
    if material_id is not None:
        stmt = stmt.where(InventoryMovement.material_id == material_id)
    if pack_size_id is not None:
        stmt = stmt.where(InventoryMovement.pack_size_id == pack_size_id)
    if movement_type:
        stmt = stmt.where(InventoryMovement.movement_type == movement_type)
    if date_from is not None:
        stmt = stmt.where(InventoryMovement.occurred_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(InventoryMovement.occurred_at <= date_to)
    stmt = stmt.order_by(InventoryMovement.occurred_at.desc(), InventoryMovement.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def list_all_movements_for_aggregation(db: Session) -> list[InventoryMovement]:
    return list(db.execute(select(InventoryMovement)).scalars().all())


def get_adjustment_by_id(
    db: Session, adjustment_id: int, *, for_update: bool = False
) -> StockAdjustment | None:
    stmt = select(StockAdjustment).where(StockAdjustment.id == adjustment_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def list_stock_adjustments(
    db: Session,
    *,
    status: str | None = None,
    item_category: str | None = None,
    limit: int = 100,
) -> list[StockAdjustment]:
    stmt = select(StockAdjustment)
    if status:
        stmt = stmt.where(StockAdjustment.status == status)
    if item_category:
        stmt = stmt.where(StockAdjustment.item_category == item_category)
    stmt = stmt.order_by(StockAdjustment.requested_at.desc(), StockAdjustment.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def count_pending_adjustments(db: Session) -> int:
    stmt = select(func.count(StockAdjustment.id)).where(
        StockAdjustment.status.in_(["DRAFT", "PENDING_APPROVAL"])
    )
    return int(db.execute(stmt).scalar_one())
