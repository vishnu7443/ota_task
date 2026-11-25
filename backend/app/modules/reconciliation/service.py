"""Reconciliation Service — cross-module diagnostic runs, CSV reports, workflow & authorized resolution."""

import csv
import hashlib
import io
import json
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.modules.audit.models import (
    ReconciliationDiscrepancy,
    ReconciliationEvent,
    ReconciliationRun,
)
from app.modules.audit.service import record_audit_log
from app.modules.billing import repository as billing_repo
from app.modules.billing.gst_engine import get_indian_financial_year
from app.modules.iam.models import User
from app.modules.iam.schemas import CurrentActor
from app.modules.inventory import service as inventory_service
from app.modules.inventory.schemas import StockAdjustmentCreateRequest
from app.modules.reconciliation import engine as recon_engine
from app.modules.reconciliation.schemas import (
    ApplyCorrectionRequest,
    ApproveCorrectionRequest,
    CloseReconciliationRunRequest,
    DispatchReconciliationRowOut,
    InventoryReconciliationReportOut,
    InvestigateDiscrepancyRequest,
    InvoiceReconciliationRowOut,
    PaymentReconciliationRowOut,
    ProductionReconciliationRowOut,
    ProposeCorrectionRequest,
    ReconciliationDiscrepancyOut,
    ReconciliationEventOut,
    ReconciliationRunCreateRequest,
    ReconciliationRunDetailOut,
    ReconciliationRunSummaryOut,
    SalesReconciliationRowOut,
)

IST = ZoneInfo("Asia/Kolkata")
_ALL_RECON_ROLES = {"FACTORY_ADMIN", "OWNER", "ACCOUNTANT_AUDITOR"}
_OPS_DOMAINS = {"INVENTORY", "PURCHASING", "PRODUCTION"}


def _default_period(period_start: date | None, period_end: date | None) -> tuple[date, date]:
    today = datetime.now(IST).date()
    end = period_end or today
    start = period_start or date(end.year if end.month >= 4 else end.year - 1, 4, 1)
    if end < start:
        raise DomainValidationError("period_end cannot be earlier than period_start.")
    return start, end


def _check_domain_view_or_run(actor: CurrentActor, domain: str) -> None:
    if actor.role_code in _ALL_RECON_ROLES:
        return
    if actor.role_code == "PRODUCTION_SUPERVISOR" and domain in _OPS_DOMAINS:
        return
    raise AuthorizationError(
        f"Role '{actor.role_code}' is not permitted to access reconciliation domain '{domain}'."
    )


def _require_recon_operator(actor: CurrentActor, domain: str, action: str) -> None:
    if actor.role_code == "ACCOUNTANT_AUDITOR":
        raise AuthorizationError(
            f"Accountant / Auditor role is strictly read-only and cannot {action}."
        )
    _check_domain_view_or_run(actor, domain)


def _compute_fingerprint(domain: str, start: date, end: date, scope: dict) -> str:
    raw = f"{domain}:{start.isoformat()}:{end.isoformat()}:{json.dumps(scope, sort_keys=True)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _users_map(db: Session, ids: set[int]) -> dict[int, User]:
    clean = {i for i in ids if i is not None}
    if not clean:
        return {}
    return {u.id: u for u in db.execute(select(User).where(User.id.in_(clean))).scalars().all()}


def _hydrate_discrepancy(d: ReconciliationDiscrepancy, users: dict[int, User]) -> ReconciliationDiscrepancyOut:
    return ReconciliationDiscrepancyOut(
        id=d.id,
        reconciliation_run_id=d.reconciliation_run_id,
        domain=d.domain,
        discrepancy_code=d.discrepancy_code,
        severity=d.severity,
        entity_schema=d.entity_schema,
        entity_table=d.entity_table,
        entity_id=d.entity_id,
        entity_ref=d.entity_ref,
        expected_value=d.expected_value,
        actual_value=d.actual_value,
        difference_summary=d.difference_summary,
        status=d.status,
        assigned_to=d.assigned_to,
        assigned_to_name=users[d.assigned_to].full_name if d.assigned_to in users else None,
        investigation_notes=d.investigation_notes,
        proposed_action=d.proposed_action,
        corrective_action_type=d.corrective_action_type,
        approved_by=d.approved_by,
        approved_by_name=users[d.approved_by].full_name if d.approved_by in users else None,
        approved_at=d.approved_at,
        resolution_notes=d.resolution_notes,
        resolution_ref_table=d.resolution_ref_table,
        resolution_ref_id=d.resolution_ref_id,
        resolved_by=d.resolved_by,
        resolved_by_name=users[d.resolved_by].full_name if d.resolved_by in users else None,
        resolved_at=d.resolved_at,
        created_at=d.created_at,
        updated_at=d.updated_at,
        version=d.version,
    )


def _hydrate_run_summary(run: ReconciliationRun, users: dict[int, User]) -> ReconciliationRunSummaryOut:
    return ReconciliationRunSummaryOut(
        id=run.id,
        run_number=run.run_number,
        financial_year=run.financial_year,
        domain=run.domain,
        status=run.status,
        period_start=run.period_start,
        period_end=run.period_end,
        cutoff_at=run.cutoff_at,
        scope_filter=run.scope_filter,
        summary_snapshot=run.summary_snapshot,
        discrepancy_count=run.discrepancy_count,
        resolved_count=run.resolved_count,
        started_by=run.started_by,
        started_by_name=users[run.started_by].full_name if run.started_by in users else "System",
        started_at=run.started_at,
        last_rerun_at=run.last_rerun_at,
        closed_by=run.closed_by,
        closed_by_name=users[run.closed_by].full_name if run.closed_by in users else None,
        closed_at=run.closed_at,
        closure_notes=run.closure_notes,
        version=run.version,
    )


def _hydrate_run_detail(db: Session, run: ReconciliationRun) -> ReconciliationRunDetailOut:
    uids = {run.started_by}
    if run.closed_by:
        uids.add(run.closed_by)
    for d in run.discrepancies:
        for u in (d.assigned_to, d.approved_by, d.resolved_by):
            if u:
                uids.add(u)
    for e in run.events:
        uids.add(e.actor_user_id)
    users = _users_map(db, uids)

    summary = _hydrate_run_summary(run, users)
    return ReconciliationRunDetailOut(
        **summary.model_dump(),
        discrepancies=[_hydrate_discrepancy(d, users) for d in run.discrepancies],
        events=[
            ReconciliationEventOut(
                id=e.id,
                reconciliation_run_id=e.reconciliation_run_id,
                discrepancy_id=e.discrepancy_id,
                actor_user_id=e.actor_user_id,
                actor_name=users[e.actor_user_id].full_name if e.actor_user_id in users else "System",
                actor_role=e.actor_role,
                event_type=e.event_type,
                from_status=e.from_status,
                to_status=e.to_status,
                notes=e.notes,
                payload=e.payload,
                occurred_at=e.occurred_at,
            )
            for e in run.events
        ],
    )


def _execute_domain_scan(
    db: Session,
    *,
    domain: str,
    period_start: date,
    period_end: date,
    cutoff_at: datetime,
    scope: dict,
) -> tuple[dict, list[recon_engine.DiscrepancyCandidate]]:
    candidates: list[recon_engine.DiscrepancyCandidate] = []
    summary: dict[str, int] = {}

    if domain in {"INVENTORY", "FULL_SYSTEM"}:
        inv_rows, inv_disc = recon_engine.evaluate_inventory_reconciliation(
            db,
            period_start=period_start,
            period_end=period_end,
            cutoff_at=cutoff_at,
            item_category=scope.get("item_category"),
            material_id=scope.get("material_id"),
            pack_size_id=scope.get("pack_size_id"),
        )
        candidates.extend(inv_disc)
        summary["inventory_items_checked"] = len(inv_rows)
        summary["inventory_mismatches"] = sum(1 for r in inv_rows if r.status == "MISMATCH")

    if domain in {"SALES", "FULL_SYSTEM"}:
        sales_rows, sales_disc = recon_engine.evaluate_sales_reconciliation(
            db, period_start=period_start, period_end=period_end
        )
        candidates.extend(sales_disc)
        summary["sales_orders_checked"] = len(sales_rows)
        summary["sales_discrepancies"] = sum(1 for r in sales_rows if r.status == "DISCREPANCY")

    if domain in {"INVOICE", "FULL_SYSTEM"}:
        inv_bill_rows, inv_bill_disc = recon_engine.evaluate_invoice_reconciliation(
            db, period_start=period_start, period_end=period_end
        )
        candidates.extend(inv_bill_disc)
        summary["invoices_checked"] = len(inv_bill_rows)
        summary["invoice_discrepancies"] = sum(1 for r in inv_bill_rows if r.status == "DISCREPANCY")

    if domain in {"PAYMENT", "FULL_SYSTEM"}:
        pmt_rows, pmt_disc = recon_engine.evaluate_payment_reconciliation(
            db, period_start=period_start, period_end=period_end
        )
        candidates.extend(pmt_disc)
        summary["payments_checked"] = len(pmt_rows)
        summary["payment_discrepancies"] = sum(1 for r in pmt_rows if r.status == "DISCREPANCY")

    if domain in {"DISPATCH", "FULL_SYSTEM"}:
        dsp_rows, dsp_disc = recon_engine.evaluate_dispatch_reconciliation(
            db, period_start=period_start, period_end=period_end
        )
        candidates.extend(dsp_disc)
        summary["dispatched_invoices_checked"] = len(dsp_rows)
        summary["dispatch_discrepancies"] = sum(1 for r in dsp_rows if r.status == "DISCREPANCY")

    if domain in {"PRODUCTION", "FULL_SYSTEM"}:
        prd_rows, prd_disc = recon_engine.evaluate_production_reconciliation(
            db, period_start=period_start, period_end=period_end
        )
        candidates.extend(prd_disc)
        summary["production_runs_checked"] = len(prd_rows)
        summary["production_discrepancies"] = sum(1 for r in prd_rows if r.status == "DISCREPANCY")

    return summary, candidates


# ── Live On-Demand Diagnostic Reports & CSV Exports ────────────────────────────

def get_inventory_reconciliation_report(
    db: Session,
    actor: CurrentActor,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    cutoff_at: datetime | None = None,
    item_category: str | None = None,
    material_id: int | None = None,
    pack_size_id: int | None = None,
    only_mismatches: bool = False,
) -> InventoryReconciliationReportOut:
    _check_domain_view_or_run(actor, "INVENTORY")
    start, end = _default_period(period_start, period_end)
    eff_cutoff = cutoff_at or datetime.now(UTC)
    rows, _ = recon_engine.evaluate_inventory_reconciliation(
        db,
        period_start=start,
        period_end=end,
        cutoff_at=eff_cutoff,
        item_category=item_category,
        material_id=material_id,
        pack_size_id=pack_size_id,
    )
    filtered = [r for r in rows if (not only_mismatches or r.status == "MISMATCH")]
    matched = sum(1 for r in rows if r.status == "MATCHED")
    mismatched = sum(1 for r in rows if r.status == "MISMATCH")
    return InventoryReconciliationReportOut(
        period_start=start,
        period_end=end,
        cutoff_at=eff_cutoff,
        total_items=len(rows),
        matched_count=matched,
        mismatch_count=mismatched,
        items=filtered,
    )


def export_inventory_reconciliation_csv(
    db: Session,
    actor: CurrentActor,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    item_category: str | None = None,
    only_mismatches: bool = False,
) -> str:
    rep = get_inventory_reconciliation_report(
        db,
        actor,
        period_start=period_start,
        period_end=period_end,
        item_category=item_category,
        only_mismatches=only_mismatches,
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "Item Type",
            "Code",
            "Name",
            "Category",
            "Base UOM",
            "Opening Qty",
            "Purchase In",
            "Production In",
            "Returns In",
            "Pos Adj In",
            "Total Inward",
            "Prod Issue Out",
            "Dispatch Out",
            "Damage/Wastage",
            "Supplier Return",
            "Neg Adj Out",
            "Total Outward",
            "Expected Closing",
            "Persisted Closing",
            "Difference",
            "Open Cost Lots",
            "Status",
        ]
    )
    for r in rep.items:
        w.writerow(
            [
                r.item_type,
                r.code,
                r.name,
                r.item_category,
                r.base_uom,
                str(r.opening_qty_base),
                str(r.inward_purchase_qty_base),
                str(r.inward_production_qty_base),
                str(r.inward_returns_qty_base),
                str(r.inward_adjustment_qty_base),
                str(r.total_inward_qty_base),
                str(r.outward_production_issue_qty_base),
                str(r.outward_dispatch_qty_base),
                str(r.outward_damage_wastage_qty_base),
                str(r.outward_supplier_return_qty_base),
                str(r.outward_adjustment_qty_base),
                str(r.total_outward_qty_base),
                str(r.expected_closing_qty_base),
                str(r.persisted_closing_qty_base),
                str(r.difference_qty_base),
                str(r.cost_lot_remaining_qty_base),
                r.status,
            ]
        )
    return buf.getvalue()


def get_sales_reconciliation_report(
    db: Session, actor: CurrentActor, *, period_start: date | None = None, period_end: date | None = None
) -> list[SalesReconciliationRowOut]:
    _check_domain_view_or_run(actor, "SALES")
    start, end = _default_period(period_start, period_end)
    rows, _ = recon_engine.evaluate_sales_reconciliation(db, period_start=start, period_end=end)
    return rows


def get_invoice_reconciliation_report(
    db: Session, actor: CurrentActor, *, period_start: date | None = None, period_end: date | None = None
) -> list[InvoiceReconciliationRowOut]:
    _check_domain_view_or_run(actor, "INVOICE")
    start, end = _default_period(period_start, period_end)
    rows, _ = recon_engine.evaluate_invoice_reconciliation(db, period_start=start, period_end=end)
    return rows


def get_payment_reconciliation_report(
    db: Session, actor: CurrentActor, *, period_start: date | None = None, period_end: date | None = None
) -> list[PaymentReconciliationRowOut]:
    _check_domain_view_or_run(actor, "PAYMENT")
    start, end = _default_period(period_start, period_end)
    rows, _ = recon_engine.evaluate_payment_reconciliation(db, period_start=start, period_end=end)
    return rows


def get_dispatch_reconciliation_report(
    db: Session, actor: CurrentActor, *, period_start: date | None = None, period_end: date | None = None
) -> list[DispatchReconciliationRowOut]:
    _check_domain_view_or_run(actor, "DISPATCH")
    start, end = _default_period(period_start, period_end)
    rows, _ = recon_engine.evaluate_dispatch_reconciliation(db, period_start=start, period_end=end)
    return rows


def get_production_reconciliation_report(
    db: Session, actor: CurrentActor, *, period_start: date | None = None, period_end: date | None = None
) -> list[ProductionReconciliationRowOut]:
    _check_domain_view_or_run(actor, "PRODUCTION")
    start, end = _default_period(period_start, period_end)
    rows, _ = recon_engine.evaluate_production_reconciliation(db, period_start=start, period_end=end)
    return rows


# ── Reconciliation Workflow & Discrepancy Resolution ──────────────────────────

def start_reconciliation_run(
    db: Session, actor: CurrentActor, payload: ReconciliationRunCreateRequest
) -> ReconciliationRunDetailOut:
    _require_recon_operator(actor, payload.domain, "start reconciliation runs")
    start, end = _default_period(payload.period_start, payload.period_end)
    cutoff = payload.cutoff_at or datetime.now(UTC)
    scope = {
        k: v
        for k, v in {
            "item_category": payload.item_category,
            "material_id": payload.material_id,
            "pack_size_id": payload.pack_size_id,
        }.items()
        if v is not None
    }
    fp = _compute_fingerprint(payload.domain, start, end, scope)

    existing_active = db.execute(
        select(ReconciliationRun).where(
            ReconciliationRun.run_fingerprint == fp,
            ReconciliationRun.status.in_(
                ["NOT_STARTED", "IN_PROGRESS", "DISCREPANCY_FOUND", "UNDER_REVIEW"]
            ),
        )
    ).scalar_one_or_none()
    if existing_active is not None:
        raise ConflictError(
            f"Active reconciliation run {existing_active.run_number} ({existing_active.status}) already covers this domain, period, and scope. Re-run or close it before starting another.",
            error_code="DUPLICATE_RECONCILIATION_RUN",
        )

    fy = get_indian_financial_year(end)
    run_no = billing_repo.allocate_fiscal_sequence(
        db, doc_type="RECONCILIATION", financial_year=fy, prefix="REC"
    )
    run = ReconciliationRun(
        run_number=run_no,
        financial_year=fy,
        domain=payload.domain,
        status="IN_PROGRESS",
        period_start=start,
        period_end=end,
        cutoff_at=cutoff,
        scope_filter=scope,
        run_fingerprint=fp,
        started_by=actor.user_id,
    )
    db.add(run)
    db.flush()

    db.add(
        ReconciliationEvent(
            reconciliation_run_id=run.id,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            event_type="RUN_STARTED",
            from_status="NOT_STARTED",
            to_status="IN_PROGRESS",
            notes=f"Initiated {payload.domain} reconciliation for {start} to {end}",
            payload={"scope": scope},
        )
    )

    summary, candidates = _execute_domain_scan(
        db,
        domain=payload.domain,
        period_start=start,
        period_end=end,
        cutoff_at=cutoff,
        scope=scope,
    )
    for cand in candidates:
        db.add(
            ReconciliationDiscrepancy(
                reconciliation_run_id=run.id,
                domain=cand.domain,
                discrepancy_code=cand.discrepancy_code,
                severity=cand.severity,
                entity_schema=cand.entity_schema,
                entity_table=cand.entity_table,
                entity_id=cand.entity_id,
                entity_ref=cand.entity_ref,
                expected_value=cand.expected_value,
                actual_value=cand.actual_value,
                difference_summary=cand.difference_summary,
                status="OPEN",
            )
        )

    final_status = "DISCREPANCY_FOUND" if len(candidates) > 0 else "RECONCILED"
    run.summary_snapshot = summary
    run.discrepancy_count = len(candidates)
    run.status = final_status
    run.version += 1
    db.flush()

    db.add(
        ReconciliationEvent(
            reconciliation_run_id=run.id,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            event_type="SCAN_COMPLETED",
            from_status="IN_PROGRESS",
            to_status=final_status,
            notes=f"Detected {len(candidates)} discrepancies.",
            payload=summary,
        )
    )
    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="RECON_RUN_STARTED",
        entity_schema="audit",
        entity_table="reconciliation_runs",
        entity_id=run.id,
        correlation_ref=run.run_number,
        after_state={
            "run_number": run.run_number,
            "domain": run.domain,
            "status": run.status,
            "discrepancy_count": run.discrepancy_count,
        },
        reason=f"Started {run.domain} reconciliation run {run.run_number}",
    )
    db.commit()
    return get_reconciliation_run_detail(db, actor, run.id)


def list_reconciliation_runs(
    db: Session,
    actor: CurrentActor,
    *,
    domain: str | None = None,
    status: str | None = None,
) -> list[ReconciliationRunSummaryOut]:
    if actor.role_code == "SALESMAN":
        raise AuthorizationError("Salesman role cannot view factory reconciliation runs.")
    stmt = select(ReconciliationRun).order_by(ReconciliationRun.id.desc())
    if actor.role_code == "PRODUCTION_SUPERVISOR":
        stmt = stmt.where(ReconciliationRun.domain.in_(["INVENTORY", "PRODUCTION"]))
    if domain:
        _check_domain_view_or_run(actor, domain)
        stmt = stmt.where(ReconciliationRun.domain == domain)
    if status:
        stmt = stmt.where(ReconciliationRun.status == status)
    runs = list(db.execute(stmt.limit(100)).scalars().all())
    uids = {r.started_by for r in runs} | {r.closed_by for r in runs if r.closed_by}
    users = _users_map(db, uids)
    return [_hydrate_run_summary(r, users) for r in runs]


def get_reconciliation_run_detail(
    db: Session, actor: CurrentActor, run_id: int
) -> ReconciliationRunDetailOut:
    run = db.execute(
        select(ReconciliationRun)
        .options(
            selectinload(ReconciliationRun.discrepancies),
            selectinload(ReconciliationRun.events),
        )
        .where(ReconciliationRun.id == run_id)
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError(f"Reconciliation run {run_id} was not found.")
    _check_domain_view_or_run(actor, run.domain)
    return _hydrate_run_detail(db, run)


def list_all_discrepancies(
    db: Session,
    actor: CurrentActor,
    *,
    domain: str | None = None,
    status: str | None = None,
) -> list[ReconciliationDiscrepancyOut]:
    if actor.role_code == "SALESMAN":
        raise AuthorizationError("Salesman role cannot inspect reconciliation discrepancies.")
    stmt = select(ReconciliationDiscrepancy).order_by(ReconciliationDiscrepancy.id.desc())
    if actor.role_code == "PRODUCTION_SUPERVISOR":
        stmt = stmt.where(ReconciliationDiscrepancy.domain.in_(["INVENTORY", "PURCHASING", "PRODUCTION"]))
    if domain:
        _check_domain_view_or_run(actor, domain)
        stmt = stmt.where(ReconciliationDiscrepancy.domain == domain)
    if status:
        stmt = stmt.where(ReconciliationDiscrepancy.status == status)
    rows = list(db.execute(stmt.limit(200)).scalars().all())
    uids = set()
    for d in rows:
        for u in (d.assigned_to, d.approved_by, d.resolved_by):
            if u:
                uids.add(u)
    users = _users_map(db, uids)
    return [_hydrate_discrepancy(d, users) for d in rows]


def _get_locked_discrepancy(db: Session, actor: CurrentActor, disc_id: int) -> tuple[ReconciliationDiscrepancy, ReconciliationRun]:
    disc = db.execute(
        select(ReconciliationDiscrepancy)
        .where(ReconciliationDiscrepancy.id == disc_id)
        .with_for_update()
    ).scalar_one_or_none()
    if disc is None:
        raise NotFoundError(f"Reconciliation discrepancy {disc_id} was not found.")
    _check_domain_view_or_run(actor, disc.domain)
    run = db.execute(
        select(ReconciliationRun)
        .where(ReconciliationRun.id == disc.reconciliation_run_id)
        .with_for_update()
    ).scalar_one()
    if run.status == "CLOSED":
        raise ConflictError("Reconciliation run is CLOSED and cannot be modified.", error_code="RUN_CLOSED")
    return disc, run


def investigate_discrepancy(
    db: Session, actor: CurrentActor, disc_id: int, payload: InvestigateDiscrepancyRequest
) -> ReconciliationDiscrepancyOut:
    if actor.role_code == "ACCOUNTANT_AUDITOR":
        raise AuthorizationError("Accountant / Auditor role is strictly read-only and cannot investigate/mutate discrepancies.")
    disc, run = _get_locked_discrepancy(db, actor, disc_id)
    if disc.status in {"RESOLVED", "CLOSED", "DISMISSED"}:
        raise ConflictError(f"Discrepancy is already in terminal status '{disc.status}'.")
    prev = disc.status
    if payload.assigned_to is not None:
        assignee = db.execute(select(User).where(User.id == payload.assigned_to)).scalar_one_or_none()
        if assignee is None:
            raise NotFoundError(f"Assigned user {payload.assigned_to} was not found.")
        disc.assigned_to = assignee.id
    disc.investigation_notes = payload.investigation_notes.strip()
    disc.status = "UNDER_REVIEW"
    disc.version += 1
    if run.status == "DISCREPANCY_FOUND":
        run.status = "UNDER_REVIEW"
        run.version += 1

    db.add(
        ReconciliationEvent(
            reconciliation_run_id=run.id,
            discrepancy_id=disc.id,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            event_type="DISCREPANCY_INVESTIGATED",
            from_status=prev,
            to_status="UNDER_REVIEW",
            notes=disc.investigation_notes,
        )
    )
    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="RECON_DISCREPANCY_REVIEWED",
        entity_schema="audit",
        entity_table="reconciliation_discrepancies",
        entity_id=disc.id,
        correlation_ref=run.run_number,
        before_state={"status": prev},
        after_state={"status": "UNDER_REVIEW", "assigned_to": disc.assigned_to},
        reason=disc.investigation_notes,
    )
    db.commit()
    return list_all_discrepancies_for_ids(db, [disc.id])[0]


def list_all_discrepancies_for_ids(db: Session, ids: list[int]) -> list[ReconciliationDiscrepancyOut]:
    rows = list(db.execute(select(ReconciliationDiscrepancy).where(ReconciliationDiscrepancy.id.in_(ids))).scalars().all())
    uids = {u for d in rows for u in (d.assigned_to, d.approved_by, d.resolved_by) if u}
    users = _users_map(db, uids)
    return [_hydrate_discrepancy(d, users) for d in rows]


def propose_discrepancy_correction(
    db: Session, actor: CurrentActor, disc_id: int, payload: ProposeCorrectionRequest
) -> ReconciliationDiscrepancyOut:
    if actor.role_code == "ACCOUNTANT_AUDITOR":
        raise AuthorizationError("Accountant / Auditor role is strictly read-only and cannot propose corrections.")
    disc, run = _get_locked_discrepancy(db, actor, disc_id)
    if disc.status in {"RESOLVED", "CLOSED", "DISMISSED"}:
        raise ConflictError(f"Discrepancy is already in terminal status '{disc.status}'.")
    prev = disc.status
    disc.corrective_action_type = payload.corrective_action_type
    disc.proposed_action = payload.proposed_action.strip()
    if payload.investigation_notes:
        disc.investigation_notes = payload.investigation_notes.strip()
    disc.status = "ACTION_PROPOSED"
    disc.version += 1
    if run.status == "DISCREPANCY_FOUND":
        run.status = "UNDER_REVIEW"
        run.version += 1

    db.add(
        ReconciliationEvent(
            reconciliation_run_id=run.id,
            discrepancy_id=disc.id,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            event_type="CORRECTION_PROPOSED",
            from_status=prev,
            to_status="ACTION_PROPOSED",
            notes=disc.proposed_action,
            payload={"corrective_action_type": disc.corrective_action_type},
        )
    )
    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="RECON_CORRECTION_PROPOSED",
        entity_schema="audit",
        entity_table="reconciliation_discrepancies",
        entity_id=disc.id,
        correlation_ref=run.run_number,
        before_state={"status": prev},
        after_state={"status": "ACTION_PROPOSED", "corrective_action_type": disc.corrective_action_type},
        reason=disc.proposed_action,
    )
    db.commit()
    return list_all_discrepancies_for_ids(db, [disc.id])[0]


def approve_discrepancy_correction(
    db: Session, actor: CurrentActor, disc_id: int, payload: ApproveCorrectionRequest
) -> ReconciliationDiscrepancyOut:
    if actor.role_code not in {"FACTORY_ADMIN", "OWNER"}:
        raise AuthorizationError("Only Factory Admin or Owner can approve proposed reconciliation corrections.")
    disc, run = _get_locked_discrepancy(db, actor, disc_id)
    if disc.status != "ACTION_PROPOSED":
        raise ConflictError(
            f"Discrepancy must be in 'ACTION_PROPOSED' before approval (currently '{disc.status}')."
        )
    prev = disc.status
    disc.status = "APPROVED"
    disc.approved_by = actor.user_id
    disc.approved_at = datetime.now(UTC)
    disc.version += 1

    db.add(
        ReconciliationEvent(
            reconciliation_run_id=run.id,
            discrepancy_id=disc.id,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            event_type="CORRECTION_APPROVED",
            from_status=prev,
            to_status="APPROVED",
            notes=payload.notes or "Approved proposed corrective action.",
        )
    )
    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="RECON_ACTION_APPROVED",
        entity_schema="audit",
        entity_table="reconciliation_discrepancies",
        entity_id=disc.id,
        correlation_ref=run.run_number,
        before_state={"status": prev},
        after_state={"status": "APPROVED"},
        reason=payload.notes or f"Approved {disc.corrective_action_type}",
    )
    db.commit()
    return list_all_discrepancies_for_ids(db, [disc.id])[0]


def apply_discrepancy_resolution(
    db: Session, actor: CurrentActor, disc_id: int, payload: ApplyCorrectionRequest
) -> ReconciliationDiscrepancyOut:
    if actor.role_code != "FACTORY_ADMIN":
        raise AuthorizationError(
            "Only Factory Admin is authorized to execute corrective reconciliation postings or resolutions."
        )
    disc, run = _get_locked_discrepancy(db, actor, disc_id)
    if payload.dismiss:
        if disc.status in {"RESOLVED", "CLOSED", "DISMISSED"}:
            raise ConflictError(f"Discrepancy is already '{disc.status}'.")
        target_status = "DISMISSED"
    else:
        if disc.status != "APPROVED":
            raise ConflictError(
                f"Discrepancy must be 'APPROVED' prior to applying corrective resolution (currently '{disc.status}')."
            )
        target_status = "RESOLVED"

    prev = disc.status
    ref_table: str | None = None
    ref_id: int | None = None

    if not payload.dismiss and disc.corrective_action_type == "STOCK_ADJUSTMENT":
        if payload.entered_qty is None or payload.entered_qty == 0 or not payload.entered_uom:
            raise DomainValidationError(
                "STOCK_ADJUSTMENT resolution requires non-zero entered_qty and entered_uom."
            )
        exp = disc.expected_value or {}
        item_type = exp.get("item_type")
        item_id = exp.get("item_id")
        if item_type not in {"MATERIAL", "PACK_SIZE"} or not item_id:
            raise DomainValidationError(
                "Discrepancy does not reference a valid Material or PackSize for stock adjustment."
            )
        adj = inventory_service.create_stock_adjustment(
            db,
            actor,
            StockAdjustmentCreateRequest(
                item_type=item_type,
                item_id=int(item_id),
                adjustment_type=payload.adjustment_type or "COUNT_CORRECTION",
                entered_qty=payload.entered_qty,
                entered_uom=payload.entered_uom,
                unit_cost_paisa_per_base=payload.unit_cost_paisa_per_base,
                reason=f"[{run.run_number}#{disc.id}] {payload.resolution_notes}",
                post_immediately=True,
            ),
        )
        ref_table = "inventory.stock_adjustments"
        ref_id = adj.id
        # Re-lock run/disc safely after create_stock_adjustment committed internally
        disc, run = _get_locked_discrepancy(db, actor, disc_id)

    disc.status = target_status
    disc.resolution_notes = payload.resolution_notes.strip()
    disc.resolution_ref_table = ref_table
    disc.resolution_ref_id = ref_id
    disc.resolved_by = actor.user_id
    disc.resolved_at = datetime.now(UTC)
    disc.version += 1

    # Recompute run resolution counts
    all_discs = list(
        db.execute(
            select(ReconciliationDiscrepancy).where(
                ReconciliationDiscrepancy.reconciliation_run_id == run.id
            )
        )
        .scalars()
        .all()
    )
    resolved_cnt = sum(1 for d in all_discs if d.status in {"RESOLVED", "CLOSED", "DISMISSED"})
    run.resolved_count = resolved_cnt
    if len(all_discs) > 0 and resolved_cnt == len(all_discs):
        run.status = "RESOLVED"
    run.version += 1

    db.add(
        ReconciliationEvent(
            reconciliation_run_id=run.id,
            discrepancy_id=disc.id,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            event_type="DISCREPANCY_DISMISSED" if payload.dismiss else "DISCREPANCY_RESOLVED",
            from_status=prev,
            to_status=target_status,
            notes=disc.resolution_notes,
            payload={"resolution_ref_table": ref_table, "resolution_ref_id": ref_id},
        )
    )
    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="RECON_ACTION_APPLIED",
        entity_schema="audit",
        entity_table="reconciliation_discrepancies",
        entity_id=disc.id,
        correlation_ref=run.run_number,
        before_state={"status": prev},
        after_state={
            "status": target_status,
            "resolution_ref_table": ref_table,
            "resolution_ref_id": ref_id,
        },
        reason=disc.resolution_notes,
    )
    db.commit()
    return list_all_discrepancies_for_ids(db, [disc.id])[0]


def rerun_reconciliation(
    db: Session, actor: CurrentActor, run_id: int
) -> ReconciliationRunDetailOut:
    run = db.execute(
        select(ReconciliationRun)
        .options(selectinload(ReconciliationRun.discrepancies))
        .where(ReconciliationRun.id == run_id)
        .with_for_update()
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError(f"Reconciliation run {run_id} was not found.")
    _require_recon_operator(actor, run.domain, "re-run reconciliation")
    if run.status == "CLOSED":
        raise ConflictError("Closed reconciliation run cannot be re-run.", error_code="RUN_CLOSED")

    now_utc = datetime.now(UTC)
    summary, fresh_cands = _execute_domain_scan(
        db,
        domain=run.domain,
        period_start=run.period_start,
        period_end=run.period_end,
        cutoff_at=now_utc,
        scope=run.scope_filter or {},
    )
    fresh_keys = {(c.discrepancy_code, c.entity_table, c.entity_id): c for c in fresh_cands}
    existing_keys = {(d.discrepancy_code, d.entity_table, d.entity_id): d for d in run.discrepancies}

    # Mark previously unresolved discrepancies that no longer fail verification as RESOLVED
    for key, d in existing_keys.items():
        if key not in fresh_keys and d.status in {"OPEN", "UNDER_REVIEW", "ACTION_PROPOSED", "APPROVED"}:
            prev = d.status
            d.status = "RESOLVED"
            d.resolution_notes = "Cleared automatically on reconciliation re-run verification."
            d.resolved_by = actor.user_id
            d.resolved_at = now_utc
            d.version += 1
            db.add(
                ReconciliationEvent(
                    reconciliation_run_id=run.id,
                    discrepancy_id=d.id,
                    actor_user_id=actor.user_id,
                    actor_role=actor.role_code,
                    event_type="AUTO_VERIFIED_RESOLVED",
                    from_status=prev,
                    to_status="RESOLVED",
                    notes=d.resolution_notes,
                )
            )

    # Insert any newly introduced discrepancies
    for key, c in fresh_keys.items():
        if key not in existing_keys:
            db.add(
                ReconciliationDiscrepancy(
                    reconciliation_run_id=run.id,
                    domain=c.domain,
                    discrepancy_code=c.discrepancy_code,
                    severity=c.severity,
                    entity_schema=c.entity_schema,
                    entity_table=c.entity_table,
                    entity_id=c.entity_id,
                    entity_ref=c.entity_ref,
                    expected_value=c.expected_value,
                    actual_value=c.actual_value,
                    difference_summary=c.difference_summary,
                    status="OPEN",
                )
            )

    db.flush()
    db.refresh(run)
    total_cnt = len(run.discrepancies)
    resolved_cnt = sum(1 for d in run.discrepancies if d.status in {"RESOLVED", "CLOSED", "DISMISSED"})
    open_cnt = total_cnt - resolved_cnt

    prev_run_status = run.status
    run.summary_snapshot = summary
    run.discrepancy_count = total_cnt
    run.resolved_count = resolved_cnt
    run.last_rerun_at = now_utc
    run.status = "RECONCILED" if total_cnt == 0 else ("RESOLVED" if open_cnt == 0 else "DISCREPANCY_FOUND")
    run.version += 1

    db.add(
        ReconciliationEvent(
            reconciliation_run_id=run.id,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            event_type="RUN_RERUN",
            from_status=prev_run_status,
            to_status=run.status,
            notes=f"Re-ran check: {open_cnt} open, {resolved_cnt} resolved.",
            payload=summary,
        )
    )
    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="RECON_RUN_RERUN",
        entity_schema="audit",
        entity_table="reconciliation_runs",
        entity_id=run.id,
        correlation_ref=run.run_number,
        before_state={"status": prev_run_status},
        after_state={"status": run.status, "open_count": open_cnt, "resolved_count": resolved_cnt},
    )
    db.commit()
    return get_reconciliation_run_detail(db, actor, run.id)


def close_reconciliation_run(
    db: Session, actor: CurrentActor, run_id: int, payload: CloseReconciliationRunRequest
) -> ReconciliationRunDetailOut:
    if actor.role_code not in {"FACTORY_ADMIN", "OWNER"}:
        raise AuthorizationError("Only Factory Admin or Owner can formally close a reconciliation run.")
    run = db.execute(
        select(ReconciliationRun)
        .options(selectinload(ReconciliationRun.discrepancies))
        .where(ReconciliationRun.id == run_id)
        .with_for_update()
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError(f"Reconciliation run {run_id} was not found.")
    if run.status == "CLOSED":
        raise ConflictError(f"Run {run.run_number} is already CLOSED.")

    unresolved = [d for d in run.discrepancies if d.status not in {"RESOLVED", "CLOSED", "DISMISSED"}]
    if unresolved:
        raise ConflictError(
            f"Cannot close {run.run_number}: {len(unresolved)} discrepancy item(s) remain unresolved.",
            error_code="UNRESOLVED_DISCREPANCIES_REMAIN",
        )

    for d in run.discrepancies:
        if d.status == "RESOLVED":
            d.status = "CLOSED"
            d.version += 1

    prev = run.status
    run.status = "CLOSED"
    run.closed_by = actor.user_id
    run.closed_at = datetime.now(UTC)
    run.closure_notes = payload.closure_notes.strip()
    run.version += 1

    db.add(
        ReconciliationEvent(
            reconciliation_run_id=run.id,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            event_type="RUN_CLOSED",
            from_status=prev,
            to_status="CLOSED",
            notes=run.closure_notes,
        )
    )
    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="RECON_RUN_CLOSED",
        entity_schema="audit",
        entity_table="reconciliation_runs",
        entity_id=run.id,
        correlation_ref=run.run_number,
        before_state={"status": prev},
        after_state={"status": "CLOSED"},
        reason=run.closure_notes,
    )
    db.commit()
    return get_reconciliation_run_detail(db, actor, run.id)
