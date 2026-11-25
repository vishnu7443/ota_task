"""Billing, GST Invoices, Credit Notes, PDF Export, Dispatch, Delivery & Reports API router."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.billing import service as billing_service
from app.modules.billing.schemas import (
    BillingDashboardOut,
    BillingReportsBundleOut,
    CreateCreditNoteRequest,
    CreateDispatchRequest,
    CreateInvoiceRequest,
    CreditNoteOut,
    DispatchActionRemarksRequest,
    DispatchDashboardOut,
    DispatchOut,
    InvoiceDetailOut,
    InvoiceSummaryOut,
    IssueInvoiceRequest,
    UpdateDeliveryStatusRequest,
    VerifyInvoiceRequest,
)
from app.modules.iam import service as iam_service
from app.modules.iam.schemas import CurrentActor

router = APIRouter(prefix="/billing", tags=["GST Billing & Dispatch"])

_BillingViewer = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN", "ACCOUNTANT_AUDITOR", "OWNER")),
]
_BillingOperator = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN")),
]
_InvoiceReader = Annotated[
    CurrentActor,
    Depends(
        iam_service.require_roles("SALESMAN", "FACTORY_ADMIN", "ACCOUNTANT_AUDITOR", "OWNER")
    ),
]


# ── Invoices ────────────────────────────────────────────────────────────────


@router.get("/dashboard", response_model=BillingDashboardOut)
def get_billing_dashboard(
    actor: _BillingViewer,
    db: Annotated[Session, Depends(get_db)],
    doc_status: str | None = Query(None),
    dispatch_status: str | None = Query(None),
    search: str | None = Query(None, max_length=80),
) -> BillingDashboardOut:
    return billing_service.get_billing_dashboard(
        db, actor, doc_status=doc_status, dispatch_status=dispatch_status, search=search
    )


@router.get("/invoices", response_model=list[InvoiceSummaryOut])
def list_invoices(
    actor: _BillingViewer,
    db: Annotated[Session, Depends(get_db)],
    doc_status: str | None = Query(None),
    dispatch_status: str | None = Query(None),
    search: str | None = Query(None, max_length=80),
) -> list[InvoiceSummaryOut]:
    return billing_service.list_invoices_view(
        db, actor, doc_status=doc_status, dispatch_status=dispatch_status, search=search
    )


@router.post("/invoices", response_model=InvoiceDetailOut, status_code=201)
def create_invoice(
    payload: CreateInvoiceRequest,
    actor: _BillingOperator,
    db: Annotated[Session, Depends(get_db)],
) -> InvoiceDetailOut:
    return billing_service.create_invoice_from_order(db, actor, payload)


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailOut)
def get_invoice(
    invoice_id: int,
    actor: _InvoiceReader,
    db: Annotated[Session, Depends(get_db)],
) -> InvoiceDetailOut:
    return billing_service.get_invoice_detail_scoped(db, actor, invoice_id)


@router.post("/invoices/{invoice_id}/verify", response_model=InvoiceDetailOut)
def verify_invoice(
    invoice_id: int,
    payload: VerifyInvoiceRequest,
    actor: _BillingOperator,
    db: Annotated[Session, Depends(get_db)],
) -> InvoiceDetailOut:
    return billing_service.verify_invoice(db, actor, invoice_id, payload)


@router.post("/invoices/{invoice_id}/issue", response_model=InvoiceDetailOut)
def issue_invoice(
    invoice_id: int,
    payload: IssueInvoiceRequest,
    actor: _BillingOperator,
    db: Annotated[Session, Depends(get_db)],
) -> InvoiceDetailOut:
    return billing_service.issue_invoice(db, actor, invoice_id, payload)


@router.get("/invoices/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: int,
    actor: _InvoiceReader,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    pdf_bytes, filename = billing_service.generate_invoice_pdf_scoped(db, actor, invoice_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ── Credit Notes ────────────────────────────────────────────────────────────


@router.get("/credit-notes", response_model=list[CreditNoteOut])
def list_credit_notes(
    actor: _BillingViewer, db: Annotated[Session, Depends(get_db)]
) -> list[CreditNoteOut]:
    return billing_service.list_credit_notes_view(db, actor)


@router.post("/credit-notes", response_model=CreditNoteOut, status_code=201)
def create_credit_note(
    payload: CreateCreditNoteRequest,
    actor: _BillingOperator,
    db: Annotated[Session, Depends(get_db)],
) -> CreditNoteOut:
    return billing_service.create_credit_note(db, actor, payload)


@router.post("/credit-notes/{cn_id}/issue", response_model=CreditNoteOut)
def issue_credit_note(
    cn_id: int, actor: _BillingOperator, db: Annotated[Session, Depends(get_db)]
) -> CreditNoteOut:
    return billing_service.issue_credit_note(db, actor, cn_id)


# ── Dispatches & Delivery Tracking ──────────────────────────────────────────


@router.get("/dispatches/dashboard", response_model=DispatchDashboardOut)
def get_dispatch_dashboard(
    actor: _BillingViewer,
    db: Annotated[Session, Depends(get_db)],
    status: str | None = Query(None),
) -> DispatchDashboardOut:
    return billing_service.get_dispatch_dashboard(db, actor, status=status)


@router.post("/dispatches", response_model=DispatchOut, status_code=201)
def create_dispatch(
    payload: CreateDispatchRequest,
    actor: _BillingOperator,
    db: Annotated[Session, Depends(get_db)],
) -> DispatchOut:
    return billing_service.create_dispatch(db, actor, payload)


@router.get("/dispatches/{dispatch_id}", response_model=DispatchOut)
def get_dispatch(
    dispatch_id: int,
    actor: _InvoiceReader,
    db: Annotated[Session, Depends(get_db)],
) -> DispatchOut:
    return billing_service.get_dispatch_detail_scoped(db, actor, dispatch_id)


@router.post("/dispatches/{dispatch_id}/ready", response_model=DispatchOut)
def mark_dispatch_ready(
    dispatch_id: int,
    payload: DispatchActionRemarksRequest,
    actor: _BillingOperator,
    db: Annotated[Session, Depends(get_db)],
) -> DispatchOut:
    return billing_service.mark_dispatch_ready(db, actor, dispatch_id, payload)


@router.post("/dispatches/{dispatch_id}/post", response_model=DispatchOut)
def post_dispatch(
    dispatch_id: int,
    payload: DispatchActionRemarksRequest,
    actor: _BillingOperator,
    db: Annotated[Session, Depends(get_db)],
) -> DispatchOut:
    return billing_service.post_dispatch(db, actor, dispatch_id, payload)


@router.post("/dispatches/{dispatch_id}/delivery", response_model=DispatchOut)
def update_delivery(
    dispatch_id: int,
    payload: UpdateDeliveryStatusRequest,
    actor: _BillingOperator,
    db: Annotated[Session, Depends(get_db)],
) -> DispatchOut:
    return billing_service.update_delivery_status(db, actor, dispatch_id, payload)


# ── Reports ─────────────────────────────────────────────────────────────────


@router.get("/reports", response_model=BillingReportsBundleOut)
def get_billing_reports(
    actor: _BillingViewer,
    db: Annotated[Session, Depends(get_db)],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> BillingReportsBundleOut:
    return billing_service.get_billing_reports_bundle(db, actor, date_from=date_from, date_to=date_to)
