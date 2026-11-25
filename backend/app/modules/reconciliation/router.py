"""Phase 10 Cross-Module Reconciliation & Investigation API router."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.iam import service as iam_service
from app.modules.iam.schemas import CurrentActor
from app.modules.reconciliation import service as recon_service
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
    ReconciliationRunCreateRequest,
    ReconciliationRunDetailOut,
    ReconciliationRunSummaryOut,
    SalesReconciliationRowOut,
)

router = APIRouter(prefix="/reconciliation", tags=["Cross-Module Reconciliation"])

_ReconUser = Annotated[
    CurrentActor,
    Depends(
        iam_service.require_roles(
            "FACTORY_ADMIN", "OWNER", "ACCOUNTANT_AUDITOR", "PRODUCTION_SUPERVISOR"
        )
    ),
]


@router.get("/reports/inventory", response_model=InventoryReconciliationReportOut)
def get_inventory_reconciliation_report(
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
    period_start: Annotated[date | None, Query()] = None,
    period_end: Annotated[date | None, Query()] = None,
    cutoff_at: Annotated[datetime | None, Query()] = None,
    item_category: Annotated[str | None, Query()] = None,
    material_id: Annotated[int | None, Query(gt=0)] = None,
    pack_size_id: Annotated[int | None, Query(gt=0)] = None,
    only_mismatches: Annotated[bool, Query()] = False,
) -> InventoryReconciliationReportOut:
    return recon_service.get_inventory_reconciliation_report(
        db,
        actor,
        period_start=period_start,
        period_end=period_end,
        cutoff_at=cutoff_at,
        item_category=item_category,
        material_id=material_id,
        pack_size_id=pack_size_id,
        only_mismatches=only_mismatches,
    )


@router.get("/reports/inventory/export/csv")
def export_inventory_reconciliation_csv(
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
    period_start: Annotated[date | None, Query()] = None,
    period_end: Annotated[date | None, Query()] = None,
    item_category: Annotated[str | None, Query()] = None,
    only_mismatches: Annotated[bool, Query()] = False,
) -> Response:
    csv_text = recon_service.export_inventory_reconciliation_csv(
        db,
        actor,
        period_start=period_start,
        period_end=period_end,
        item_category=item_category,
        only_mismatches=only_mismatches,
    )
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="inventory_reconciliation.csv"'},
    )


@router.get("/reports/sales", response_model=list[SalesReconciliationRowOut])
def get_sales_reconciliation_report(
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
    period_start: Annotated[date | None, Query()] = None,
    period_end: Annotated[date | None, Query()] = None,
) -> list[SalesReconciliationRowOut]:
    return recon_service.get_sales_reconciliation_report(
        db, actor, period_start=period_start, period_end=period_end
    )


@router.get("/reports/invoices", response_model=list[InvoiceReconciliationRowOut])
def get_invoice_reconciliation_report(
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
    period_start: Annotated[date | None, Query()] = None,
    period_end: Annotated[date | None, Query()] = None,
) -> list[InvoiceReconciliationRowOut]:
    return recon_service.get_invoice_reconciliation_report(
        db, actor, period_start=period_start, period_end=period_end
    )


@router.get("/reports/payments", response_model=list[PaymentReconciliationRowOut])
def get_payment_reconciliation_report(
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
    period_start: Annotated[date | None, Query()] = None,
    period_end: Annotated[date | None, Query()] = None,
) -> list[PaymentReconciliationRowOut]:
    return recon_service.get_payment_reconciliation_report(
        db, actor, period_start=period_start, period_end=period_end
    )


@router.get("/reports/dispatch", response_model=list[DispatchReconciliationRowOut])
def get_dispatch_reconciliation_report(
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
    period_start: Annotated[date | None, Query()] = None,
    period_end: Annotated[date | None, Query()] = None,
) -> list[DispatchReconciliationRowOut]:
    return recon_service.get_dispatch_reconciliation_report(
        db, actor, period_start=period_start, period_end=period_end
    )


@router.get("/reports/production", response_model=list[ProductionReconciliationRowOut])
def get_production_reconciliation_report(
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
    period_start: Annotated[date | None, Query()] = None,
    period_end: Annotated[date | None, Query()] = None,
) -> list[ProductionReconciliationRowOut]:
    return recon_service.get_production_reconciliation_report(
        db, actor, period_start=period_start, period_end=period_end
    )


@router.get("/runs", response_model=list[ReconciliationRunSummaryOut])
def list_reconciliation_runs(
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
    domain: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> list[ReconciliationRunSummaryOut]:
    return recon_service.list_reconciliation_runs(db, actor, domain=domain, status=status)


@router.post("/runs", response_model=ReconciliationRunDetailOut, status_code=201)
def start_reconciliation_run(
    payload: ReconciliationRunCreateRequest,
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
) -> ReconciliationRunDetailOut:
    return recon_service.start_reconciliation_run(db, actor, payload)


@router.get("/runs/{run_id}", response_model=ReconciliationRunDetailOut)
def get_reconciliation_run(
    run_id: int,
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
) -> ReconciliationRunDetailOut:
    return recon_service.get_reconciliation_run_detail(db, actor, run_id)


@router.post("/runs/{run_id}/rerun", response_model=ReconciliationRunDetailOut)
def rerun_reconciliation(
    run_id: int,
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
) -> ReconciliationRunDetailOut:
    return recon_service.rerun_reconciliation(db, actor, run_id)


@router.post("/runs/{run_id}/close", response_model=ReconciliationRunDetailOut)
def close_reconciliation(
    run_id: int,
    payload: CloseReconciliationRunRequest,
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
) -> ReconciliationRunDetailOut:
    return recon_service.close_reconciliation_run(db, actor, run_id, payload)


@router.get("/discrepancies", response_model=list[ReconciliationDiscrepancyOut])
def list_discrepancies(
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
    domain: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> list[ReconciliationDiscrepancyOut]:
    return recon_service.list_all_discrepancies(db, actor, domain=domain, status=status)


@router.post("/discrepancies/{discrepancy_id}/investigate", response_model=ReconciliationDiscrepancyOut)
def investigate_discrepancy(
    discrepancy_id: int,
    payload: InvestigateDiscrepancyRequest,
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
) -> ReconciliationDiscrepancyOut:
    return recon_service.investigate_discrepancy(db, actor, discrepancy_id, payload)


@router.post("/discrepancies/{discrepancy_id}/propose", response_model=ReconciliationDiscrepancyOut)
def propose_correction(
    discrepancy_id: int,
    payload: ProposeCorrectionRequest,
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
) -> ReconciliationDiscrepancyOut:
    return recon_service.propose_discrepancy_correction(db, actor, discrepancy_id, payload)


@router.post("/discrepancies/{discrepancy_id}/approve", response_model=ReconciliationDiscrepancyOut)
def approve_correction(
    discrepancy_id: int,
    payload: ApproveCorrectionRequest,
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
) -> ReconciliationDiscrepancyOut:
    return recon_service.approve_discrepancy_correction(db, actor, discrepancy_id, payload)


@router.post("/discrepancies/{discrepancy_id}/resolve", response_model=ReconciliationDiscrepancyOut)
def resolve_discrepancy(
    discrepancy_id: int,
    payload: ApplyCorrectionRequest,
    actor: _ReconUser,
    db: Annotated[Session, Depends(get_db)],
) -> ReconciliationDiscrepancyOut:
    return recon_service.apply_discrepancy_resolution(db, actor, discrepancy_id, payload)
