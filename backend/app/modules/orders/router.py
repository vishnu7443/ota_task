from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.iam import service as iam_service
from app.modules.iam.schemas import CurrentActor
from app.modules.orders import service as orders_service
from app.modules.orders.schemas import (
    AdminApproveRequest,
    AdminModifyOrderRequest,
    AdminOrdersSummaryResponse,
    AdminReasonRequest,
    AdminReviewHoldRequest,
    CreateOrderRequest,
    OrderDetailResponse,
    OrderReasonRequest,
    PaginatedOrdersResponse,
    SalesmanResubmitRequest,
)
from app.modules.orders.state_machine import PENDING_VERIFICATION_STATUSES

salesman_orders_router = APIRouter(prefix="/orders", tags=["Salesman Orders"])
admin_orders_router = APIRouter(prefix="/admin/orders", tags=["Admin Order Management"])

_SalesmanActor = Annotated[CurrentActor, Depends(iam_service.require_roles("SALESMAN"))]
_StaffActor = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("SALESMAN", "FACTORY_ADMIN", "OWNER", "ACCOUNTANT_AUDITOR")),
]
_AdminViewerActor = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN", "OWNER", "ACCOUNTANT_AUDITOR")),
]
_FactoryAdminActor = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN")),
]


@salesman_orders_router.post(
    "",
    response_model=OrderDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_order(
    payload: CreateOrderRequest,
    response: Response,
    actor: _SalesmanActor,
    db: Annotated[Session, Depends(get_db)],
) -> OrderDetailResponse:
    detail, is_duplicate = orders_service.submit_sales_order(db, actor, payload)
    if is_duplicate:
        response.status_code = status.HTTP_200_OK
    return detail


@salesman_orders_router.get("/my", response_model=PaginatedOrdersResponse)
def list_my_orders(
    actor: _SalesmanActor,
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=80)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedOrdersResponse:
    statuses = [s.strip() for s in status_filter.split(",") if s.strip()] if status_filter else None
    return orders_service.list_paginated_orders(
        db,
        salesman_id=actor.user_id,
        statuses=statuses,
        search=search,
        page=page,
        page_size=page_size,
    )


@salesman_orders_router.get("/{order_id}", response_model=OrderDetailResponse)
def get_order_for_salesman_or_staff(
    order_id: int,
    actor: _StaffActor,
    db: Annotated[Session, Depends(get_db)],
) -> OrderDetailResponse:
    return orders_service.get_order_detail(db, actor, order_id)


@salesman_orders_router.put("/{order_id}", response_model=OrderDetailResponse)
def resubmit_corrected_order(
    order_id: int,
    payload: SalesmanResubmitRequest,
    actor: _SalesmanActor,
    db: Annotated[Session, Depends(get_db)],
) -> OrderDetailResponse:
    return orders_service.salesman_resubmit_order(db, actor, order_id, payload)


@salesman_orders_router.post("/{order_id}/cancel", response_model=OrderDetailResponse)
def salesman_cancel_order(
    order_id: int,
    payload: OrderReasonRequest,
    actor: _SalesmanActor,
    db: Annotated[Session, Depends(get_db)],
) -> OrderDetailResponse:
    return orders_service.cancel_order(db, actor, order_id, payload)


@admin_orders_router.get("/summary", response_model=AdminOrdersSummaryResponse)
def get_admin_queue_summary(
    _actor: _AdminViewerActor,
    db: Annotated[Session, Depends(get_db)],
) -> AdminOrdersSummaryResponse:
    return orders_service.get_admin_orders_summary(db)


@admin_orders_router.get("", response_model=PaginatedOrdersResponse)
def list_incoming_orders(
    _actor: _AdminViewerActor,
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    pending_verification: bool = False,
    customer_id: Annotated[int | None, Query(gt=0)] = None,
    salesman_id: Annotated[int | None, Query(gt=0)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    has_shortage: bool | None = None,
    search: Annotated[str | None, Query(max_length=80)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedOrdersResponse:
    if pending_verification and not status_filter:
        statuses = PENDING_VERIFICATION_STATUSES
    elif status_filter:
        statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
    else:
        statuses = None

    return orders_service.list_paginated_orders(
        db,
        salesman_id=salesman_id,
        customer_id=customer_id,
        statuses=statuses,
        date_from=date_from,
        date_to=date_to,
        has_shortage=has_shortage,
        search=search,
        page=page,
        page_size=page_size,
    )


@admin_orders_router.get("/{order_id}", response_model=OrderDetailResponse)
def get_admin_order_detail(
    order_id: int,
    actor: _AdminViewerActor,
    db: Annotated[Session, Depends(get_db)],
) -> OrderDetailResponse:
    return orders_service.get_order_detail(db, actor, order_id)


@admin_orders_router.patch("/{order_id}", response_model=OrderDetailResponse)
def modify_order_details(
    order_id: int,
    payload: AdminModifyOrderRequest,
    actor: _FactoryAdminActor,
    db: Annotated[Session, Depends(get_db)],
) -> OrderDetailResponse:
    return orders_service.admin_modify_order(db, actor, order_id, payload)


@admin_orders_router.post("/{order_id}/review", response_model=OrderDetailResponse)
def mark_order_under_review(
    order_id: int,
    payload: AdminReviewHoldRequest,
    actor: _FactoryAdminActor,
    db: Annotated[Session, Depends(get_db)],
) -> OrderDetailResponse:
    return orders_service.admin_mark_under_review(db, actor, order_id, payload)


@admin_orders_router.post("/{order_id}/request-correction", response_model=OrderDetailResponse)
def request_order_correction(
    order_id: int,
    payload: AdminReasonRequest,
    actor: _FactoryAdminActor,
    db: Annotated[Session, Depends(get_db)],
) -> OrderDetailResponse:
    return orders_service.admin_request_correction(db, actor, order_id, payload)


@admin_orders_router.post("/{order_id}/approve", response_model=OrderDetailResponse)
def approve_order(
    order_id: int,
    payload: AdminApproveRequest,
    actor: _FactoryAdminActor,
    db: Annotated[Session, Depends(get_db)],
) -> OrderDetailResponse:
    return orders_service.admin_approve_order(db, actor, order_id, payload)


@admin_orders_router.post("/{order_id}/reject", response_model=OrderDetailResponse)
def reject_order(
    order_id: int,
    payload: AdminReasonRequest,
    actor: _FactoryAdminActor,
    db: Annotated[Session, Depends(get_db)],
) -> OrderDetailResponse:
    return orders_service.admin_reject_order(db, actor, order_id, payload)


@admin_orders_router.post("/{order_id}/cancel", response_model=OrderDetailResponse)
def admin_cancel_order(
    order_id: int,
    payload: AdminReasonRequest,
    actor: _FactoryAdminActor,
    db: Annotated[Session, Depends(get_db)],
) -> OrderDetailResponse:
    return orders_service.cancel_order(db, actor, order_id, payload)
