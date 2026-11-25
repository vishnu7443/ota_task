"""Billing repository — FY sequential allocation, row locks, and dispatch aggregation."""

from datetime import date

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from app.modules.audit.models import AuditLog
from app.modules.billing.models import (
    CreditNote,
    Dispatch,
    DispatchItem,
    FiscalSequence,
    Invoice,
)
from app.modules.inventory.models import CostLot
from app.modules.orders.models import SalesOrder


def allocate_fiscal_sequence(
    db: Session,
    *,
    doc_type: str,
    financial_year: str,
    prefix: str,
) -> str:
    """Concurrency-safe gap-free FY counter (`PREFIX/YYYY-YY/0001`) locked FOR UPDATE."""
    stmt_ins = (
        pg_insert(FiscalSequence)
        .values(doc_type=doc_type, financial_year=financial_year, prefix=prefix, last_seq_no=0)
        .on_conflict_do_nothing(index_elements=["doc_type", "financial_year"])
    )
    db.execute(stmt_ins)
    db.flush()

    row = (
        db.execute(
            select(FiscalSequence)
            .where(
                FiscalSequence.doc_type == doc_type,
                FiscalSequence.financial_year == financial_year,
            )
            .with_for_update()
        )
        .scalar_one()
    )
    row.last_seq_no += 1
    db.flush()
    return f"{row.prefix}/{row.financial_year}/{row.last_seq_no:04d}"


def get_invoice(db: Session, invoice_id: int, *, for_update: bool = False) -> Invoice | None:
    stmt = (
        select(Invoice)
        .options(
            selectinload(Invoice.items),
            selectinload(Invoice.tax_components),
            selectinload(Invoice.credit_notes).selectinload(CreditNote.items),
            selectinload(Invoice.dispatches).selectinload(Dispatch.items),
            selectinload(Invoice.dispatches).selectinload(Dispatch.status_history),
        )
        .execution_options(populate_existing=True)
        .where(Invoice.id == invoice_id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def get_active_invoice_for_order(db: Session, sales_order_id: int) -> Invoice | None:
    stmt = select(Invoice).where(
        Invoice.sales_order_id == sales_order_id,
        Invoice.doc_status != "CANCELLED_BY_CN",
    )
    return db.execute(stmt).scalar_one_or_none()


def list_invoices(
    db: Session,
    *,
    doc_status: str | None = None,
    dispatch_status: str | None = None,
    customer_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    limit: int = 200,
) -> list[Invoice]:
    stmt = select(Invoice).options(
        selectinload(Invoice.items),
        selectinload(Invoice.dispatches).selectinload(Dispatch.items),
    )
    if doc_status:
        stmt = stmt.where(Invoice.doc_status == doc_status)
    if dispatch_status:
        stmt = stmt.where(Invoice.dispatch_status == dispatch_status)
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if date_from:
        stmt = stmt.where(Invoice.invoice_date >= date_from)
    if date_to:
        stmt = stmt.where(Invoice.invoice_date <= date_to)
    if search and search.strip():
        pat = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Invoice.invoice_number.ilike(pat),
                Invoice.draft_ref.ilike(pat),
                Invoice.customer_name.ilike(pat),
            )
        )
    stmt = stmt.order_by(Invoice.invoice_date.desc(), Invoice.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def list_ready_for_billing_orders(db: Session) -> list[SalesOrder]:
    sub = select(Invoice.sales_order_id).where(Invoice.doc_status != "CANCELLED_BY_CN")
    stmt = (
        select(SalesOrder)
        .options(selectinload(SalesOrder.items))
        .where(SalesOrder.status == "APPROVED", ~SalesOrder.id.in_(sub))
        .order_by(SalesOrder.approved_at.asc(), SalesOrder.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def get_credit_note(db: Session, cn_id: int, *, for_update: bool = False) -> CreditNote | None:
    stmt = (
        select(CreditNote)
        .options(selectinload(CreditNote.items))
        .execution_options(populate_existing=True)
        .where(CreditNote.id == cn_id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def list_credit_notes(
    db: Session,
    *,
    original_invoice_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 200,
) -> list[CreditNote]:
    stmt = select(CreditNote).options(selectinload(CreditNote.items))
    if original_invoice_id is not None:
        stmt = stmt.where(CreditNote.original_invoice_id == original_invoice_id)
    if date_from is not None:
        stmt = stmt.where(CreditNote.issue_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(CreditNote.issue_date <= date_to)
    stmt = stmt.order_by(CreditNote.issue_date.desc(), CreditNote.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def get_dispatch(db: Session, dispatch_id: int, *, for_update: bool = False) -> Dispatch | None:
    stmt = (
        select(Dispatch)
        .options(selectinload(Dispatch.items), selectinload(Dispatch.status_history))
        .execution_options(populate_existing=True)
        .where(Dispatch.id == dispatch_id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def list_dispatches(
    db: Session,
    *,
    invoice_id: int | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 200,
) -> list[Dispatch]:
    stmt = select(Dispatch).options(
        selectinload(Dispatch.items),
        selectinload(Dispatch.status_history),
    )
    if invoice_id is not None:
        stmt = stmt.where(Dispatch.invoice_id == invoice_id)
    if status:
        stmt = stmt.where(Dispatch.status == status)
    if date_from:
        stmt = stmt.where(Dispatch.dispatch_date >= date_from)
    if date_to:
        stmt = stmt.where(Dispatch.dispatch_date <= date_to)
    stmt = stmt.order_by(Dispatch.dispatch_date.desc(), Dispatch.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def sum_dispatched_qty_by_invoice_item_ids(
    db: Session, invoice_item_ids: list[int], *, exclude_dispatch_id: int | None = None
) -> dict[int, int]:
    """Return all committed dispatch quantities across CREATED..DELIVERED dispatches."""
    if not invoice_item_ids:
        return {}
    stmt = select(
        DispatchItem.invoice_item_id,
        func.coalesce(func.sum(DispatchItem.dispatched_qty_pkts), 0),
    ).where(DispatchItem.invoice_item_id.in_(invoice_item_ids))
    if exclude_dispatch_id is not None:
        stmt = stmt.where(DispatchItem.dispatch_id != exclude_dispatch_id)
    stmt = stmt.group_by(DispatchItem.invoice_item_id)
    return {row[0]: int(row[1]) for row in db.execute(stmt).all()}


def list_ready_for_dispatch_invoices(db: Session) -> list[Invoice]:
    stmt = (
        select(Invoice)
        .options(
            selectinload(Invoice.items),
            selectinload(Invoice.dispatches).selectinload(Dispatch.items),
        )
        .where(
            Invoice.doc_status == "ISSUED",
            Invoice.dispatch_status.in_(["PENDING", "PARTIAL"]),
        )
        .order_by(Invoice.invoice_date.asc(), Invoice.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def list_open_fg_lots_fefo_for_update(db: Session, *, pack_size_id: int) -> list[CostLot]:
    """Lock open Finished Goods CostLot layers ordered by FEFO (earliest expiry, then FIFO)."""
    stmt = (
        select(CostLot)
        .where(CostLot.pack_size_id == pack_size_id, CostLot.remaining_qty_base > 0)
        .order_by(CostLot.expiry_date.asc().nullslast(), CostLot.received_at.asc(), CostLot.id.asc())
        .with_for_update()
    )
    return list(db.execute(stmt).scalars().all())


def list_invoice_audit_logs(db: Session, invoice_id: int) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(
            or_(
                and_(AuditLog.entity_table == "invoices", AuditLog.entity_id == invoice_id),
                and_(
                    AuditLog.entity_table.in_(["credit_notes", "dispatches"]),
                    AuditLog.after_state["invoice_id"].astext == str(invoice_id),
                ),
            )
        )
        .order_by(AuditLog.occurred_at.asc(), AuditLog.id.asc())
    )
    return list(db.execute(stmt).scalars().all())
