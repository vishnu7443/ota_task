"""Production repository — deterministic data access & FIFO locking helpers."""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.modules.audit.models import VarianceAlert
from app.modules.inventory.models import CostLot, CostLotConsumption, InventoryMovement
from app.modules.production.models import (
    BomComponent,
    BomHeader,
    BomVersion,
    ProductionRun,
    ProductionVariance,
    RecipeTemplate,
)
from app.modules.sales.models import PackSize, Product

# ── Catalog & BOM Queries ───────────────────────────────────────────────────


def list_products(db: Session, *, active_only: bool = True) -> list[Product]:
    stmt = select(Product)
    if active_only:
        stmt = stmt.where(Product.is_active.is_(True))
    stmt = stmt.order_by(Product.name.asc())
    return list(db.execute(stmt).scalars().all())


def get_product(db: Session, product_id: int) -> Product | None:
    return db.execute(select(Product).where(Product.id == product_id)).scalar_one_or_none()


def list_pack_sizes(db: Session, *, active_only: bool = True) -> list[PackSize]:
    stmt = select(PackSize)
    if active_only:
        stmt = stmt.where(PackSize.is_active.is_(True))
    stmt = stmt.order_by(PackSize.display_name.asc())
    return list(db.execute(stmt).scalars().all())


def list_recipe_templates(db: Session) -> list[RecipeTemplate]:
    stmt = select(RecipeTemplate).where(RecipeTemplate.is_active.is_(True)).order_by(RecipeTemplate.name.asc())
    return list(db.execute(stmt).scalars().all())


def get_recipe_template(db: Session, template_id: int) -> RecipeTemplate | None:
    return db.execute(
        select(RecipeTemplate).where(RecipeTemplate.id == template_id)
    ).scalar_one_or_none()


def get_bom_header_by_pack_size(
    db: Session, pack_size_id: int, *, for_update: bool = False
) -> BomHeader | None:
    stmt = select(BomHeader).where(BomHeader.pack_size_id == pack_size_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def get_bom_header(
    db: Session, header_id: int, *, for_update: bool = False
) -> BomHeader | None:
    stmt = select(BomHeader).where(BomHeader.id == header_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def get_bom_version(
    db: Session, version_id: int, *, for_update: bool = False
) -> BomVersion | None:
    stmt = (
        select(BomVersion)
        .options(selectinload(BomVersion.components))
        .execution_options(populate_existing=True)
        .where(BomVersion.id == version_id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def get_active_bom_version_for_pack_size(db: Session, pack_size_id: int) -> BomVersion | None:
    header = get_bom_header_by_pack_size(db, pack_size_id)
    if header is None or header.active_version_id is None:
        return None
    return get_bom_version(db, header.active_version_id)


def list_bom_versions_for_header(db: Session, header_id: int) -> list[BomVersion]:
    stmt = (
        select(BomVersion)
        .options(selectinload(BomVersion.components))
        .where(BomVersion.bom_header_id == header_id)
        .order_by(BomVersion.version_no.desc())
    )
    return list(db.execute(stmt).scalars().all())


def list_all_bom_headers(db: Session) -> list[BomHeader]:
    return list(db.execute(select(BomHeader).order_by(BomHeader.id.asc())).scalars().all())


def get_next_version_no(db: Session, header_id: int) -> int:
    stmt = select(func.coalesce(func.max(BomVersion.version_no), 0)).where(
        BomVersion.bom_header_id == header_id
    )
    return int(db.execute(stmt).scalar_one()) + 1


def count_runs_by_bom_version_ids(db: Session, version_ids: list[int]) -> dict[int, int]:
    if not version_ids:
        return {}
    stmt = (
        select(ProductionRun.bom_version_id, func.count(ProductionRun.id))
        .where(ProductionRun.bom_version_id.in_(version_ids))
        .group_by(ProductionRun.bom_version_id)
    )
    return {row[0]: int(row[1]) for row in db.execute(stmt).all()}


def delete_components_for_version(db: Session, version_id: int) -> None:
    rows = db.execute(
        select(BomComponent).where(BomComponent.bom_version_id == version_id)
    ).scalars().all()
    for row in rows:
        db.delete(row)
    db.flush()


# ── Production Run Queries ──────────────────────────────────────────────────


def get_production_run(db: Session, run_id: int, *, for_update: bool = False) -> ProductionRun | None:
    stmt = (
        select(ProductionRun)
        .options(
            selectinload(ProductionRun.material_issues),
            selectinload(ProductionRun.outputs),
            selectinload(ProductionRun.wastages),
            selectinload(ProductionRun.variances),
        )
        .execution_options(populate_existing=True)
        .where(ProductionRun.id == run_id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def list_production_runs(
    db: Session,
    *,
    status: str | None = None,
    pack_size_id: int | None = None,
    limit: int = 100,
) -> list[ProductionRun]:
    stmt = (
        select(ProductionRun)
        .options(
            selectinload(ProductionRun.material_issues),
            selectinload(ProductionRun.wastages),
            selectinload(ProductionRun.variances),
        )
    )
    if status:
        stmt = stmt.where(ProductionRun.status == status)
    if pack_size_id:
        stmt = stmt.where(ProductionRun.pack_size_id == pack_size_id)
    stmt = stmt.order_by(ProductionRun.run_date.desc(), ProductionRun.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def list_movements_for_run(db: Session, run_id: int) -> list[InventoryMovement]:
    stmt = (
        select(InventoryMovement)
        .where(InventoryMovement.production_run_id == run_id)
        .order_by(InventoryMovement.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def list_alerts(
    db: Session, *, status: str | None = None, run_id: int | None = None, limit: int = 100
) -> list[VarianceAlert]:
    stmt = select(VarianceAlert)
    if status:
        stmt = stmt.where(VarianceAlert.status == status)
    if run_id:
        stmt = stmt.where(VarianceAlert.production_run_id == run_id)
    stmt = stmt.order_by(VarianceAlert.created_at.desc(), VarianceAlert.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def get_alert(db: Session, alert_id: int, *, for_update: bool = False) -> VarianceAlert | None:
    stmt = select(VarianceAlert).where(VarianceAlert.id == alert_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def list_variances_for_run(db: Session, run_id: int) -> list[ProductionVariance]:
    stmt = (
        select(ProductionVariance)
        .where(ProductionVariance.production_run_id == run_id)
        .order_by(ProductionVariance.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


# ── FIFO Cost Lot Consumption & Attribution ─────────────────────────────────


def consume_fifo_lots(
    db: Session,
    *,
    material_id: int | None = None,
    pack_size_id: int | None = None,
    qty_base: Decimal,
) -> tuple[int, list[tuple[CostLot, Decimal, Decimal, int]]]:
    """Consume qty from open FIFO lots (`received_at ASC, id ASC FOR UPDATE`).

    Returns `(total_cost_paisa, [(lot, taken_qty_base, unit_cost_base, lot_cost_paisa), ...])`.
    """
    stmt = select(CostLot).where(CostLot.remaining_qty_base > 0)
    if material_id is not None:
        stmt = stmt.where(CostLot.material_id == material_id)
    if pack_size_id is not None:
        stmt = stmt.where(CostLot.pack_size_id == pack_size_id)
    stmt = stmt.order_by(CostLot.received_at.asc(), CostLot.id.asc()).with_for_update()
    lots = list(db.execute(stmt).scalars().all())

    remaining = Decimal(qty_base).quantize(Decimal("0.001"))
    total_cost_paisa = 0
    consumed: list[tuple[CostLot, Decimal, Decimal, int]] = []

    for lot in lots:
        if remaining <= 0:
            break
        take = min(Decimal(lot.remaining_qty_base), remaining).quantize(Decimal("0.001"))
        unit_cost_base = Decimal(lot.unit_cost_paisa_per_base).quantize(Decimal("0.000001"))
        lot_cost = int((take * unit_cost_base).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        lot.remaining_qty_base = (Decimal(lot.remaining_qty_base) - take).quantize(Decimal("0.001"))
        total_cost_paisa += lot_cost
        consumed.append((lot, take, unit_cost_base, lot_cost))
        remaining = (remaining - take).quantize(Decimal("0.001"))

    return total_cost_paisa, consumed


def record_movement_with_lot_consumptions(
    db: Session,
    *,
    movement: InventoryMovement,
    consumed_lots: list[tuple[CostLot, Decimal, Decimal, int]],
) -> InventoryMovement:
    """Persist InventoryMovement and create CostLotConsumption junction entries."""
    db.add(movement)
    db.flush()
    for lot, take, unit_cost_base, lot_cost in consumed_lots:
        db.add(
            CostLotConsumption(
                inventory_movement_id=movement.id,
                cost_lot_id=lot.id,
                consumed_qty_base=take,
                unit_cost_paisa_per_base=unit_cost_base,
                cost_paisa=lot_cost,
            )
        )
    db.flush()
    return movement
