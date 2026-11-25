from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.iam import service as iam_service
from app.modules.iam.schemas import CurrentActor
from app.modules.inventory import service as inventory_service
from app.modules.inventory.schemas import (
    InventoryDashboardResponse,
    InventoryLedgerEntryResponse,
    MaterialSummaryResponse,
    StockAdjustmentActionReasonRequest,
    StockAdjustmentCreateRequest,
    StockAdjustmentResponse,
    StockReportsSummaryResponse,
)
from app.modules.purchasing import service as purchasing_service

router = APIRouter(prefix="/inventory", tags=["Inventory & Stock Management"])

_InventoryViewer = Annotated[
    CurrentActor,
    Depends(
        iam_service.require_roles(
            "FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "ACCOUNTANT_AUDITOR", "OWNER"
        )
    ),
]
_InventoryOperator = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN", "PRODUCTION_SUPERVISOR")),
]
_FactoryAdmin = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN")),
]


@router.get("/materials", response_model=list[MaterialSummaryResponse])
def list_materials(
    _actor: _InventoryViewer,
    db: Annotated[Session, Depends(get_db)],
    category: str | None = None,
    search: Annotated[str | None, Query(max_length=80)] = None,
) -> list[MaterialSummaryResponse]:
    return inventory_service.list_materials(db, category=category, search=search)


@router.get("/overview", response_model=InventoryDashboardResponse)
def get_inventory_overview(
    _actor: _InventoryViewer,
    db: Annotated[Session, Depends(get_db)],
    item_category: str | None = None,
    low_stock_only: bool = False,
    search: Annotated[str | None, Query(max_length=80)] = None,
) -> InventoryDashboardResponse:
    return inventory_service.get_inventory_overview(
        db,
        item_category=item_category,
        low_stock_only=low_stock_only,
        search=search,
    )


@router.get("/ledger", response_model=list[InventoryLedgerEntryResponse])
def list_inventory_ledger(
    _actor: _InventoryViewer,
    db: Annotated[Session, Depends(get_db)],
    item_category: str | None = None,
    material_id: Annotated[int | None, Query(gt=0)] = None,
    pack_size_id: Annotated[int | None, Query(gt=0)] = None,
    movement_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[InventoryLedgerEntryResponse]:
    from datetime import date

    df = date.fromisoformat(date_from) if date_from else None
    dt = date.fromisoformat(date_to) if date_to else None
    return inventory_service.list_ledger_entries(
        db,
        item_category=item_category,
        material_id=material_id,
        pack_size_id=pack_size_id,
        movement_type=movement_type,
        date_from=df,
        date_to=dt,
        limit=limit,
    )


@router.get("/adjustments", response_model=list[StockAdjustmentResponse])
def list_stock_adjustments(
    _actor: _InventoryViewer,
    db: Annotated[Session, Depends(get_db)],
    status: str | None = None,
    item_category: str | None = None,
) -> list[StockAdjustmentResponse]:
    return inventory_service.list_adjustments(db, status=status, item_category=item_category)


@router.post("/adjustments", response_model=StockAdjustmentResponse, status_code=201)
def create_stock_adjustment(
    payload: StockAdjustmentCreateRequest,
    actor: _InventoryOperator,
    db: Annotated[Session, Depends(get_db)],
) -> StockAdjustmentResponse:
    return inventory_service.create_stock_adjustment(db, actor, payload)


@router.post("/adjustments/{adjustment_id}/approve", response_model=StockAdjustmentResponse)
def approve_stock_adjustment(
    adjustment_id: int,
    actor: _FactoryAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> StockAdjustmentResponse:
    return inventory_service.approve_stock_adjustment(db, actor, adjustment_id)


@router.post("/adjustments/{adjustment_id}/reject", response_model=StockAdjustmentResponse)
def reject_stock_adjustment(
    adjustment_id: int,
    payload: StockAdjustmentActionReasonRequest,
    actor: _FactoryAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> StockAdjustmentResponse:
    return inventory_service.reject_stock_adjustment(db, actor, adjustment_id, payload.reason)


@router.get("/reports/summary", response_model=StockReportsSummaryResponse)
def get_stock_reports_summary(
    _actor: _InventoryViewer,
    db: Annotated[Session, Depends(get_db)],
    date_from: str | None = None,
    date_to: str | None = None,
) -> StockReportsSummaryResponse:
    from datetime import date

    df = date.fromisoformat(date_from) if date_from else None
    dt = date.fromisoformat(date_to) if date_to else None
    overview = inventory_service.get_inventory_overview(db)
    low_stock = [i for i in overview.items if i.is_low_stock]
    receipt_rows = purchasing_service.list_purchase_receipt_report_rows(
        db, date_from=df, date_to=dt
    )
    adjustments = inventory_service.list_adjustments(db)
    return StockReportsSummaryResponse(
        current_stock=overview.items,
        low_stock_items=low_stock,
        purchase_receipts=receipt_rows,
        adjustments=adjustments,
    )
