"""Phase 9 Finance API router — Payments, Invoice Allocation, Receipts, AR, Ageing & Profitability."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.finance import service as finance_service
from app.modules.finance.schemas import (
    AgeingReportOut,
    AllocatePaymentRequest,
    CustomerStatementOut,
    FinanceDashboardOut,
    OpenInvoiceForAllocationOut,
    PaginatedCustomerArOut,
    PaginatedPaymentsOut,
    PaymentOut,
    ProfitabilityReportOut,
    RecordPaymentRequest,
    RefundPaymentRequest,
    ReverseAllocationRequest,
    ReversePaymentRequest,
    SalesmanCustomerArOut,
)
from app.modules.iam import service as iam_service
from app.modules.iam.schemas import CurrentActor

router = APIRouter(prefix="/finance", tags=["Payments, AR & Profitability"])

_FinanceOperator = Annotated[
    CurrentActor, Depends(iam_service.require_roles("FACTORY_ADMIN"))
]
_FinanceViewer = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN", "ACCOUNTANT_AUDITOR", "OWNER")),
]
_SalesmanOnly = Annotated[CurrentActor, Depends(iam_service.require_roles("SALESMAN"))]


@router.get("/dashboard", response_model=FinanceDashboardOut)
def get_finance_dashboard(
    actor: _FinanceViewer,
    db: Annotated[Session, Depends(get_db)],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> FinanceDashboardOut:
    return finance_service.get_financial_dashboard(db, actor, date_from=date_from, date_to=date_to)


@router.get("/payments", response_model=PaginatedPaymentsOut)
def list_payments(
    actor: _FinanceViewer,
    db: Annotated[Session, Depends(get_db)],
    customer_id: Annotated[int | None, Query(gt=0)] = None,
    status: Annotated[str | None, Query()] = None,
    payment_mode: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=80)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedPaymentsOut:
    return finance_service.list_payments_paginated(
        db,
        actor,
        customer_id=customer_id,
        status=status,
        payment_mode=payment_mode,
        date_from=date_from,
        date_to=date_to,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.post("/payments", response_model=PaymentOut, status_code=201)
def record_payment(
    payload: RecordPaymentRequest,
    actor: _FinanceOperator,
    db: Annotated[Session, Depends(get_db)],
) -> PaymentOut:
    return finance_service.record_customer_payment(db, actor, payload)


@router.get("/payments/{payment_id}", response_model=PaymentOut)
def get_payment(
    payment_id: int,
    actor: _FinanceViewer,
    db: Annotated[Session, Depends(get_db)],
) -> PaymentOut:
    return finance_service.get_payment_detail(db, actor, payment_id)


@router.post("/payments/{payment_id}/allocate", response_model=PaymentOut)
def allocate_payment(
    payment_id: int,
    payload: AllocatePaymentRequest,
    actor: _FinanceOperator,
    db: Annotated[Session, Depends(get_db)],
) -> PaymentOut:
    return finance_service.allocate_payment(db, actor, payment_id, payload)


@router.post("/payments/{payment_id}/reverse", response_model=PaymentOut)
def reverse_payment(
    payment_id: int,
    payload: ReversePaymentRequest,
    actor: _FinanceOperator,
    db: Annotated[Session, Depends(get_db)],
) -> PaymentOut:
    return finance_service.reverse_payment(db, actor, payment_id, payload)


@router.post("/payments/{payment_id}/refund", response_model=PaymentOut)
def refund_payment(
    payment_id: int,
    payload: RefundPaymentRequest,
    actor: _FinanceOperator,
    db: Annotated[Session, Depends(get_db)],
) -> PaymentOut:
    return finance_service.refund_payment(db, actor, payment_id, payload)


@router.post("/allocations/{allocation_id}/reverse", response_model=PaymentOut)
def reverse_allocation(
    allocation_id: int,
    payload: ReverseAllocationRequest,
    actor: _FinanceOperator,
    db: Annotated[Session, Depends(get_db)],
) -> PaymentOut:
    return finance_service.reverse_allocation(db, actor, allocation_id, payload)


@router.get("/payments/{payment_id}/receipt-pdf")
def download_payment_receipt_pdf(
    payment_id: int,
    actor: _FinanceViewer,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    pdf_bytes, filename = finance_service.generate_payment_receipt_pdf(db, actor, payment_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/receivables", response_model=PaginatedCustomerArOut)
def list_receivables(
    actor: _FinanceViewer,
    db: Annotated[Session, Depends(get_db)],
    as_of_date: Annotated[date | None, Query()] = None,
    customer_id: Annotated[int | None, Query(gt=0)] = None,
    search: Annotated[str | None, Query(max_length=80)] = None,
    only_outstanding: Annotated[bool, Query()] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedCustomerArOut:
    return finance_service.get_customer_receivables_summary(
        db,
        actor,
        as_of_date=as_of_date,
        customer_id=customer_id,
        search=search,
        only_outstanding=only_outstanding,
        page=page,
        page_size=page_size,
    )


@router.get("/receivables/ageing", response_model=AgeingReportOut)
def get_ageing_report(
    actor: _FinanceViewer,
    db: Annotated[Session, Depends(get_db)],
    as_of_date: Annotated[date | None, Query()] = None,
    customer_id: Annotated[int | None, Query(gt=0)] = None,
    search: Annotated[str | None, Query(max_length=80)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AgeingReportOut:
    return finance_service.get_ageing_report(
        db,
        actor,
        as_of_date=as_of_date,
        customer_id=customer_id,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/receivables/customers/{customer_id}/statement", response_model=CustomerStatementOut)
def get_customer_statement(
    customer_id: int,
    actor: _FinanceViewer,
    db: Annotated[Session, Depends(get_db)],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> CustomerStatementOut:
    return finance_service.get_customer_statement(
        db, actor, customer_id, date_from=date_from, date_to=date_to
    )


@router.get("/receivables/open-invoices/{customer_id}", response_model=list[OpenInvoiceForAllocationOut])
def get_open_invoices(
    customer_id: int,
    actor: _FinanceViewer,
    db: Annotated[Session, Depends(get_db)],
    as_of_date: Annotated[date | None, Query()] = None,
) -> list[OpenInvoiceForAllocationOut]:
    return finance_service.list_open_invoices_for_customer(
        db, actor, customer_id, as_of_date=as_of_date
    )


@router.get("/my-customers/receivables", response_model=list[SalesmanCustomerArOut])
def get_salesman_customer_receivables(
    actor: _SalesmanOnly,
    db: Annotated[Session, Depends(get_db)],
) -> list[SalesmanCustomerArOut]:
    return finance_service.get_salesman_customer_receivables(db, actor)


@router.get("/profitability", response_model=ProfitabilityReportOut)
def get_profitability_report(
    actor: _FinanceViewer,
    db: Annotated[Session, Depends(get_db)],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    customer_id: Annotated[int | None, Query(gt=0)] = None,
    pack_size_id: Annotated[int | None, Query(gt=0)] = None,
) -> ProfitabilityReportOut:
    return finance_service.get_profitability_report(
        db,
        actor,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        pack_size_id=pack_size_id,
    )
