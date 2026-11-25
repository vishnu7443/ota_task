"""Phase 9 Product Costing Engine — Direct FIFO consumption, Overheads, Monthly Pool Allocation & Snapshots.

Preserves historical inventory_movements unmodified while recording versioned, immutable
costing snapshots in costing.production_cost_summaries.
"""

from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.modules.audit.service import record_audit_log
from app.modules.costing.models import ProductionCostSummary, ProductionOverhead
from app.modules.costing.schemas import (
    AddMonthlyPoolOverheadRequest,
    AddRunOverheadRequest,
    CostingDashboardOut,
    FinalizeRunCostingRequest,
    MaterialCostLineOut,
    ProductCostAggregateOut,
    ProductionCostSummaryOut,
    ProductionOverheadOut,
    RunCostingDetailOut,
    VoidOverheadRequest,
)
from app.modules.iam.models import CompanyProfile, User
from app.modules.iam.schemas import CurrentActor
from app.modules.inventory.models import CostLot, CostLotConsumption, InventoryMovement, Material
from app.modules.production.models import ProductionRun
from app.modules.sales.models import PackSize

IST = ZoneInfo("Asia/Kolkata")
_COST_OPERATOR_ROLES = {"FACTORY_ADMIN", "PRODUCTION_SUPERVISOR"}
_COST_VIEWER_ROLES = {"FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "ACCOUNTANT_AUDITOR", "OWNER"}


def _require_cost_operator(actor: CurrentActor, action: str) -> None:
    if actor.role_code not in _COST_OPERATOR_ROLES:
        raise AuthorizationError(f"Only Factory Admin or Production Supervisor can {action}.")


def _require_cost_viewer(actor: CurrentActor, action: str) -> None:
    if actor.role_code not in _COST_VIEWER_ROLES:
        raise AuthorizationError(f"Your role is not permitted to {action}.")


def _get_company(db: Session) -> CompanyProfile:
    cp = db.execute(select(CompanyProfile).limit(1)).scalar_one_or_none()
    if cp is None:
        raise DomainValidationError("Company profile is not configured.")
    return cp


def _users_map(db: Session, ids: set[int]) -> dict[int, User]:
    clean = {i for i in ids if i is not None}
    if not clean:
        return {}
    return {u.id: u for u in db.execute(select(User).where(User.id.in_(clean))).scalars().all()}


def _hydrate_overhead(ov: ProductionOverhead, users: dict[int, User]) -> ProductionOverheadOut:
    return ProductionOverheadOut(
        id=ov.id,
        production_run_id=ov.production_run_id,
        period_month=ov.period_month,
        overhead_type=ov.overhead_type,
        allocation_scope=ov.allocation_scope,
        amount_paisa=int(ov.amount_paisa),
        notes=ov.notes,
        is_voided=ov.is_voided,
        void_reason=ov.void_reason,
        voided_by_name=(
            users[ov.voided_by].full_name if ov.voided_by and ov.voided_by in users else None
        ),
        voided_at=ov.voided_at,
        recorded_by_name=users[ov.recorded_by].full_name if ov.recorded_by in users else "System",
        recorded_at=ov.recorded_at,
    )


def _hydrate_summary(
    pcs: ProductionCostSummary,
    *,
    run: ProductionRun,
    ps: PackSize,
    users: dict[int, User],
) -> ProductionCostSummaryOut:
    snap = pcs.cost_breakdown_snapshot or {}
    lines_raw = snap.get("material_lines", [])
    material_lines = [MaterialCostLineOut(**ln) for ln in lines_raw]

    planned_per_pkt_int = int(
        Decimal(pcs.planned_cost_per_packet_paisa).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    )
    pkt_var = (
        int(pcs.cost_per_packet_paisa) - planned_per_pkt_int
        if pcs.cost_per_packet_paisa is not None and pcs.planned_total_cost_paisa > 0
        else None
    )

    return ProductionCostSummaryOut(
        id=pcs.id,
        production_run_id=pcs.production_run_id,
        run_number=run.run_number,
        run_date=run.run_date,
        pack_size_id=run.pack_size_id,
        sku_code=ps.sku_code,
        display_name=ps.display_name,
        snapshot_version=pcs.snapshot_version,
        is_current=pcs.is_current,
        cost_status=pcs.cost_status,
        valuation_method=pcs.valuation_method,
        planned_raw_cost_paisa=int(pcs.planned_raw_cost_paisa),
        planned_pkg_cost_paisa=int(pcs.planned_pkg_cost_paisa),
        planned_overhead_cost_paisa=int(pcs.planned_overhead_cost_paisa),
        planned_total_cost_paisa=int(pcs.planned_total_cost_paisa),
        planned_cost_per_packet_paisa=Decimal(pcs.planned_cost_per_packet_paisa),
        raw_material_cost_paisa=int(pcs.raw_material_cost_paisa),
        good_packaging_cost_paisa=int(pcs.good_packaging_cost_paisa),
        damaged_packaging_cost_paisa=int(pcs.damaged_packaging_cost_paisa),
        packaging_cost_paisa=int(pcs.packaging_cost_paisa),
        raw_wastage_cost_paisa=int(pcs.raw_wastage_cost_paisa),
        rejected_output_cost_impact_paisa=int(pcs.rejected_output_cost_impact_paisa),
        direct_labour_paisa=int(pcs.direct_labour_paisa),
        gas_power_paisa=int(pcs.gas_power_paisa),
        other_direct_overhead_paisa=int(pcs.other_direct_overhead_paisa),
        direct_overhead_paisa=int(pcs.direct_overhead_paisa),
        allocated_overhead_paisa=int(pcs.allocated_overhead_paisa),
        total_cost_paisa=int(pcs.total_cost_paisa),
        expected_output_pkts=pcs.expected_output_pkts,
        good_packets=pcs.good_packets,
        rejected_packets=pcs.rejected_packets,
        cost_per_packet_paisa=int(pcs.cost_per_packet_paisa) if pcs.cost_per_packet_paisa is not None else None,
        exact_cost_per_packet_paisa=(
            Decimal(pcs.exact_cost_per_packet_paisa) if pcs.exact_cost_per_packet_paisa is not None else None
        ),
        selling_price_snapshot_paisa=int(pcs.selling_price_snapshot_paisa),
        gross_margin_per_pkt_paisa=(
            int(pcs.gross_margin_per_pkt_paisa) if pcs.gross_margin_per_pkt_paisa is not None else None
        ),
        gross_margin_pct=Decimal(pcs.gross_margin_pct) if pcs.gross_margin_pct is not None else None,
        material_variance_paisa=int(pcs.material_variance_paisa),
        cost_per_pkt_variance_paisa=pkt_var,
        material_lines=material_lines,
        notes=pcs.notes,
        computed_by_name=users[pcs.computed_by].full_name if pcs.computed_by in users else "System",
        computed_at=pcs.computed_at,
    )


def _compute_monthly_pool_share_for_run(db: Session, run: ProductionRun) -> int:
    """Allocate monthly factory overhead pools deterministically across completed/posted runs by good packets."""
    period_month = run.run_date.strftime("%Y-%m")
    pools = (
        db.execute(
            select(ProductionOverhead).where(
                ProductionOverhead.allocation_scope == "MONTHLY_POOL",
                ProductionOverhead.period_month == period_month,
                ProductionOverhead.is_voided.is_(False),
            )
        )
        .scalars()
        .all()
    )
    total_pool = sum(int(p.amount_paisa) for p in pools)
    if total_pool <= 0:
        return 0

    month_start = date(run.run_date.year, run.run_date.month, 1)
    if run.run_date.month == 12:
        next_month = date(run.run_date.year + 1, 1, 1)
    else:
        next_month = date(run.run_date.year, run.run_date.month + 1, 1)

    eligible_runs = (
        db.execute(
            select(ProductionRun)
            .where(
                ProductionRun.run_date >= month_start,
                ProductionRun.run_date < next_month,
                ProductionRun.status.in_(["COMPLETED", "POSTED"]),
                ProductionRun.actual_good_output_pkts > 0,
            )
            .order_by(ProductionRun.id.asc())
        )
        .scalars()
        .all()
    )
    total_pkts = sum(r.actual_good_output_pkts for r in eligible_runs)
    if total_pkts <= 0 or run.actual_good_output_pkts <= 0:
        return 0

    # Exact largest-remainder apportionment across runs so SUM(shares) == total_pool to the single paisa
    exact_rows: list[tuple[int, int, Decimal]] = []
    floor_sum = 0
    for er in eligible_runs:
        exact = (Decimal(total_pool) * Decimal(er.actual_good_output_pkts)) / Decimal(total_pkts)
        floored = int(exact)
        rem = exact - Decimal(floored)
        exact_rows.append((er.id, floored, rem))
        floor_sum += floored

    leftover = total_pool - floor_sum
    if leftover > 0:
        # Deterministic tie-break: largest remainder desc, then earliest run_id asc
        ranked = sorted(exact_rows, key=lambda x: (-x[2], x[0]))
        bonus_ids = {r[0] for r in ranked[:leftover]}
    else:
        bonus_ids = set()

    for rid, floored, _ in exact_rows:
        if rid == run.id:
            return floored + (1 if rid in bonus_ids else 0)
    return 0


def _material_fifo_unit_cost_for_planned(
    db: Session,
    *,
    run_id: int,
    material_id: int,
) -> Decimal:
    """Resolve persisted lot rate for planned BOM costing from consumed lots on run or earliest CostLot."""
    clc_stmt = (
        select(CostLotConsumption)
        .join(InventoryMovement, InventoryMovement.id == CostLotConsumption.inventory_movement_id)
        .join(CostLot, CostLot.id == CostLotConsumption.cost_lot_id)
        .where(
            InventoryMovement.production_run_id == run_id,
            CostLot.material_id == material_id,
        )
        .order_by(CostLotConsumption.id.asc())
    )
    rows = db.execute(clc_stmt).scalars().all()
    if rows:
        # Planned standard quantity consumes oldest FIFO lot rate first
        return Decimal(rows[0].unit_cost_paisa_per_base)

    lot = (
        db.execute(
            select(CostLot)
            .where(CostLot.material_id == material_id)
            .order_by(CostLot.received_at.asc(), CostLot.id.asc())
            .limit(1)
        )
        .scalar_one_or_none()
    )
    return Decimal(lot.unit_cost_paisa_per_base) if lot else Decimal(0)


def create_cost_snapshot_for_run(
    db: Session,
    *,
    actor: CurrentActor,
    run: ProductionRun,
    cost_status: str = "FINALIZED",
    notes: str | None = None,
) -> ProductionCostSummary:
    """Compute & persist a new immutable versioned ProductionCostSummary from actual DB records."""
    if run.status not in {"COMPLETED", "POSTED"}:
        raise ConflictError(
            f"Run {run.run_number} is in status '{run.status}'; costing requires COMPLETED or POSTED production.",
            error_code="INVALID_STATE_TRANSITION",
        )

    company = _get_company(db)
    ps = db.execute(select(PackSize).where(PackSize.id == run.pack_size_id)).scalar_one()

    # Load actual ledger movements & consumptions recorded for this run
    movements = (
        db.execute(
            select(InventoryMovement)
            .where(InventoryMovement.production_run_id == run.id)
            .order_by(InventoryMovement.id.asc())
        )
        .scalars()
        .all()
    )
    dmg_cost_by_mat: dict[int, int] = {}
    for m in movements:
        if m.material_id is not None and m.movement_type == "PACKAGING_DAMAGE_OUT":
            dmg_cost_by_mat[m.material_id] = dmg_cost_by_mat.get(m.material_id, 0) + int(m.total_cost_paisa)

    mat_ids = [mi.material_id for mi in run.material_issues]
    mats = (
        {m.id: m for m in db.execute(select(Material).where(Material.id.in_(mat_ids))).scalars().all()}
        if mat_ids
        else {}
    )

    planned_raw_cost = 0
    planned_pkg_cost = 0
    raw_mat_cost = 0
    good_pkg_cost = 0
    dmg_pkg_cost = 0
    raw_wastage_cost = 0
    material_lines_payload: list[dict[str, Any]] = []

    for mi in sorted(run.material_issues, key=lambda x: x.id):
        mat = mats[mi.material_id]
        planned_qty = Decimal(mi.planned_qty_base).quantize(Decimal("0.001"))
        actual_qty = Decimal(mi.actual_consumed_qty_base).quantize(Decimal("0.001"))
        dmg_qty = Decimal(mi.damaged_qty_base).quantize(Decimal("0.001"))
        wasted_qty = Decimal(mi.wasted_qty_base).quantize(Decimal("0.001"))
        returned_qty = Decimal(mi.returned_unused_qty_base).quantize(Decimal("0.001"))

        actual_cost = int(mi.cost_absorbed_paisa)
        unit_rate_plan = _material_fifo_unit_cost_for_planned(db, run_id=run.id, material_id=mat.id)
        planned_cost = int((planned_qty * unit_rate_plan).quantize(Decimal(1), rounding=ROUND_HALF_UP))

        if mi.issue_phase == "RAW_ISSUE":
            planned_raw_cost += planned_cost
            raw_mat_cost += actual_cost
            avg_uc = (
                (Decimal(actual_cost) / actual_qty)
                if actual_qty > 0
                else unit_rate_plan
            )
            w_cost = int((wasted_qty * avg_uc).quantize(Decimal(1), rounding=ROUND_HALF_UP)) if wasted_qty > 0 else 0
            raw_wastage_cost += w_cost
            d_cost = 0
        else:
            planned_pkg_cost += planned_cost
            if mat.id in dmg_cost_by_mat:
                d_cost = dmg_cost_by_mat[mat.id]
            elif dmg_qty > 0 and actual_qty > 0:
                d_cost = int(
                    ((Decimal(actual_cost) * dmg_qty) / actual_qty).quantize(Decimal(1), rounding=ROUND_HALF_UP)
                )
            else:
                d_cost = 0
            dmg_pkg_cost += d_cost
            good_pkg_cost += max(0, actual_cost - d_cost)
            w_cost = 0

        material_lines_payload.append(
            {
                "material_id": mat.id,
                "material_code": mat.code,
                "material_name": mat.name,
                "issue_phase": mi.issue_phase,
                "display_uom": mat.display_uom,
                "planned_qty_base": str(planned_qty),
                "actual_consumed_qty_base": str(actual_qty),
                "damaged_qty_base": str(dmg_qty),
                "wasted_qty_base": str(wasted_qty),
                "returned_unused_qty_base": str(returned_qty),
                "planned_cost_paisa": planned_cost,
                "actual_cost_paisa": actual_cost,
                "damaged_cost_paisa": d_cost,
                "wasted_cost_paisa": w_cost,
                "cost_variance_paisa": actual_cost - planned_cost,
            }
        )

    packaging_cost = good_pkg_cost + dmg_pkg_cost

    # Active Direct Overheads for this run
    direct_ovs = (
        db.execute(
            select(ProductionOverhead)
            .where(
                ProductionOverhead.production_run_id == run.id,
                ProductionOverhead.allocation_scope == "DIRECT_RUN",
                ProductionOverhead.is_voided.is_(False),
            )
            .order_by(ProductionOverhead.id.asc())
        )
        .scalars()
        .all()
    )
    direct_labour = sum(int(o.amount_paisa) for o in direct_ovs if o.overhead_type == "DIRECT_LABOUR")
    gas_power = sum(int(o.amount_paisa) for o in direct_ovs if o.overhead_type == "GAS_POWER")
    other_direct = sum(
        int(o.amount_paisa)
        for o in direct_ovs
        if o.overhead_type not in {"DIRECT_LABOUR", "GAS_POWER"}
    )
    direct_overhead = direct_labour + gas_power + other_direct
    allocated_overhead = _compute_monthly_pool_share_for_run(db, run)

    total_cost = raw_mat_cost + packaging_cost + direct_overhead + allocated_overhead
    planned_overhead = direct_overhead + allocated_overhead
    planned_total = planned_raw_cost + planned_pkg_cost + planned_overhead
    planned_unit = (
        (Decimal(planned_total) / Decimal(run.expected_output_pkts)).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
        if run.expected_output_pkts > 0
        else Decimal("0.000000")
    )

    good_pkts = run.actual_good_output_pkts
    rej_pkts = run.rejected_output_pkts
    tot_produced = good_pkts + rej_pkts
    rejected_impact = (
        int(((Decimal(total_cost) * Decimal(rej_pkts)) / Decimal(tot_produced)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if tot_produced > 0 and rej_pkts > 0
        else 0
    )

    if good_pkts > 0:
        exact_unit = (Decimal(total_cost) / Decimal(good_pkts)).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
        unit_paisa = int(exact_unit.quantize(Decimal(1), rounding=ROUND_HALF_UP))
        selling_paisa = int(ps.base_selling_price_paisa)
        margin_paisa = selling_paisa - unit_paisa
        margin_pct = (
            ((Decimal(margin_paisa) / Decimal(selling_paisa)) * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if selling_paisa > 0
            else None
        )
    else:
        exact_unit = None
        unit_paisa = None
        selling_paisa = int(ps.base_selling_price_paisa)
        margin_paisa = None
        margin_pct = None

    mat_variance = (raw_mat_cost + packaging_cost) - (planned_raw_cost + planned_pkg_cost)

    # Supersede previous current snapshot cleanly (trigger permits ONLY is_current TRUE -> FALSE!)
    prev_current = (
        db.execute(
            select(ProductionCostSummary)
            .where(
                ProductionCostSummary.production_run_id == run.id,
                ProductionCostSummary.is_current.is_(True),
            )
            .with_for_update()
        )
        .scalar_one_or_none()
    )
    next_ver = 1
    if prev_current is not None:
        next_ver = prev_current.snapshot_version + 1
        prev_current.is_current = False
        db.flush()

    snapshot_json: dict[str, Any] = {
        "run_number": run.run_number,
        "sku_code": ps.sku_code,
        "valuation_method": company.valuation_method,
        "planned_raw_cost_paisa": planned_raw_cost,
        "planned_pkg_cost_paisa": planned_pkg_cost,
        "planned_overhead_cost_paisa": planned_overhead,
        "raw_material_cost_paisa": raw_mat_cost,
        "good_packaging_cost_paisa": good_pkg_cost,
        "damaged_packaging_cost_paisa": dmg_pkg_cost,
        "raw_wastage_cost_paisa": raw_wastage_cost,
        "rejected_output_cost_impact_paisa": rejected_impact,
        "direct_labour_paisa": direct_labour,
        "gas_power_paisa": gas_power,
        "other_direct_overhead_paisa": other_direct,
        "allocated_overhead_paisa": allocated_overhead,
        "total_cost_paisa": total_cost,
        "good_packets": good_pkts,
        "cost_per_packet_paisa": unit_paisa,
        "material_lines": material_lines_payload,
    }

    new_summary = ProductionCostSummary(
        production_run_id=run.id,
        snapshot_version=next_ver,
        is_current=True,
        cost_status=cost_status,
        valuation_method=company.valuation_method,
        planned_raw_cost_paisa=planned_raw_cost,
        planned_pkg_cost_paisa=planned_pkg_cost,
        planned_overhead_cost_paisa=planned_overhead,
        planned_total_cost_paisa=planned_total,
        planned_cost_per_packet_paisa=planned_unit,
        raw_material_cost_paisa=raw_mat_cost,
        good_packaging_cost_paisa=good_pkg_cost,
        damaged_packaging_cost_paisa=dmg_pkg_cost,
        packaging_cost_paisa=packaging_cost,
        raw_wastage_cost_paisa=raw_wastage_cost,
        rejected_output_cost_impact_paisa=rejected_impact,
        direct_labour_paisa=direct_labour,
        gas_power_paisa=gas_power,
        other_direct_overhead_paisa=other_direct,
        direct_overhead_paisa=direct_overhead,
        allocated_overhead_paisa=allocated_overhead,
        total_cost_paisa=total_cost,
        expected_output_pkts=run.expected_output_pkts,
        good_packets=good_pkts,
        rejected_packets=rej_pkts,
        cost_per_packet_paisa=unit_paisa,
        exact_cost_per_packet_paisa=exact_unit,
        selling_price_snapshot_paisa=selling_paisa,
        gross_margin_per_pkt_paisa=margin_paisa,
        gross_margin_pct=margin_pct,
        material_variance_paisa=mat_variance,
        cost_breakdown_snapshot=snapshot_json,
        notes=notes,
        computed_by=actor.user_id,
    )
    db.add(new_summary)
    db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="PRODUCTION_COST_SNAPSHOT_CREATED",
        entity_schema="costing",
        entity_table="production_cost_summaries",
        entity_id=new_summary.id,
        after_state={
            "production_run_id": run.id,
            "run_number": run.run_number,
            "snapshot_version": next_ver,
            "cost_status": cost_status,
            "total_cost_paisa": total_cost,
            "good_packets": good_pkts,
            "cost_per_packet_paisa": unit_paisa,
            "direct_overhead_paisa": direct_overhead,
            "allocated_overhead_paisa": allocated_overhead,
        },
        reason=notes or f"Recorded immutable batch cost snapshot v{next_ver} ({cost_status}) for {run.run_number}",
    )
    return new_summary


def _load_run_for_costing(db: Session, run_id: int, *, for_update: bool = False) -> ProductionRun:
    stmt = (
        select(ProductionRun)
        .options(selectinload(ProductionRun.material_issues))
        .execution_options(populate_existing=True)
        .where(ProductionRun.id == run_id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    run = db.execute(stmt).scalar_one_or_none()
    if run is None:
        raise NotFoundError(f"Production run {run_id} was not found.")
    return run


def get_run_costing_detail(db: Session, actor: CurrentActor, run_id: int) -> RunCostingDetailOut:
    _require_cost_viewer(actor, "view production costing breakdown")
    run = _load_run_for_costing(db, run_id)
    ps = db.execute(select(PackSize).where(PackSize.id == run.pack_size_id)).scalar_one()
    summaries = (
        db.execute(
            select(ProductionCostSummary)
            .where(ProductionCostSummary.production_run_id == run.id)
            .order_by(ProductionCostSummary.snapshot_version.desc())
        )
        .scalars()
        .all()
    )
    overheads = (
        db.execute(
            select(ProductionOverhead)
            .where(ProductionOverhead.production_run_id == run.id)
            .order_by(ProductionOverhead.id.asc())
        )
        .scalars()
        .all()
    )
    uids = {s.computed_by for s in summaries} | {o.recorded_by for o in overheads} | {
        o.voided_by for o in overheads if o.voided_by is not None
    }
    users = _users_map(db, uids)
    hydrated_snaps = [_hydrate_summary(s, run=run, ps=ps, users=users) for s in summaries]
    current = next((s for s in hydrated_snaps if s.is_current), hydrated_snaps[0] if hydrated_snaps else None)
    return RunCostingDetailOut(
        production_run_id=run.id,
        run_number=run.run_number,
        sku_code=ps.sku_code,
        display_name=ps.display_name,
        run_status=run.status,
        run_date=run.run_date,
        current_summary=current,
        history_snapshots=hydrated_snaps,
        overheads=[_hydrate_overhead(o, users) for o in overheads],
    )


def add_run_overhead(
    db: Session, actor: CurrentActor, run_id: int, payload: AddRunOverheadRequest
) -> RunCostingDetailOut:
    _require_cost_operator(actor, "record production run overheads")
    try:
        run = _load_run_for_costing(db, run_id, for_update=True)
        if run.status not in {"COMPLETED", "POSTED"}:
            raise ConflictError(
                f"Cannot attach overheads to run {run.run_number} in status '{run.status}'; post or complete run first.",
                error_code="INVALID_STATE_TRANSITION",
            )
        ov = ProductionOverhead(
            production_run_id=run.id,
            period_month=run.run_date.strftime("%Y-%m"),
            overhead_type=payload.overhead_type,
            allocation_scope="DIRECT_RUN",
            amount_paisa=payload.amount_paisa,
            notes=payload.notes.strip() if payload.notes else None,
            recorded_by=actor.user_id,
        )
        db.add(ov)
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PRODUCTION_OVERHEAD_ADDED",
            entity_schema="costing",
            entity_table="production_overheads",
            entity_id=ov.id,
            after_state={
                "production_run_id": run.id,
                "overhead_type": ov.overhead_type,
                "amount_paisa": int(ov.amount_paisa),
            },
            reason=ov.notes or f"Added {ov.overhead_type} overhead to {run.run_number}",
        )
        create_cost_snapshot_for_run(
            db,
            actor=actor,
            run=run,
            cost_status="FINALIZED",
            notes=ov.notes or f"Updated batch costing after adding {ov.overhead_type}",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_run_costing_detail(db, actor, run_id)


def finalize_run_costing(
    db: Session, actor: CurrentActor, run_id: int, payload: FinalizeRunCostingRequest
) -> RunCostingDetailOut:
    """Step 8 Batch Costing: optionally add direct labour / gas-power / overheads and finalize batch cost snapshot."""
    _require_cost_operator(actor, "finalize production batch costing")
    try:
        run = _load_run_for_costing(db, run_id, for_update=True)
        if run.status not in {"COMPLETED", "POSTED"}:
            raise ConflictError(
                f"Run {run.run_number} must be COMPLETED or POSTED before finalizing costing.",
                error_code="INVALID_STATE_TRANSITION",
            )
        for line in payload.overheads:
            ov = ProductionOverhead(
                production_run_id=run.id,
                period_month=run.run_date.strftime("%Y-%m"),
                overhead_type=line.overhead_type,
                allocation_scope="DIRECT_RUN",
                amount_paisa=line.amount_paisa,
                notes=line.notes.strip() if line.notes else None,
                recorded_by=actor.user_id,
            )
            db.add(ov)
            db.flush()
            record_audit_log(
                db,
                actor_user_id=actor.user_id,
                actor_role=actor.role_code,
                action="PRODUCTION_OVERHEAD_ADDED",
                entity_schema="costing",
                entity_table="production_overheads",
                entity_id=ov.id,
                after_state={
                    "production_run_id": run.id,
                    "overhead_type": ov.overhead_type,
                    "amount_paisa": int(ov.amount_paisa),
                },
                reason=ov.notes or f"Step 8 direct overhead on {run.run_number}",
            )

        create_cost_snapshot_for_run(
            db,
            actor=actor,
            run=run,
            cost_status="FINALIZED",
            notes=payload.notes.strip() if payload.notes else f"Finalized batch cost for {run.run_number}",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_run_costing_detail(db, actor, run_id)


def void_overhead(
    db: Session, actor: CurrentActor, overhead_id: int, payload: VoidOverheadRequest
) -> dict:
    """Audit-logged voiding of an erroneous overhead entry without deleting historical rows."""
    if actor.role_code != "FACTORY_ADMIN":
        raise AuthorizationError("Only Factory Admin can void recorded overhead entries.")
    try:
        ov = (
            db.execute(
                select(ProductionOverhead)
                .where(ProductionOverhead.id == overhead_id)
                .with_for_update()
            )
            .scalar_one_or_none()
        )
        if ov is None:
            raise NotFoundError(f"Overhead entry {overhead_id} was not found.")
        if ov.is_voided:
            raise ConflictError("Overhead entry is already voided.", error_code="ALREADY_VOIDED")
        ov.is_voided = True
        ov.void_reason = payload.reason
        ov.voided_by = actor.user_id
        ov.voided_at = datetime.now(UTC)
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PRODUCTION_OVERHEAD_VOIDED",
            entity_schema="costing",
            entity_table="production_overheads",
            entity_id=ov.id,
            after_state={"is_voided": True, "amount_paisa": int(ov.amount_paisa)},
            reason=payload.reason,
        )

        if ov.production_run_id is not None:
            run = _load_run_for_costing(db, ov.production_run_id, for_update=True)
            create_cost_snapshot_for_run(
                db,
                actor=actor,
                run=run,
                cost_status="FINALIZED",
                notes=f"Recalculated after voiding overhead #{ov.id}: {payload.reason}",
            )
        else:
            reallocate_monthly_pool_internal(db, actor=actor, period_month=ov.period_month, notes=payload.reason)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"status": "VOIDED", "overhead_id": overhead_id}


def reallocate_monthly_pool_internal(
    db: Session,
    *,
    actor: CurrentActor,
    period_month: str,
    notes: str | None = None,
) -> list[ProductionCostSummary]:
    year, month = int(period_month[:4]), int(period_month[5:7])
    month_start = date(year, month, 1)
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    runs = (
        db.execute(
            select(ProductionRun)
            .options(selectinload(ProductionRun.material_issues))
            .where(
                ProductionRun.run_date >= month_start,
                ProductionRun.run_date < next_month,
                ProductionRun.status.in_(["COMPLETED", "POSTED"]),
                ProductionRun.actual_good_output_pkts > 0,
            )
            .order_by(ProductionRun.id.asc())
            .with_for_update()
        )
        .scalars()
        .all()
    )
    created: list[ProductionCostSummary] = []
    for run in runs:
        created.append(
            create_cost_snapshot_for_run(
                db,
                actor=actor,
                run=run,
                cost_status="FINALIZED",
                notes=notes or f"Allocated monthly factory overhead pool for {period_month}",
            )
        )
    return created


def add_monthly_pool_overhead(
    db: Session, actor: CurrentActor, payload: AddMonthlyPoolOverheadRequest
) -> ProductionOverheadOut:
    _require_cost_operator(actor, "record monthly overhead pools")
    try:
        ov = ProductionOverhead(
            production_run_id=None,
            period_month=payload.period_month,
            overhead_type=payload.overhead_type,
            allocation_scope="MONTHLY_POOL",
            amount_paisa=payload.amount_paisa,
            notes=payload.notes.strip() if payload.notes else None,
            recorded_by=actor.user_id,
        )
        db.add(ov)
        db.flush()
        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="MONTHLY_OVERHEAD_POOL_ADDED",
            entity_schema="costing",
            entity_table="production_overheads",
            entity_id=ov.id,
            after_state={
                "period_month": ov.period_month,
                "overhead_type": ov.overhead_type,
                "amount_paisa": int(ov.amount_paisa),
            },
            reason=ov.notes or f"Monthly overhead pool for {ov.period_month}",
        )
        reallocate_monthly_pool_internal(
            db, actor=actor, period_month=ov.period_month, notes=ov.notes
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    users = _users_map(db, {ov.recorded_by})
    return _hydrate_overhead(ov, users)


def reallocate_monthly_pool(
    db: Session, actor: CurrentActor, period_month: str
) -> dict:
    _require_cost_operator(actor, "reallocate monthly overhead pools")
    try:
        snaps = reallocate_monthly_pool_internal(db, actor=actor, period_month=period_month)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"period_month": period_month, "updated_runs_count": len(snaps)}


def get_costing_dashboard(
    db: Session,
    actor: CurrentActor,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    pack_size_id: int | None = None,
) -> CostingDashboardOut:
    _require_cost_viewer(actor, "view costing dashboard")
    company = _get_company(db)

    stmt = (
        select(ProductionCostSummary, ProductionRun, PackSize)
        .join(ProductionRun, ProductionRun.id == ProductionCostSummary.production_run_id)
        .join(PackSize, PackSize.id == ProductionRun.pack_size_id)
        .where(ProductionCostSummary.is_current.is_(True))
    )
    if date_from is not None:
        stmt = stmt.where(ProductionRun.run_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(ProductionRun.run_date <= date_to)
    if pack_size_id is not None:
        stmt = stmt.where(ProductionRun.pack_size_id == pack_size_id)
    stmt = stmt.order_by(ProductionRun.run_date.desc(), ProductionRun.id.desc())

    rows = db.execute(stmt).all()
    uids = {pcs.computed_by for pcs, _, _ in rows}
    pools = (
        db.execute(
            select(ProductionOverhead)
            .where(ProductionOverhead.allocation_scope == "MONTHLY_POOL")
            .order_by(ProductionOverhead.period_month.desc(), ProductionOverhead.id.desc())
        )
        .scalars()
        .all()
    )
    uids |= {p.recorded_by for p in pools} | {p.voided_by for p in pools if p.voided_by is not None}
    users = _users_map(db, uids)

    runs_out = [_hydrate_summary(pcs, run=run, ps=ps, users=users) for pcs, run, ps in rows]

    # Product-level aggregation across costed runs
    agg: dict[int, dict[str, Any]] = {}
    for s in runs_out:
        ent = agg.setdefault(
            s.pack_size_id,
            {
                "pack_size_id": s.pack_size_id,
                "sku_code": s.sku_code,
                "display_name": s.display_name,
                "run_count": 0,
                "total_good_packets": 0,
                "total_rejected_packets": 0,
                "total_raw_cost_paisa": 0,
                "total_pkg_cost_paisa": 0,
                "total_overhead_cost_paisa": 0,
                "total_cost_paisa": 0,
                "latest_cost_per_pkt_paisa": s.cost_per_packet_paisa or 0,
                "selling_price_paisa": s.selling_price_snapshot_paisa,
            },
        )
        ent["run_count"] += 1
        ent["total_good_packets"] += s.good_packets
        ent["total_rejected_packets"] += s.rejected_packets
        ent["total_raw_cost_paisa"] += s.raw_material_cost_paisa
        ent["total_pkg_cost_paisa"] += s.packaging_cost_paisa
        ent["total_overhead_cost_paisa"] += s.direct_overhead_paisa + s.allocated_overhead_paisa
        ent["total_cost_paisa"] += s.total_cost_paisa

    prod_summaries: list[ProductCostAggregateOut] = []
    for ent in sorted(agg.values(), key=lambda x: x["sku_code"]):
        gp = ent["total_good_packets"]
        w_avg = (
            int((Decimal(ent["total_cost_paisa"]) / Decimal(gp)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            if gp > 0
            else 0
        )
        sp = ent["selling_price_paisa"]
        mg = sp - w_avg
        mg_pct = ((Decimal(mg) / Decimal(sp)) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if sp > 0 else Decimal("0.00")
        prod_summaries.append(
            ProductCostAggregateOut(
                **ent,
                weighted_avg_cost_per_pkt_paisa=w_avg,
                unit_gross_margin_paisa=mg,
                unit_gross_margin_pct=mg_pct,
            )
        )

    return CostingDashboardOut(
        valuation_method=company.valuation_method,
        total_costed_runs=len(runs_out),
        total_finalized_runs=sum(1 for r in runs_out if r.cost_status == "FINALIZED"),
        total_good_packets=sum(r.good_packets for r in runs_out),
        total_batch_cost_paisa=sum(r.total_cost_paisa for r in runs_out),
        total_wastage_and_damage_paisa=sum(
            r.damaged_packaging_cost_paisa + r.raw_wastage_cost_paisa + r.rejected_output_cost_impact_paisa
            for r in runs_out
        ),
        runs=runs_out,
        product_summaries=prod_summaries,
        monthly_pools=[_hydrate_overhead(p, users) for p in pools],
    )
