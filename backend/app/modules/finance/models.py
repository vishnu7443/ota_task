"""SQLAlchemy 2.0 models for finance schema: Payments, PaymentAllocations, PaymentRefunds, CustomerReceivables."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Payment(Base):
    """Recorded customer payment header supporting partial/multi-invoice allocations, advances, refunds & reversals."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("financial_year ~ '^[0-9]{4}-[0-9]{2}$'", name="pmt_fy_format"),
        CheckConstraint("amount_paisa > 0", name="pmt_amount_pos"),
        CheckConstraint("allocated_paisa >= 0", name="pmt_allocated_non_neg"),
        CheckConstraint("refunded_paisa >= 0", name="pmt_refunded_non_neg"),
        CheckConstraint(
            "allocated_paisa + refunded_paisa <= amount_paisa", name="pmt_cap_bounds"
        ),
        CheckConstraint(
            "payment_mode IN ('CASH','UPI','BANK_TRANSFER','NEFT','RTGS','IMPS','CHEQUE','CARD','OTHER')",
            name="pmt_mode_enum",
        ),
        CheckConstraint(
            "status IN ('RECORDED','PARTIALLY_ALLOCATED','ALLOCATED','PARTIALLY_REFUNDED','REFUNDED','REVERSED')",
            name="pmt_status_enum",
        ),
        CheckConstraint("version >= 1", name="pmt_version_pos"),
        Index(
            "uq_payments_customer_dup_ref",
            "customer_id",
            "payment_date",
            "amount_paisa",
            "reference_no",
            unique=True,
            postgresql_where=text("status <> 'REVERSED' AND reference_no IS NOT NULL"),
        ),
        Index("idx_payments_customer_date", "customer_id", text("payment_date DESC"), text("id DESC")),
        Index("idx_payments_status_date", "status", text("payment_date DESC")),
        {"schema": "finance"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    payment_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    financial_year: Mapped[str] = mapped_column(String(7), nullable=False)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.customers.id", ondelete="RESTRICT"), nullable=False
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allocated_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    refunded_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    unallocated_paisa: Mapped[int] = mapped_column(
        BigInteger,
        Computed(
            "CASE WHEN status IN ('REVERSED','REFUNDED') THEN 0::bigint "
            "ELSE GREATEST(0::bigint, amount_paisa - allocated_paisa - refunded_paisa) END",
            persisted=True,
        ),
        nullable=False,
    )
    payment_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    reference_no: Mapped[str | None] = mapped_column(String(80), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_advance: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    idempotency_key: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="'RECORDED'")
    reversal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reversed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        back_populates="payment", order_by="PaymentAllocation.id.asc()"
    )
    refunds: Mapped[list["PaymentRefund"]] = relationship(
        back_populates="payment", order_by="PaymentRefund.id.asc()"
    )


class PaymentAllocation(Base):
    """Auditable event-level mapping between a customer Payment and an issued GST Invoice."""

    __tablename__ = "payment_allocations"
    __table_args__ = (
        CheckConstraint("allocated_paisa > 0", name="pa_amount_pos"),
        CheckConstraint("status IN ('ACTIVE', 'REVERSED')", name="pa_status_enum"),
        Index("idx_pa_payment_status", "payment_id", "status"),
        Index("idx_pa_invoice_status", "invoice_id", "status"),
        {"schema": "finance"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("finance.payments.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.invoices.id", ondelete="RESTRICT"), nullable=False
    )
    allocated_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="'ACTIVE'")
    allocated_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    allocated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reversed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    payment: Mapped[Payment] = relationship(back_populates="allocations")


class PaymentRefund(Base):
    """Immutable refund voucher returning unallocated customer advance/overpayment funds."""

    __tablename__ = "payment_refunds"
    __table_args__ = (
        CheckConstraint("financial_year ~ '^[0-9]{4}-[0-9]{2}$'", name="rfd_fy_format"),
        CheckConstraint("amount_paisa > 0", name="rfd_amount_pos"),
        CheckConstraint(
            "refund_mode IN ('CASH','UPI','BANK_TRANSFER','NEFT','RTGS','IMPS','CHEQUE','CARD','OTHER')",
            name="rfd_mode_enum",
        ),
        CheckConstraint("length(trim(reason)) >= 5", name="rfd_reason_len"),
        CheckConstraint("status IN ('POSTED')", name="rfd_status_enum"),
        Index("idx_refunds_payment", "payment_id"),
        Index("idx_refunds_customer_date", "customer_id", text("refund_date DESC")),
        {"schema": "finance"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    refund_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    financial_year: Mapped[str] = mapped_column(String(7), nullable=False)
    payment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("finance.payments.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.customers.id", ondelete="RESTRICT"), nullable=False
    )
    refund_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    refund_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    reference_no: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="'POSTED'")
    refunded_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    refunded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    payment: Mapped[Payment] = relationship(back_populates="refunds")


class CustomerReceivable(Base):
    """1:1 Receivable balance anchor per issued invoice enforcing non-negative AR math in DB."""

    __tablename__ = "customer_receivables"
    __table_args__ = (
        CheckConstraint("original_paisa >= 0", name="ar_orig_non_neg"),
        CheckConstraint("credited_paisa >= 0", name="ar_cred_non_neg"),
        CheckConstraint("paid_paisa >= 0", name="ar_paid_non_neg"),
        CheckConstraint("credited_paisa + paid_paisa <= original_paisa", name="ar_non_negative"),
        Index("idx_ar_customer_due", "customer_id", "due_date"),
        {"schema": "finance"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.customers.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("billing.invoices.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    original_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    credited_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    paid_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    outstanding_paisa: Mapped[int] = mapped_column(
        BigInteger,
        Computed("original_paisa - credited_paisa - paid_paisa", persisted=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
