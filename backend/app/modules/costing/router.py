"""Phase 9 Costing & Overhead Allocation API router."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.costing import service as costing_service
from app.modules.costing.schemas import (
    AddMonthlyPoolOverheadRequest,
    AddRunOverheadRequest,
    CostingDashboardOut,
    FinalizeRunCostingRequest,
    ProductionOverheadOut,
    RunCostingDetailOut,
    VoidOverheadRequest,
)
from app.modules.iam import service as iam_service
from app.modules.iam.schemas import CurrentActor

router = APIRouter(prefix="/costing", tags=["Product Costing & Overheads"])

_CostViewer = Annotated[
    CurrentActor,
    Depends(
        iam_service.require_roles(
            "FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "ACCOUNTANT_AUDITOR", "OWNER"
        )
    ),
]
_CostOperator = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN", "PRODUCTION_SUPERVISOR")),
]
_AdminOnly = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN")),
]


@router.get("/dashboard", response_model=CostingDashboardOut)
def get_costing_dashboard(
    actor: _CostViewer,
    db: Annotated[Session, Depends(get_db)],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    pack_size_id: Annotated[int | None, Query(gt=0)] = None,
) -> CostingDashboardOut:
    return costing_service.get_costing_dashboard(
        db, actor, date_from=date_from, date_to=date_to, pack_size_id=pack_size_id
    )


@router.get("/runs/{run_id}", response_model=RunCostingDetailOut)
def get_run_costing(
    run_id: int,
    actor: _CostViewer,
    db: Annotated[Session, Depends(get_db)],
) -> RunCostingDetailOut:
    return costing_service.get_run_costing_detail(db, actor, run_id)


@router.post("/runs/{run_id}/overheads", response_model=RunCostingDetailOut, status_code=201)
def add_run_overhead(
    run_id: int,
    payload: AddRunOverheadRequest,
    actor: _CostOperator,
    db: Annotated[Session, Depends(get_db)],
) -> RunCostingDetailOut:
    return costing_service.add_run_overhead(db, actor, run_id, payload)


@router.post("/runs/{run_id}/finalize", response_model=RunCostingDetailOut)
def finalize_run_costing(
    run_id: int,
    payload: FinalizeRunCostingRequest,
    actor: _CostOperator,
    db: Annotated[Session, Depends(get_db)],
) -> RunCostingDetailOut:
    return costing_service.finalize_run_costing(db, actor, run_id, payload)


@router.post("/overheads/{overhead_id}/void")
def void_overhead(
    overhead_id: int,
    payload: VoidOverheadRequest,
    actor: _AdminOnly,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return costing_service.void_overhead(db, actor, overhead_id, payload)


@router.post("/monthly-pools", response_model=ProductionOverheadOut, status_code=201)
def add_monthly_pool_overhead(
    payload: AddMonthlyPoolOverheadRequest,
    actor: _CostOperator,
    db: Annotated[Session, Depends(get_db)],
) -> ProductionOverheadOut:
    return costing_service.add_monthly_pool_overhead(db, actor, payload)


@router.post("/monthly-pools/{period_month}/reallocate")
def reallocate_monthly_pool(
    period_month: str,
    actor: _CostOperator,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return costing_service.reallocate_monthly_pool(db, actor, period_month)
