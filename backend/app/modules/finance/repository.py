"""Finance repository — locked reads for Payments, Allocations, Refunds & CustomerReceivables."""

from datetime import date
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.modules.billing.models import Invoice
from app.modules.finance.models import (
    CustomerReceivable,
    Payment,
    PaymentAllocation,
    PaymentRefund,
)
from app.modules.sales.models import Customer


def get_payment(db: Session, payment_id: int, *, for_update: bool = False) -> Payment | None:
    stmt = (
        select(Payment)
        .options(selectinload(Payment.allocations), selectinload(Payment.refunds))
        .execution_options(populate_existing=True)
        .where(Payment.id == payment_id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def get_payment_by_idempotency(db: Session, key: UUID) -> Payment | None:
    stmt = (
        select(Payment)
        .options(selectinload(Payment.allocations), selectinload(Payment.refunds))
        .where(Payment.idempotency_key == key)
    )
    return db.execute(stmt).scalar_one_or_none()


def find_duplicate_payment_ref(
    db: Session,
    *,
    customer_id: int,
    payment_date: date,
    amount_paisa: int,
    reference_no: str,
) -> Payment | None:
    stmt = select(Payment).where(
        Payment.customer_id == customer_id,
        Payment.payment_date == payment_date,
        Payment.amount_paisa == amount_paisa,
        Payment.reference_no == reference_no,
        Payment.status != "REVERSED",
    )
    return db.execute(stmt).scalar_one_or_none()


def list_payments(
    db: Session,
    *,
    customer_id: int | None = None,
    status: str | None = None,
    payment_mode: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Payment], int]:
    base = select(Payment).join(Customer, Customer.id == Payment.customer_id)
    if customer_id is not None:
        base = base.where(Payment.customer_id == customer_id)
    if status:
        base = base.where(Payment.status == status)
    if payment_mode:
        base = base.where(Payment.payment_mode == payment_mode)
    if date_from is not None:
        base = base.where(Payment.payment_date >= date_from)
    if date_to is not None:
        base = base.where(Payment.payment_date <= date_to)
    if search and search.strip():
        pat = f"%{search.strip()}%"
        base = base.where(
            or_(
                Payment.payment_number.ilike(pat),
                Payment.reference_no.ilike(pat),
                Customer.name.ilike(pat),
            )
        )

    total = int(db.execute(select(func.count()).select_from(base.subquery())).scalar_one())
    stmt = (
        base.options(selectinload(Payment.allocations), selectinload(Payment.refunds))
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all()), total


def get_allocation(
    db: Session, allocation_id: int, *, for_update: bool = False
) -> PaymentAllocation | None:
    stmt = (
        select(PaymentAllocation)
        .execution_options(populate_existing=True)
        .where(PaymentAllocation.id == allocation_id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def lock_invoices_for_settlement(
    db: Session, invoice_ids: list[int]
) -> tuple[dict[int, Invoice], dict[int, CustomerReceivable]]:
    """Lock target invoices and CustomerReceivables in deterministic ascending ID order."""
    unique_ids = sorted(set(invoice_ids))
    if not unique_ids:
        return {}, {}

    inv_rows = (
        db.execute(
            select(Invoice)
            .where(Invoice.id.in_(unique_ids))
            .order_by(Invoice.id.asc())
            .with_for_update()
        )
        .scalars()
        .all()
    )
    inv_map = {inv.id: inv for inv in inv_rows}

    ar_rows = (
        db.execute(
            select(CustomerReceivable)
            .where(CustomerReceivable.invoice_id.in_(unique_ids))
            .order_by(CustomerReceivable.invoice_id.asc())
            .with_for_update()
        )
        .scalars()
        .all()
    )
    ar_map = {ar.invoice_id: ar for ar in ar_rows}

    # Self-heal AR anchor for any ISSUED/CANCELLED invoice created before trigger hook
    for inv_id in unique_ids:
        inv = inv_map.get(inv_id)
        if inv is not None and inv.doc_status != "DRAFT" and inv_id not in ar_map:
            ar = CustomerReceivable(
                customer_id=inv.customer_id,
                invoice_id=inv.id,
                invoice_date=inv.invoice_date,
                due_date=inv.due_date,
                original_paisa=int(inv.grand_total_paisa),
                credited_paisa=int(inv.credited_paisa),
                paid_paisa=int(inv.paid_paisa),
            )
            db.add(ar)
            db.flush()
            ar_map[inv_id] = ar

    return inv_map, ar_map


def sum_active_allocations_for_invoice(db: Session, invoice_id: int) -> int:
    val = db.execute(
        select(func.coalesce(func.sum(PaymentAllocation.allocated_paisa), 0)).where(
            PaymentAllocation.invoice_id == invoice_id,
            PaymentAllocation.status == "ACTIVE",
        )
    ).scalar_one()
    return int(val or 0)


def sum_active_allocations_for_payment(db: Session, payment_id: int) -> int:
    val = db.execute(
        select(func.coalesce(func.sum(PaymentAllocation.allocated_paisa), 0)).where(
            PaymentAllocation.payment_id == payment_id,
            PaymentAllocation.status == "ACTIVE",
        )
    ).scalar_one()
    return int(val or 0)


def list_active_allocations_for_invoice_for_update(
    db: Session, invoice_id: int
) -> list[PaymentAllocation]:
    stmt = (
        select(PaymentAllocation)
        .where(
            PaymentAllocation.invoice_id == invoice_id,
            PaymentAllocation.status == "ACTIVE",
        )
        .order_by(PaymentAllocation.id.desc())
        .with_for_update()
    )
    return list(db.execute(stmt).scalars().all())


def list_all_refunds_for_payment(db: Session, payment_id: int) -> list[PaymentRefund]:
    stmt = (
        select(PaymentRefund)
        .where(PaymentRefund.payment_id == payment_id)
        .order_by(PaymentRefund.id.asc())
    )
    return list(db.execute(stmt).scalars().all())
