"""Production API router — Catalog, BOM versioning, BOM calculator, runs, execution, posting, variances, dashboard."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.iam import service as iam_service
from app.modules.iam.schemas import CurrentActor
from app.modules.production import service as prod_service
from app.modules.production.schemas import (
    AcknowledgeAlertRequest,
    BomCalculateRequest,
    BomCalculationOut,
    BomHeaderOut,
    BomVersionOut,
    CancelProductionRequest,
    CompleteProductionRequest,
    CreateBomVersionRequest,
    CreateMaterialRequest,
    CreatePackSizeRequest,
    CreateProductionRunRequest,
    PackSizeOut,
    ProductionCatalogOut,
    ProductionDashboardOut,
    ProductionRunOut,
    ProductionVarianceReportRow,
    StartProductionRequest,
    UpdateDraftBomVersionRequest,
    VarianceAlertOut,
)

router = APIRouter(prefix="/production", tags=["Production & BOM"])

_ProdViewer = Annotated[
    CurrentActor,
    Depends(
        iam_service.require_roles(
            "FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "ACCOUNTANT_AUDITOR", "OWNER"
        )
    ),
]
_ProdOperator = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN", "PRODUCTION_SUPERVISOR")),
]
_AlertAckActor = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "OWNER")),
]


# ── Catalog & Extensible Pack Sizes / Materials ─────────────────────────────


@router.get("/catalog", response_model=ProductionCatalogOut)
def get_catalog(actor: _ProdViewer, db: Annotated[Session, Depends(get_db)]) -> ProductionCatalogOut:
    return prod_service.get_production_catalog(db, actor)


@router.post("/catalog/pack-sizes", response_model=PackSizeOut, status_code=201)
def add_pack_size(
    payload: CreatePackSizeRequest,
    actor: _ProdOperator,
    db: Annotated[Session, Depends(get_db)],
) -> PackSizeOut:
    return prod_service.create_pack_size(db, actor, payload)


@router.post("/catalog/materials", status_code=201)
def add_material(
    payload: CreateMaterialRequest,
    actor: _ProdOperator,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return prod_service.create_material(db, actor, payload)


# ── BOM Management & Versioning ─────────────────────────────────────────────


@router.get("/bom", response_model=list[BomHeaderOut])
def list_boms(actor: _ProdViewer, db: Annotated[Session, Depends(get_db)]) -> list[BomHeaderOut]:
    return prod_service.list_bom_headers(db, actor)


@router.get("/bom/{pack_size_id}", response_model=BomHeaderOut)
def get_bom(
    pack_size_id: int, actor: _ProdViewer, db: Annotated[Session, Depends(get_db)]
) -> BomHeaderOut:
    return prod_service.get_bom_for_pack_size(db, actor, pack_size_id)


@router.post("/bom/versions", response_model=BomVersionOut, status_code=201)
def create_bom_version(
    payload: CreateBomVersionRequest,
    actor: _ProdOperator,
    db: Annotated[Session, Depends(get_db)],
) -> BomVersionOut:
    return prod_service.create_bom_version(db, actor, payload)


@router.put("/bom/versions/{version_id}", response_model=BomVersionOut)
def update_draft_bom_version(
    version_id: int,
    payload: UpdateDraftBomVersionRequest,
    actor: _ProdOperator,
    db: Annotated[Session, Depends(get_db)],
) -> BomVersionOut:
    return prod_service.update_draft_bom_version(db, actor, version_id, payload)


@router.post("/bom/versions/{version_id}/activate", response_model=BomVersionOut)
def activate_bom_version(
    version_id: int,
    actor: _ProdOperator,
    db: Annotated[Session, Depends(get_db)],
) -> BomVersionOut:
    return prod_service.activate_bom_version(db, actor, version_id)


@router.delete("/bom/versions/{version_id}", status_code=204)
def delete_bom_version(
    version_id: int,
    actor: _ProdOperator,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    prod_service.delete_bom_version(db, actor, version_id)


@router.post("/bom/calculate", response_model=BomCalculationOut)
def calculate_bom_post(
    payload: BomCalculateRequest,
    actor: _ProdViewer,
    db: Annotated[Session, Depends(get_db)],
) -> BomCalculationOut:
    return prod_service.calculate_bom_requirements(db, actor, payload)


@router.get("/bom/{pack_size_id}/calculate", response_model=BomCalculationOut)
def calculate_bom_get(
    pack_size_id: int,
    actor: _ProdViewer,
    db: Annotated[Session, Depends(get_db)],
    batch_multiplier: Annotated[Decimal | None, Query(gt=0)] = None,
    target_output_pkts: Annotated[int | None, Query(gt=0)] = None,
    bom_version_id: Annotated[int | None, Query(gt=0)] = None,
) -> BomCalculationOut:
    payload = BomCalculateRequest(
        pack_size_id=pack_size_id,
        batch_multiplier=batch_multiplier,
        target_output_pkts=target_output_pkts,
        bom_version_id=bom_version_id,
    )
    return prod_service.calculate_bom_requirements(db, actor, payload)


# ── Production Planning, Material Issue, Execution, Posting ──────────────────


@router.get("/dashboard", response_model=ProductionDashboardOut)
def get_dashboard(
    actor: _ProdViewer,
    db: Annotated[Session, Depends(get_db)],
    status: str | None = Query(None),
    pack_size_id: int | None = Query(None, gt=0),
) -> ProductionDashboardOut:
    return prod_service.get_production_dashboard(
        db, actor, status=status, pack_size_id=pack_size_id
    )


@router.get("/runs/{run_id}", response_model=ProductionRunOut)
def get_run(
    run_id: int, actor: _ProdViewer, db: Annotated[Session, Depends(get_db)]
) -> ProductionRunOut:
    return prod_service.get_production_run_detail(db, actor, run_id)


@router.post("/runs", response_model=ProductionRunOut, status_code=201)
def create_run(
    payload: CreateProductionRunRequest,
    actor: _ProdOperator,
    db: Annotated[Session, Depends(get_db)],
) -> ProductionRunOut:
    return prod_service.create_production_run(db, actor, payload)


@router.post("/runs/{run_id}/plan", response_model=ProductionRunOut)
def plan_run(
    run_id: int, actor: _ProdOperator, db: Annotated[Session, Depends(get_db)]
) -> ProductionRunOut:
    return prod_service.plan_production_run(db, actor, run_id)


@router.post("/runs/{run_id}/issue-materials", response_model=ProductionRunOut)
def issue_materials_and_start(
    run_id: int,
    payload: StartProductionRequest,
    actor: _ProdOperator,
    db: Annotated[Session, Depends(get_db)],
) -> ProductionRunOut:
    return prod_service.issue_materials_and_start_run(db, actor, run_id, payload)


@router.post("/runs/{run_id}/complete", response_model=ProductionRunOut)
def complete_run(
    run_id: int,
    payload: CompleteProductionRequest,
    actor: _ProdOperator,
    db: Annotated[Session, Depends(get_db)],
) -> ProductionRunOut:
    return prod_service.complete_production_run(db, actor, run_id, payload)


@router.post("/runs/{run_id}/post", response_model=ProductionRunOut)
def post_run(
    run_id: int, actor: _ProdOperator, db: Annotated[Session, Depends(get_db)]
) -> ProductionRunOut:
    return prod_service.post_production_run(db, actor, run_id)


@router.post("/runs/{run_id}/cancel", response_model=ProductionRunOut)
def cancel_run(
    run_id: int,
    payload: CancelProductionRequest,
    actor: _ProdOperator,
    db: Annotated[Session, Depends(get_db)],
) -> ProductionRunOut:
    return prod_service.cancel_production_run(db, actor, run_id, payload)


# ── Alerts & Variance Report ────────────────────────────────────────────────


@router.get("/alerts", response_model=list[VarianceAlertOut])
def get_alerts(
    actor: _ProdViewer,
    db: Annotated[Session, Depends(get_db)],
    status: str | None = Query(None),
) -> list[VarianceAlertOut]:
    return prod_service.list_alerts(db, actor, status=status)


@router.post("/alerts/{alert_id}/acknowledge", response_model=VarianceAlertOut)
def ack_alert(
    alert_id: int,
    payload: AcknowledgeAlertRequest,
    actor: _AlertAckActor,
    db: Annotated[Session, Depends(get_db)],
) -> VarianceAlertOut:
    return prod_service.acknowledge_alert(db, actor, alert_id, payload.note)


@router.get("/reports/variances", response_model=list[ProductionVarianceReportRow])
def variance_report(
    actor: _ProdViewer, db: Annotated[Session, Depends(get_db)]
) -> list[ProductionVarianceReportRow]:
    return prod_service.list_production_variance_report(db, actor)
