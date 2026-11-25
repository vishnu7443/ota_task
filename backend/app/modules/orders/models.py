from datetime import date, datetime
from typing import Any
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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SalesOrder(Base):
    __tablename__ = "sales_orders"
    __table_args__ = (
        CheckConstraint("place_of_supply_state_code ~ '^[0-9]{2}$'", name="pos_state_format"),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','UNDER_REVIEW','CORRECTION_REQUESTED',"
            "'APPROVED','REJECTED','INVOICED','PARTIALLY_DISPATCHED','DISPATCHED','CANCELLED')",
            name="order_status_enum",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        UniqueConstraint("salesman_id", "client_order_id", name="uq_sales_orders_idempotency"),
        Index("idx_orders_salesman_date", "salesman_id", text("order_date DESC"), text("id DESC")),
        Index("idx_orders_admin_date", text("order_date DESC"), text("id DESC")),
        Index("idx_orders_customer_date", "customer_id", text("order_date DESC"), text("id DESC")),
        Index(
            "idx_orders_pending_queue",
            "status",
            text("created_at ASC"),
            postgresql_where=text(
                "status IN ('SUBMITTED','UNDER_REVIEW','CORRECTION_REQUESTED','APPROVED','INVOICED')"
            ),
        ),
        {"schema": "sales"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    client_order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    salesman_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.customers.id", ondelete="RESTRICT"), nullable=False
    )
    shipping_address_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sales.customer_addresses.id", ondelete="RESTRICT"), nullable=True
    )
    place_of_supply_state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(28), nullable=False)
    has_shortage: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["SalesOrderItem"]] = relationship(
        back_populates="order", order_by="SalesOrderItem.id"
    )
    status_history: Mapped[list["SalesOrderStatusHistory"]] = relationship(
        back_populates="order", order_by="SalesOrderStatusHistory.changed_at"
    )
    approvals: Mapped[list["SalesOrderApproval"]] = relationship(
        back_populates="order", order_by="SalesOrderApproval.decided_at"
    )


class SalesOrderItem(Base):
    __tablename__ = "sales_order_items"
    __table_args__ = (
        CheckConstraint("ordered_qty_pkts > 0", name="ordered_qty_positive"),
        CheckConstraint(
            "approved_qty_pkts IS NULL OR approved_qty_pkts >= 0",
            name="approved_qty_non_negative",
        ),
        CheckConstraint("unit_price_paisa >= 0", name="unit_price_non_negative"),
        CheckConstraint("original_unit_price_paisa >= 0", name="orig_price_non_negative"),
        UniqueConstraint("sales_order_id", "pack_size_id", name="uq_soi_order_sku"),
        {"schema": "sales"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sales_order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.sales_orders.id", ondelete="RESTRICT"), nullable=False
    )
    pack_size_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"), nullable=False
    )
    ordered_qty_pkts: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_qty_pkts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_unit_price_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unit_price_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_taxable_paisa: Mapped[int] = mapped_column(
        BigInteger,
        Computed("COALESCE(approved_qty_pkts, ordered_qty_pkts)::bigint * unit_price_paisa", persisted=True),
        nullable=False,
    )

    order: Mapped[SalesOrder] = relationship(back_populates="items")


class SalesOrderStatusHistory(Base):
    __tablename__ = "sales_order_status_history"
    __table_args__ = (
        CheckConstraint("from_status IS DISTINCT FROM to_status", name="no_noop_transition"),
        Index("idx_osh_order_time", "sales_order_id", "changed_at"),
        {"schema": "sales"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sales_order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.sales_orders.id", ondelete="RESTRICT"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(28), nullable=True)
    to_status: Mapped[str] = mapped_column(String(28), nullable=False)
    changed_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    order: Mapped[SalesOrder] = relationship(back_populates="status_history")


class SalesOrderApproval(Base):
    __tablename__ = "sales_order_approvals"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('APPROVED', 'REJECTED', 'CORRECTION_REQUESTED', 'HELD_SHORTAGE', 'PENDING_REVIEW', 'CANCELLED')",
            name="approval_decision_enum",
        ),
        CheckConstraint("ordered_total_pkts > 0", name="ordered_total_positive"),
        CheckConstraint("available_total_pkts >= 0", name="available_total_non_negative"),
        CheckConstraint("shortage_pkts >= 0", name="shortage_non_negative"),
        CheckConstraint(
            "NOT (decision = 'APPROVED' AND shortage_pkts > 0)",
            name="no_approve_with_shortage",
        ),
        {"schema": "sales"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sales_order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.sales_orders.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(28), nullable=False)
    ordered_total_pkts: Mapped[int] = mapped_column(Integer, nullable=False)
    available_total_pkts: Mapped[int] = mapped_column(Integer, nullable=False)
    shortage_pkts: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    order: Mapped[SalesOrder] = relationship(back_populates="approvals")
