from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.iam import service as iam_service
from app.modules.iam.schemas import CurrentActor
from app.modules.purchasing import service as purchasing_service
from app.modules.purchasing.schemas import (
    GoodsReceiptCreateRequest,
    GoodsReceiptDetailResponse,
    GoodsReceiptSummaryResponse,
    PurchaseOrderActionReasonRequest,
    PurchaseOrderCreateRequest,
    PurchaseOrderDetailResponse,
    PurchaseOrderSummaryResponse,
    SupplierCreateRequest,
    SupplierDetailResponse,
    SupplierResponse,
    SupplierUpdateRequest,
)

router = APIRouter(prefix="/purchasing", tags=["Purchasing & Goods Receipts"])

_PurchasingViewer = Annotated[
    CurrentActor,
    Depends(
        iam_service.require_roles(
            "FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "ACCOUNTANT_AUDITOR", "OWNER"
        )
    ),
]
_PurchasingOperator = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN", "PRODUCTION_SUPERVISOR")),
]
_FactoryAdmin = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN")),
]


# --- Suppliers ---


@router.get("/suppliers", response_model=list[SupplierResponse])
def list_suppliers(
    _actor: _PurchasingViewer,
    db: Annotated[Session, Depends(get_db)],
    active_only: bool = False,
    search: Annotated[str | None, Query(max_length=80)] = None,
) -> list[SupplierResponse]:
    return purchasing_service.list_suppliers(db, active_only=active_only, search=search)


@router.get("/suppliers/{supplier_id}", response_model=SupplierDetailResponse)
def get_supplier_detail(
    supplier_id: int,
    _actor: _PurchasingViewer,
    db: Annotated[Session, Depends(get_db)],
) -> SupplierDetailResponse:
    return purchasing_service.get_supplier_detail(db, supplier_id)


@router.post("/suppliers", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
def create_supplier(
    payload: SupplierCreateRequest,
    actor: _FactoryAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> SupplierResponse:
    return purchasing_service.create_supplier(db, actor, payload)


@router.put("/suppliers/{supplier_id}", response_model=SupplierResponse)
def update_supplier(
    supplier_id: int,
    payload: SupplierUpdateRequest,
    actor: _FactoryAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> SupplierResponse:
    return purchasing_service.update_supplier(db, actor, supplier_id, payload)


# --- Purchase Orders ---


@router.get("/orders", response_model=list[PurchaseOrderSummaryResponse])
def list_purchase_orders(
    _actor: _PurchasingViewer,
    db: Annotated[Session, Depends(get_db)],
    supplier_id: Annotated[int | None, Query(gt=0)] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=80)] = None,
) -> list[PurchaseOrderSummaryResponse]:
    return purchasing_service.list_purchase_orders(
        db, supplier_id=supplier_id, status=status_filter, search=search
    )


@router.get("/orders/{po_id}", response_model=PurchaseOrderDetailResponse)
def get_purchase_order_detail(
    po_id: int,
    _actor: _PurchasingViewer,
    db: Annotated[Session, Depends(get_db)],
) -> PurchaseOrderDetailResponse:
    return purchasing_service.get_purchase_order_detail(db, po_id)


@router.post(
    "/orders",
    response_model=PurchaseOrderDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_purchase_order(
    payload: PurchaseOrderCreateRequest,
    actor: _PurchasingOperator,
    db: Annotated[Session, Depends(get_db)],
) -> PurchaseOrderDetailResponse:
    return purchasing_service.create_purchase_order(db, actor, payload)


@router.post("/orders/{po_id}/submit", response_model=PurchaseOrderDetailResponse)
def submit_purchase_order(
    po_id: int,
    actor: _PurchasingOperator,
    db: Annotated[Session, Depends(get_db)],
) -> PurchaseOrderDetailResponse:
    return purchasing_service.submit_purchase_order(db, actor, po_id)


@router.post("/orders/{po_id}/approve", response_model=PurchaseOrderDetailResponse)
def approve_purchase_order(
    po_id: int,
    actor: _FactoryAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> PurchaseOrderDetailResponse:
    return purchasing_service.approve_purchase_order(db, actor, po_id)


@router.post("/orders/{po_id}/reject", response_model=PurchaseOrderDetailResponse)
def reject_purchase_order(
    po_id: int,
    payload: PurchaseOrderActionReasonRequest,
    actor: _FactoryAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> PurchaseOrderDetailResponse:
    return purchasing_service.reject_purchase_order(db, actor, po_id, payload.reason)


@router.post("/orders/{po_id}/cancel", response_model=PurchaseOrderDetailResponse)
def cancel_purchase_order(
    po_id: int,
    payload: PurchaseOrderActionReasonRequest,
    actor: _FactoryAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> PurchaseOrderDetailResponse:
    return purchasing_service.cancel_purchase_order(db, actor, po_id, payload.reason)


# --- Goods Receipts ---


@router.get("/receipts", response_model=list[GoodsReceiptSummaryResponse])
def list_goods_receipts(
    _actor: _PurchasingViewer,
    db: Annotated[Session, Depends(get_db)],
    supplier_id: Annotated[int | None, Query(gt=0)] = None,
    purchase_order_id: Annotated[int | None, Query(gt=0)] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: Annotated[str | None, Query(max_length=80)] = None,
) -> list[GoodsReceiptSummaryResponse]:
    return purchasing_service.list_goods_receipts(
        db,
        supplier_id=supplier_id,
        purchase_order_id=purchase_order_id,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )


@router.get("/receipts/{receipt_id}", response_model=GoodsReceiptDetailResponse)
def get_goods_receipt_detail(
    receipt_id: int,
    _actor: _PurchasingViewer,
    db: Annotated[Session, Depends(get_db)],
) -> GoodsReceiptDetailResponse:
    return purchasing_service.get_goods_receipt_detail(db, receipt_id)


@router.post(
    "/receipts",
    response_model=GoodsReceiptDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_goods_receipt(
    payload: GoodsReceiptCreateRequest,
    response: Response,
    actor: _PurchasingOperator,
    db: Annotated[Session, Depends(get_db)],
) -> GoodsReceiptDetailResponse:
    detail, is_dup = purchasing_service.create_goods_receipt(db, actor, payload)
    if is_dup:
        response.status_code = status.HTTP_200_OK
    return detail


@router.post("/receipts/{receipt_id}/submit", response_model=GoodsReceiptDetailResponse)
def submit_goods_receipt(
    receipt_id: int,
    actor: _PurchasingOperator,
    db: Annotated[Session, Depends(get_db)],
) -> GoodsReceiptDetailResponse:
    return purchasing_service.submit_goods_receipt(db, actor, receipt_id)


@router.post("/receipts/{receipt_id}/verify", response_model=GoodsReceiptDetailResponse)
def verify_goods_receipt(
    receipt_id: int,
    actor: _PurchasingOperator,
    db: Annotated[Session, Depends(get_db)],
) -> GoodsReceiptDetailResponse:
    return purchasing_service.verify_goods_receipt(db, actor, receipt_id)


@router.post("/receipts/{receipt_id}/post", response_model=GoodsReceiptDetailResponse)
def post_goods_receipt(
    receipt_id: int,
    actor: _PurchasingOperator,
    db: Annotated[Session, Depends(get_db)],
) -> GoodsReceiptDetailResponse:
    return purchasing_service.post_goods_receipt(db, actor, receipt_id)
