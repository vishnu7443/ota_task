from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OpeningBalance(Base):
    """Phase 4 source document anchoring seeded initial finished-goods stock."""

    __tablename__ = "opening_balances"
    __table_args__ = (
        CheckConstraint(
            "item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL', 'FINISHED_GOOD')",
            name="ob_item_category_enum",
        ),
        CheckConstraint("opening_qty_base > 0", name="ob_qty_positive"),
        CheckConstraint("unit_cost_paisa_per_base >= 0", name="ob_cost_non_negative"),
        Index(
            "uq_ob_batch_pack_size",
            "batch_ref",
            "pack_size_id",
            unique=True,
            postgresql_where=text("pack_size_id IS NOT NULL"),
        ),
        {"schema": "inventory"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_ref: Mapped[str] = mapped_column(String(40), nullable=False)
    item_category: Mapped[str] = mapped_column(String(20), nullable=False)
    pack_size_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"), nullable=True
    )
    opening_qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_cost_paisa_per_base: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InventoryBalance(Base):
    """Concurrency lock target & ledger-reconciled projection per SKU."""

    __tablename__ = "inventory_balances"
    __table_args__ = (
        CheckConstraint(
            "item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL', 'FINISHED_GOOD')",
            name="bal_item_category_enum",
        ),
        CheckConstraint("on_hand_qty_base >= 0", name="bal_on_hand_non_negative"),
        CheckConstraint("reserved_qty_base >= 0", name="bal_reserved_non_negative"),
        CheckConstraint("reserved_qty_base <= on_hand_qty_base", name="bal_reserved_cap"),
        Index(
            "uq_bal_pack_size",
            "pack_size_id",
            unique=True,
            postgresql_where=text("pack_size_id IS NOT NULL"),
        ),
        {"schema": "inventory"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_category: Mapped[str] = mapped_column(String(20), nullable=False)
    pack_size_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"), nullable=True
    )
    on_hand_qty_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0"
    )
    reserved_qty_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0"
    )
    available_qty_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), Computed("on_hand_qty_base - reserved_qty_base", persisted=True)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class InventoryMovement(Base):
    """Immutable append-only stock ledger linking every physical delta to a source document."""

    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint(
            "item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL', 'FINISHED_GOOD')",
            name="mov_item_category_enum",
        ),
        CheckConstraint(
            "movement_type IN ('OPENING','PURCHASE_IN','PROD_ISSUE_OUT','PACKAGING_DAMAGE_OUT',"
            "'PROD_OUTPUT_IN','PROD_RETURN_IN','DISPATCH_OUT','CREDIT_RETURN_IN','ADJUSTMENT')",
            name="mov_type_enum",
        ),
        CheckConstraint("signed_qty_base <> 0", name="mov_qty_nonzero"),
        CheckConstraint("unit_cost_paisa_per_base >= 0", name="mov_unit_cost_non_negative"),
        CheckConstraint("total_cost_paisa >= 0", name="mov_total_cost_non_negative"),
        CheckConstraint(
            "source_doc_type IN ('OPENING_BALANCE','PURCHASE_RECEIPT','PRODUCTION_RUN','DISPATCH','CREDIT_NOTE','STOCK_ADJUSTMENT')",
            name="mov_source_doc_type_enum",
        ),
        CheckConstraint(
            "(source_doc_type = 'OPENING_BALANCE' AND opening_balance_id IS NOT NULL) OR (source_doc_type <> 'OPENING_BALANCE')",
            name="mov_opening_source_required",
        ),
        Index(
            "idx_mov_pack_time",
            "pack_size_id",
            text("occurred_at ASC"),
            text("id ASC"),
            postgresql_where=text("pack_size_id IS NOT NULL"),
        ),
        {"schema": "inventory"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_category: Mapped[str] = mapped_column(String(20), nullable=False)
    pack_size_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"), nullable=True
    )
    movement_type: Mapped[str] = mapped_column(String(28), nullable=False)
    signed_qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_cost_paisa_per_base: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    total_cost_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_doc_type: Mapped[str] = mapped_column(String(24), nullable=False)
    opening_balance_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("inventory.opening_balances.id", ondelete="RESTRICT"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )


class StockReservation(Base):
    """Per-order-item stock reservation record supporting concurrent approvals and release auditability."""

    __tablename__ = "stock_reservations"
    __table_args__ = (
        CheckConstraint("reserved_qty_pkts > 0", name="qty_positive"),
        CheckConstraint("status IN ('ACTIVE', 'RELEASED', 'FULFILLED')", name="status_enum"),
        Index(
            "uq_stock_res_active_item",
            "sales_order_item_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "idx_stock_res_pack_active",
            "pack_size_id",
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("idx_stock_res_order_status", "sales_order_id", "status"),
        {"schema": "inventory"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sales_order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.sales_orders.id", ondelete="RESTRICT"), nullable=False
    )
    sales_order_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.sales_order_items.id", ondelete="RESTRICT"), nullable=False
    )
    pack_size_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"), nullable=False
    )
    reserved_qty_pkts: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reserved_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    released_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
