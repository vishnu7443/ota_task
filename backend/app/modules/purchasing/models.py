from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
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
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint(
            "gstin IS NULL OR gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'",
            name="gstin_format",
        ),
        CheckConstraint("state_code ~ '^[0-9]{2}$'", name="state_code_format"),
        CheckConstraint(
            "gstin IS NULL OR SUBSTRING(gstin FROM 1 FOR 2) = state_code",
            name="gstin_matches_state",
        ),
        Index("idx_suppliers_active_name", "is_active", "name"),
        {"schema": "purchasing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    contact_person: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    state_name: Mapped[str] = mapped_column(String(80), nullable=False)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','APPROVED','REJECTED','PARTIALLY_RECEIVED','RECEIVED','CLOSED','CANCELLED')",
            name="po_status_enum",
        ),
        CheckConstraint("subtotal_paisa >= 0", name="po_subtotal_non_negative"),
        CheckConstraint("tax_paisa >= 0", name="po_tax_non_negative"),
        CheckConstraint("total_paisa >= 0", name="po_total_non_negative"),
        CheckConstraint("version >= 1", name="po_version_positive"),
        Index("idx_po_supplier_date", "supplier_id", text("order_date DESC"), text("id DESC")),
        {"schema": "purchasing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    po_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    supplier_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("purchasing.suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    subtotal_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    tax_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    submitted_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    supplier: Mapped[Supplier] = relationship()
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="purchase_order", order_by="PurchaseOrderItem.id"
    )


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        CheckConstraint("entered_qty > 0", name="poi_entered_qty_positive"),
        CheckConstraint("ordered_qty_base > 0", name="poi_ordered_base_positive"),
        CheckConstraint("received_qty_base >= 0", name="poi_received_base_non_negative"),
        CheckConstraint("rejected_qty_base >= 0", name="poi_rejected_base_non_negative"),
        CheckConstraint("unit_rate_paisa >= 0", name="poi_rate_non_negative"),
        CheckConstraint("gst_rate_bps >= 0 AND gst_rate_bps <= 2800", name="poi_gst_valid"),
        CheckConstraint("line_subtotal_paisa >= 0", name="poi_subtotal_non_negative"),
        CheckConstraint("line_tax_paisa >= 0", name="poi_tax_non_negative"),
        CheckConstraint("line_total_paisa >= 0", name="poi_total_non_negative"),
        UniqueConstraint("purchase_order_id", "material_id", name="uq_poi_po_material"),
        {"schema": "purchasing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    purchase_order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("purchasing.purchase_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    material_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("production.materials.id", ondelete="RESTRICT"), nullable=False
    )
    entered_qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    entered_uom: Mapped[str] = mapped_column(String(16), nullable=False)
    ordered_qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    received_qty_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0"
    )
    rejected_qty_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0"
    )
    unit_rate_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gst_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    line_subtotal_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_tax_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_total_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="items")


class PurchaseReceipt(Base):
    __tablename__ = "purchase_receipts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','VERIFIED','POSTED','RECEIVED','CLOSED','CANCELLED')",
            name="pr_status_enum",
        ),
        CheckConstraint("subtotal_paisa >= 0", name="pr_subtotal_non_negative"),
        CheckConstraint("input_gst_paisa >= 0", name="pr_gst_non_negative"),
        CheckConstraint("total_paisa >= 0", name="pr_total_non_negative"),
        CheckConstraint("version >= 1", name="pr_version_positive"),
        Index("idx_pr_supplier_date", "supplier_id", text("receipt_date DESC"), text("id DESC")),
        Index("idx_pr_po", "purchase_order_id"),
        {"schema": "purchasing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    receipt_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    client_receipt_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, unique=True)
    purchase_order_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("purchasing.purchase_orders.id", ondelete="RESTRICT"),
        nullable=True,
    )
    supplier_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("purchasing.suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    supplier_bill_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    subtotal_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    input_gst_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    discrepancy_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    submitted_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    supplier: Mapped[Supplier] = relationship()
    items: Mapped[list["PurchaseReceiptItem"]] = relationship(
        back_populates="purchase_receipt", order_by="PurchaseReceiptItem.id"
    )


class PurchaseReceiptItem(Base):
    __tablename__ = "purchase_receipt_items"
    __table_args__ = (
        CheckConstraint("received_qty_entered > 0", name="pri_rec_entered_pos"),
        CheckConstraint("rejected_qty_entered >= 0", name="pri_rej_entered_non_neg"),
        CheckConstraint("accepted_qty_entered >= 0", name="pri_acc_entered_non_neg"),
        CheckConstraint("received_qty_base > 0", name="pri_rec_base_pos"),
        CheckConstraint("rejected_qty_base >= 0", name="pri_rej_base_non_neg"),
        CheckConstraint("accepted_qty_base >= 0", name="pri_acc_base_non_neg"),
        CheckConstraint(
            "accepted_qty_entered + rejected_qty_entered = received_qty_entered",
            name="pri_entered_split_match",
        ),
        CheckConstraint(
            "accepted_qty_base + rejected_qty_base = received_qty_base",
            name="pri_base_split_match",
        ),
        CheckConstraint("entered_unit_rate_paisa >= 0", name="pri_rate_non_neg"),
        CheckConstraint("gst_rate_bps >= 0 AND gst_rate_bps <= 2800", name="pri_gst_valid"),
        CheckConstraint("unit_cost_paisa_per_base >= 0", name="pri_unit_cost_non_neg"),
        CheckConstraint("line_subtotal_paisa >= 0", name="pri_sub_non_neg"),
        CheckConstraint("line_tax_paisa >= 0", name="pri_tax_non_neg"),
        CheckConstraint("line_total_paisa >= 0", name="pri_tot_non_neg"),
        {"schema": "purchasing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    purchase_receipt_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("purchasing.purchase_receipts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    purchase_order_item_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("purchasing.purchase_order_items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    material_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("production.materials.id", ondelete="RESTRICT"), nullable=False
    )
    entered_uom: Mapped[str] = mapped_column(String(16), nullable=False)
    received_qty_entered: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    rejected_qty_entered: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0"
    )
    accepted_qty_entered: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    received_qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    rejected_qty_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0"
    )
    accepted_qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    entered_unit_rate_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gst_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unit_cost_paisa_per_base: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    line_subtotal_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_tax_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_total_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    batch_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    purchase_receipt: Mapped[PurchaseReceipt] = relationship(back_populates="items")
