from datetime import date, datetime
from decimal import Decimal

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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Material(Base):
    """Unified Raw Materials & Packaging Materials master (production.materials)."""

    __tablename__ = "materials"
    __table_args__ = (
        CheckConstraint(
            "material_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL')",
            name="mat_category_enum",
        ),
        CheckConstraint("unit_dimension IN ('MASS', 'VOLUME', 'COUNT')", name="mat_dim_enum"),
        CheckConstraint(
            "(unit_dimension = 'MASS' AND base_uom = 'g') OR "
            "(unit_dimension = 'VOLUME' AND base_uom = 'ml') OR "
            "(unit_dimension = 'COUNT' AND base_uom = 'piece')",
            name="mat_dim_base_match",
        ),
        CheckConstraint("reorder_level_base >= 0", name="mat_reorder_non_neg"),
        {"schema": "production"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    material_category: Mapped[str] = mapped_column(String(24), nullable=False)
    unit_dimension: Mapped[str] = mapped_column(String(16), nullable=False)
    base_uom: Mapped[str] = mapped_column(String(16), nullable=False)
    display_uom: Mapped[str] = mapped_column(String(16), nullable=False)
    reorder_level_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class UnitConversion(Base):
    """Exact metric/count conversion factors within a single unit dimension."""

    __tablename__ = "unit_conversions"
    __table_args__ = (
        CheckConstraint("unit_dimension IN ('MASS', 'VOLUME', 'COUNT')", name="uom_dim_enum"),
        CheckConstraint("multiplier > 0", name="uom_multiplier_pos"),
        UniqueConstraint("from_uom", "to_base_uom", name="uq_uom_pair"),
        {"schema": "production"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    from_uom: Mapped[str] = mapped_column(String(16), nullable=False)
    to_base_uom: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_dimension: Mapped[str] = mapped_column(String(16), nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)


class OpeningBalance(Base):
    """Source document anchoring seeded/opening inventory for RM, Packaging, and FG."""

    __tablename__ = "opening_balances"
    __table_args__ = (
        CheckConstraint(
            "item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL', 'FINISHED_GOOD')",
            name="ob_item_category_enum",
        ),
        CheckConstraint(
            "(item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL') AND material_id IS NOT NULL AND pack_size_id IS NULL) OR "
            "(item_category = 'FINISHED_GOOD' AND pack_size_id IS NOT NULL AND material_id IS NULL)",
            name="ob_one_item",
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
        Index(
            "uq_ob_batch_material",
            "batch_ref",
            "material_id",
            unique=True,
            postgresql_where=text("material_id IS NOT NULL"),
        ),
        {"schema": "inventory"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_ref: Mapped[str] = mapped_column(String(40), nullable=False)
    item_category: Mapped[str] = mapped_column(String(20), nullable=False)
    material_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("production.materials.id", ondelete="RESTRICT"), nullable=True
    )
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
    """Concurrency lock target & ledger-reconciled projection per Material or Finished Good SKU."""

    __tablename__ = "inventory_balances"
    __table_args__ = (
        CheckConstraint(
            "item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL', 'FINISHED_GOOD')",
            name="bal_item_category_enum",
        ),
        CheckConstraint(
            "(item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL') AND material_id IS NOT NULL AND pack_size_id IS NULL) OR "
            "(item_category = 'FINISHED_GOOD' AND pack_size_id IS NOT NULL AND material_id IS NULL)",
            name="bal_one_item",
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
        Index(
            "uq_bal_material",
            "material_id",
            unique=True,
            postgresql_where=text("material_id IS NOT NULL"),
        ),
        {"schema": "inventory"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_category: Mapped[str] = mapped_column(String(20), nullable=False)
    material_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("production.materials.id", ondelete="RESTRICT"), nullable=True
    )
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


class CostLot(Base):
    """Immutable FIFO cost layer created by Opening, Purchase Receipt, Production Output, or Returns."""

    __tablename__ = "cost_lots"
    __table_args__ = (
        CheckConstraint(
            "item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL', 'FINISHED_GOOD')",
            name="lot_item_category_enum",
        ),
        CheckConstraint(
            "(material_id IS NOT NULL AND pack_size_id IS NULL) OR (pack_size_id IS NOT NULL AND material_id IS NULL)",
            name="lot_one_item",
        ),
        CheckConstraint(
            "source_doc_type IN ('OPENING_BALANCE','PURCHASE_RECEIPT','PRODUCTION_RUN','CREDIT_NOTE','STOCK_ADJUSTMENT')",
            name="lot_source_doc_enum",
        ),
        CheckConstraint("original_qty_base > 0", name="lot_orig_qty_pos"),
        CheckConstraint(
            "remaining_qty_base >= 0 AND remaining_qty_base <= original_qty_base",
            name="lot_rem_qty_bounds",
        ),
        CheckConstraint("unit_cost_paisa_per_base >= 0", name="lot_unit_cost_non_neg"),
        Index(
            "idx_lots_fifo_open",
            "material_id",
            "received_at",
            "id",
            postgresql_where=text("remaining_qty_base > 0 AND material_id IS NOT NULL"),
        ),
        Index(
            "idx_lots_fg_fefo",
            "pack_size_id",
            text("expiry_date ASC NULLS LAST"),
            "received_at",
            "id",
            postgresql_where=text("remaining_qty_base > 0 AND pack_size_id IS NOT NULL"),
        ),
        {"schema": "inventory"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_category: Mapped[str] = mapped_column(String(20), nullable=False)
    material_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("production.materials.id", ondelete="RESTRICT"), nullable=True
    )
    pack_size_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"), nullable=True
    )
    source_doc_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_doc_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    batch_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    original_qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    remaining_qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_cost_paisa_per_base: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StockAdjustment(Base):
    """Reason-logged controlled stock adjustment voucher (DAMAGED, EXPIRED, MISSING, COUNT, SUPPLIER_RETURN)."""

    __tablename__ = "stock_adjustments"
    __table_args__ = (
        CheckConstraint(
            "item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL', 'FINISHED_GOOD')",
            name="adj_item_category_enum",
        ),
        CheckConstraint(
            "(item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL') AND material_id IS NOT NULL AND pack_size_id IS NULL) OR "
            "(item_category = 'FINISHED_GOOD' AND pack_size_id IS NOT NULL AND material_id IS NULL)",
            name="adj_one_item",
        ),
        CheckConstraint(
            "adjustment_type IN ('DAMAGED','EXPIRED','MISSING','COUNT_CORRECTION','SUPPLIER_RETURN','OTHER')",
            name="adj_type_enum",
        ),
        CheckConstraint("delta_qty_base <> 0", name="adj_delta_nonzero"),
        CheckConstraint("entered_qty <> 0", name="adj_entered_nonzero"),
        CheckConstraint("unit_cost_paisa_per_base >= 0", name="adj_unit_cost_non_neg"),
        CheckConstraint("length(trim(reason)) >= 5", name="adj_reason_min_len"),
        CheckConstraint(
            "status IN ('DRAFT','PENDING_APPROVAL','POSTED','REJECTED')",
            name="adj_status_enum",
        ),
        {"schema": "inventory"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    adjustment_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    item_category: Mapped[str] = mapped_column(String(20), nullable=False)
    material_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("production.materials.id", ondelete="RESTRICT"), nullable=True
    )
    pack_size_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"), nullable=True
    )
    adjustment_type: Mapped[str] = mapped_column(String(24), nullable=False)
    entered_qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    entered_uom: Mapped[str] = mapped_column(String(16), nullable=False)
    delta_qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_cost_paisa_per_base: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    requested_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InventoryMovement(Base):
    """Immutable append-only stock ledger linking every physical delta to a source document."""

    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint(
            "item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL', 'FINISHED_GOOD')",
            name="mov_item_category_enum",
        ),
        CheckConstraint(
            "(item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL') AND material_id IS NOT NULL AND pack_size_id IS NULL) OR "
            "(item_category = 'FINISHED_GOOD' AND pack_size_id IS NOT NULL AND material_id IS NULL)",
            name="mov_one_item",
        ),
        CheckConstraint(
            "movement_type IN ('OPENING','PURCHASE_IN','PROD_ISSUE_OUT','PACKAGING_DAMAGE_OUT',"
            "'PROD_OUTPUT_IN','PROD_RETURN_IN','DISPATCH_OUT','CREDIT_RETURN_IN',"
            "'SUPPLIER_RETURN','DAMAGE_WASTAGE','ADJUSTMENT')",
            name="mov_type_enum",
        ),
        CheckConstraint("signed_qty_base <> 0", name="mov_qty_nonzero"),
        CheckConstraint("unit_cost_paisa_per_base >= 0", name="mov_unit_cost_non_negative"),
        CheckConstraint("total_cost_paisa >= 0", name="mov_total_cost_non_negative"),
        CheckConstraint(
            "source_doc_type IN ('OPENING_BALANCE','PURCHASE_RECEIPT','PRODUCTION_RUN','DISPATCH','CREDIT_NOTE','STOCK_ADJUSTMENT','SUPPLIER_RETURN')",
            name="mov_source_doc_type_enum",
        ),
        CheckConstraint(
            "(source_doc_type = 'OPENING_BALANCE' AND opening_balance_id IS NOT NULL) OR "
            "(source_doc_type = 'PURCHASE_RECEIPT' AND purchase_receipt_item_id IS NOT NULL) OR "
            "(source_doc_type IN ('STOCK_ADJUSTMENT', 'SUPPLIER_RETURN') AND stock_adjustment_id IS NOT NULL) OR "
            "source_doc_type IN ('PRODUCTION_RUN', 'DISPATCH', 'CREDIT_NOTE')",
            name="mov_source_required",
        ),
        CheckConstraint(
            "(movement_type IN ('OPENING','PURCHASE_IN','PROD_OUTPUT_IN','PROD_RETURN_IN','CREDIT_RETURN_IN') AND signed_qty_base > 0) OR "
            "(movement_type IN ('PROD_ISSUE_OUT','PACKAGING_DAMAGE_OUT','DISPATCH_OUT','SUPPLIER_RETURN','DAMAGE_WASTAGE') AND signed_qty_base < 0) OR "
            "(movement_type = 'ADJUSTMENT' AND signed_qty_base <> 0)",
            name="mov_sign_direction",
        ),
        Index(
            "idx_mov_pack_time",
            "pack_size_id",
            text("occurred_at ASC"),
            text("id ASC"),
            postgresql_where=text("pack_size_id IS NOT NULL"),
        ),
        Index(
            "idx_mov_material_time",
            "material_id",
            text("occurred_at ASC"),
            text("id ASC"),
            postgresql_where=text("material_id IS NOT NULL"),
        ),
        {"schema": "inventory"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_category: Mapped[str] = mapped_column(String(20), nullable=False)
    material_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("production.materials.id", ondelete="RESTRICT"), nullable=True
    )
    pack_size_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"), nullable=True
    )
    movement_type: Mapped[str] = mapped_column(String(28), nullable=False)
    entered_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    entered_uom: Mapped[str | None] = mapped_column(String(16), nullable=True)
    signed_qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_cost_paisa_per_base: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    total_cost_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_doc_type: Mapped[str] = mapped_column(String(24), nullable=False)
    reference_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    opening_balance_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("inventory.opening_balances.id", ondelete="RESTRICT"), nullable=True
    )
    purchase_receipt_item_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("purchasing.purchase_receipt_items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    stock_adjustment_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("inventory.stock_adjustments.id", ondelete="RESTRICT"),
        nullable=True,
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
