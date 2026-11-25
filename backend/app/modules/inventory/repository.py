from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.inventory.models import (
    InventoryBalance,
    InventoryMovement,
    OpeningBalance,
    StockReservation,
)


def get_balances_by_pack_size_ids(
    db: Session, pack_size_ids: list[int]
) -> dict[int, InventoryBalance]:
    if not pack_size_ids:
        return {}
    stmt = select(InventoryBalance).where(InventoryBalance.pack_size_id.in_(pack_size_ids))
    rows = db.execute(stmt).scalars().all()
    return {row.pack_size_id: row for row in rows if row.pack_size_id is not None}


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
        signed_qty_base=qty_decimal,
        unit_cost_paisa_per_base=unit_cost_decimal,
        total_cost_paisa=total_cost_paisa,
        source_doc_type="OPENING_BALANCE",
        opening_balance_id=opening.id,
        created_by=created_by,
    )
    db.add(movement)
    db.flush()
    return opening
