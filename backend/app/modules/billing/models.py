"""Billing domain SQLAlchemy models — FiscalSequence, Invoice, CreditNote, Dispatch & Delivery."""

from datetime import date, datetime
from typing import Any

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FiscalSequence(Base):
    """Transaction-safe Indian Financial Year sequential counter locked with FOR UPDATE."""

    __tablename__ = "fiscal_sequences"
    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('INVOICE', 'CREDIT_NOTE', 'DISPATCH')",
            name="fs_doc_type_enum",
        ),
        CheckConstraint(
            "financial_year ~ '^[0-9]{4}-[0-9]{2}$'",
            name="fs_fy_format",
        ),
        CheckConstraint("last_seq_no >= 0", name="fs_seq_non_neg"),
        UniqueConstraint("doc_type", "financial_year", name="uq_fiscal_seq_type_fy"),
        {"schema": "billing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_type: Mapped[str] = mapped_column(String(16), nullable=False)
    financial_year: Mapped[str] = mapped_column(String(7), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    last_seq_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Invoice(Base):
    """Statutory GST Tax Invoice preserving tax snapshot, FY sequence, and lifecycle state."""

    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "financial_year ~ '^[0-9]{4}-[0-9]{2}$'",
            name="inv_fy_format",
        ),
        CheckConstraint("nature_of_supply IN ('B2B', 'B2C')", name="inv_nature_enum"),
        CheckConstraint("supply_type IN ('INTRA_STATE', 'INTER_STATE')", name="inv_supply_enum"),
        CheckConstraint(
            "doc_status IN ('DRAFT', 'ISSUED', 'CANCELLED_BY_CN')",
            name="inv_doc_status_enum",
        ),
        CheckConstraint(
            "payment_status IN ('UNPAID', 'PARTIALLY_PAID', 'PAID', 'CREDITED')",
            name="inv_payment_status_enum",
        ),
        CheckConstraint(
            "dispatch_status IN ('PENDING', 'PARTIAL', 'DISPATCHED')",
            name="inv_dispatch_status_enum",
        ),
        CheckConstraint("discount_total_paisa >= 0", name="inv_disc_non_neg"),
        CheckConstraint("taxable_total_paisa >= 0", name="inv_taxable_non_neg"),
        CheckConstraint("cgst_total_paisa >= 0", name="inv_cgst_non_neg"),
        CheckConstraint("sgst_total_paisa >= 0", name="inv_sgst_non_neg"),
        CheckConstraint("igst_total_paisa >= 0", name="inv_igst_non_neg"),
        CheckConstraint(
            "round_off_paisa >= -100 AND round_off_paisa <= 100", name="inv_round_off_bounds"
        ),
        CheckConstraint("paid_paisa >= 0", name="inv_paid_non_neg"),
        CheckConstraint("credited_paisa >= 0", name="inv_credited_non_neg"),
        CheckConstraint("version >= 1", name="inv_version_pos"),
        CheckConstraint(
            "(supply_type = 'INTRA_STATE' AND igst_total_paisa = 0 AND cgst_total_paisa = sgst_total_paisa) OR "
            "(supply_type = 'INTER_STATE' AND cgst_total_paisa = 0 AND sgst_total_paisa = 0)",
            name="inv_gst_split",
        ),
        CheckConstraint(
            "(doc_status = 'DRAFT' AND invoice_number IS NULL) OR "
            "(doc_status IN ('ISSUED', 'CANCELLED_BY_CN') AND invoice_number IS NOT NULL AND issued_by IS NOT NULL AND issued_at IS NOT NULL)",
            name="inv_issued_number_required",
        ),
        Index(
            "uq_invoices_active_order",
            "sales_order_id",
            unique=True,
            postgresql_where=text("doc_status <> 'CANCELLED_BY_CN'"),
        ),
        Index("idx_invoices_customer_date", "customer_id", text("invoice_date DESC"), text("id DESC")),
        Index("idx_invoices_fy_date_status", "financial_year", "invoice_date", "doc_status"),
        {"schema": "billing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    draft_ref: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    invoice_number: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    financial_year: Mapped[str] = mapped_column(String(7), nullable=False)
    sales_order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.sales_orders.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.customers.id", ondelete="RESTRICT"), nullable=False
    )
    customer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    customer_type: Mapped[str] = mapped_column(String(20), nullable=False)
    seller_legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    seller_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    seller_state_name: Mapped[str] = mapped_column(String(80), nullable=False)
    seller_state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    seller_address: Mapped[str] = mapped_column(Text, nullable=False)
    buyer_gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    place_of_supply_state_name: Mapped[str] = mapped_column(String(80), nullable=False)
    place_of_supply_state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    billing_address_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    shipping_address_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    nature_of_supply: Mapped[str] = mapped_column(String(16), nullable=False)
    supply_type: Mapped[str] = mapped_column(String(16), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_terms: Mapped[str] = mapped_column(String(80), nullable=False)
    doc_status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="'DRAFT'")
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="'UNPAID'")
    dispatch_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="'PENDING'"
    )
    discount_total_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    taxable_total_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cgst_total_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    sgst_total_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    igst_total_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    round_off_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    grand_total_paisa: Mapped[int] = mapped_column(
        BigInteger,
        Computed(
            "taxable_total_paisa + cgst_total_paisa + sgst_total_paisa + igst_total_paisa + round_off_paisa",
            persisted=True,
        ),
        nullable=False,
    )
    paid_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    credited_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    outstanding_paisa: Mapped[int] = mapped_column(
        BigInteger,
        Computed(
            "GREATEST(0::bigint, taxable_total_paisa + cgst_total_paisa + sgst_total_paisa + igst_total_paisa + round_off_paisa - credited_paisa - paid_paisa)",
            persisted=True,
        ),
        nullable=False,
    )
    amount_in_words: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_declaration: Mapped[str] = mapped_column(Text, nullable=False)
    tax_calculation_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    verified_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice", order_by="InvoiceItem.id.asc()"
    )
    tax_components: Mapped[list["InvoiceTaxComponent"]] = relationship(
        back_populates="invoice", order_by="InvoiceTaxComponent.id.asc()"
    )
    credit_notes: Mapped[list["CreditNote"]] = relationship(
        back_populates="original_invoice", order_by="CreditNote.id.asc()"
    )
    dispatches: Mapped[list["Dispatch"]] = relationship(
        back_populates="invoice", order_by="Dispatch.id.asc()"
    )


class InvoiceItem(Base):
    """Historical snapshot line item on a GST Invoice with HSN, discount, and tax split."""

    __tablename__ = "invoice_items"
    __table_args__ = (
        CheckConstraint("qty_pkts > 0", name="ii_qty_pos"),
        CheckConstraint("unit_price_paisa >= 0", name="ii_price_non_neg"),
        CheckConstraint("discount_paisa >= 0", name="ii_disc_non_neg"),
        CheckConstraint("taxable_paisa >= 0", name="ii_taxable_non_neg"),
        CheckConstraint("gst_rate_bps >= 0", name="ii_gst_bps_non_neg"),
        CheckConstraint("cgst_paisa >= 0", name="ii_cgst_non_neg"),
        CheckConstraint("sgst_paisa >= 0", name="ii_sgst_non_neg"),
        CheckConstraint("igst_paisa >= 0", name="ii_igst_non_neg"),
        UniqueConstraint("invoice_id", "sales_order_item_id", name="uq_ii_inv_order_item"),
        {"schema": "billing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.invoices.id", ondelete="RESTRICT"), nullable=False
    )
    sales_order_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.sales_order_items.id", ondelete="RESTRICT"), nullable=False
    )
    pack_size_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"), nullable=False
    )
    sku_code: Mapped[str] = mapped_column(String(40), nullable=False)
    product_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    hsn_code: Mapped[str] = mapped_column(String(12), nullable=False)
    qty_pkts: Mapped[int] = mapped_column(Integer, nullable=False)
    uom: Mapped[str] = mapped_column(String(16), nullable=False, server_default="'packet'")
    unit_price_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    taxable_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gst_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    cgst_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    sgst_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    igst_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cgst_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    sgst_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    igst_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    line_total_paisa: Mapped[int] = mapped_column(
        BigInteger,
        Computed("taxable_paisa + cgst_paisa + sgst_paisa + igst_paisa", persisted=True),
        nullable=False,
    )

    invoice: Mapped[Invoice] = relationship(back_populates="items")


class InvoiceTaxComponent(Base):
    """HSN & Tax-head summary rows supporting GSTR-1 / outward tax reports without drift."""

    __tablename__ = "invoice_tax_components"
    __table_args__ = (
        CheckConstraint("tax_type IN ('CGST', 'SGST', 'IGST')", name="itc_tax_type_enum"),
        CheckConstraint("rate_bps >= 0", name="itc_rate_non_neg"),
        CheckConstraint("taxable_base_paisa >= 0", name="itc_base_non_neg"),
        CheckConstraint("tax_amount_paisa >= 0", name="itc_amt_non_neg"),
        UniqueConstraint("invoice_id", "hsn_code", "tax_type", "rate_bps", name="uq_itc_bucket"),
        {"schema": "billing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.invoices.id", ondelete="RESTRICT"), nullable=False
    )
    hsn_code: Mapped[str] = mapped_column(String(12), nullable=False)
    tax_type: Mapped[str] = mapped_column(String(8), nullable=False)
    rate_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    taxable_base_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_amount_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="tax_components")


class CreditNote(Base):
    """Immutable statutory GST Credit Note for cancellations, returns, or tax adjustments."""

    __tablename__ = "credit_notes"
    __table_args__ = (
        CheckConstraint("financial_year ~ '^[0-9]{4}-[0-9]{2}$'", name="cn_fy_format"),
        CheckConstraint("supply_type IN ('INTRA_STATE', 'INTER_STATE')", name="cn_supply_enum"),
        CheckConstraint(
            "note_type IN ('INVOICE_CANCELLATION', 'SALES_RETURN', 'VALUE_ADJUSTMENT')",
            name="cn_type_enum",
        ),
        CheckConstraint("status IN ('DRAFT', 'ISSUED')", name="cn_status_enum"),
        CheckConstraint("length(trim(reason)) >= 5", name="cn_reason_len"),
        CheckConstraint("taxable_reversed_paisa >= 0", name="cn_taxable_non_neg"),
        CheckConstraint("cgst_reversed_paisa >= 0", name="cn_cgst_non_neg"),
        CheckConstraint("sgst_reversed_paisa >= 0", name="cn_sgst_non_neg"),
        CheckConstraint("igst_reversed_paisa >= 0", name="cn_igst_non_neg"),
        CheckConstraint(
            "(status = 'DRAFT' AND cn_number IS NULL) OR (status = 'ISSUED' AND cn_number IS NOT NULL AND issued_by IS NOT NULL AND issued_at IS NOT NULL)",
            name="cn_issued_number_required",
        ),
        {"schema": "billing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    draft_ref: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    cn_number: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    financial_year: Mapped[str] = mapped_column(String(7), nullable=False)
    original_invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.invoices.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.customers.id", ondelete="RESTRICT"), nullable=False
    )
    supply_type: Mapped[str] = mapped_column(String(16), nullable=False)
    note_type: Mapped[str] = mapped_column(String(24), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="'DRAFT'")
    cancel_original_invoice: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    taxable_reversed_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cgst_reversed_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    sgst_reversed_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    igst_reversed_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    round_off_reversed_paisa: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    total_reversed_paisa: Mapped[int] = mapped_column(
        BigInteger,
        Computed(
            "taxable_reversed_paisa + cgst_reversed_paisa + sgst_reversed_paisa + igst_reversed_paisa + round_off_reversed_paisa",
            persisted=True,
        ),
        nullable=False,
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    original_invoice: Mapped[Invoice] = relationship(back_populates="credit_notes")
    items: Mapped[list["CreditNoteItem"]] = relationship(
        back_populates="credit_note", order_by="CreditNoteItem.id.asc()"
    )


class CreditNoteItem(Base):
    """Itemized Credit Note line linking original InvoiceItem & optional return stock disposition."""

    __tablename__ = "credit_note_items"
    __table_args__ = (
        CheckConstraint("qty_pkts >= 0", name="cni_qty_non_neg"),
        CheckConstraint(
            "return_disposition IN ('NONE_NOT_DISPATCHED', 'RESTOCK_SELLABLE', 'SCRAP_DAMAGED')",
            name="cni_disp_enum",
        ),
        CheckConstraint("taxable_reversed_paisa >= 0", name="cni_taxable_non_neg"),
        CheckConstraint("cgst_reversed_paisa >= 0", name="cni_cgst_non_neg"),
        CheckConstraint("sgst_reversed_paisa >= 0", name="cni_sgst_non_neg"),
        CheckConstraint("igst_reversed_paisa >= 0", name="cni_igst_non_neg"),
        {"schema": "billing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    credit_note_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.credit_notes.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.invoice_items.id", ondelete="RESTRICT"), nullable=False
    )
    pack_size_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"), nullable=False
    )
    qty_pkts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    return_disposition: Mapped[str] = mapped_column(String(24), nullable=False)
    taxable_reversed_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cgst_reversed_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    sgst_reversed_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    igst_reversed_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    line_total_reversed_paisa: Mapped[int] = mapped_column(
        BigInteger,
        Computed(
            "taxable_reversed_paisa + cgst_reversed_paisa + sgst_reversed_paisa + igst_reversed_paisa",
            persisted=True,
        ),
        nullable=False,
    )

    credit_note: Mapped[CreditNote] = relationship(back_populates="items")


class Dispatch(Base):
    """Physical FG Dispatch & Delivery Tracking header bound to an issued GST Invoice."""

    __tablename__ = "dispatches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CREATED', 'READY_FOR_DISPATCH', 'DISPATCHED', 'IN_TRANSIT', 'DELIVERED', 'DELIVERY_EXCEPTION')",
            name="dsp_status_enum",
        ),
        CheckConstraint("version >= 1", name="dsp_version_pos"),
        Index("idx_dispatches_invoice", "invoice_id"),
        Index("idx_dispatches_order", "sales_order_id"),
        Index("idx_dispatches_status_date", "status", text("dispatch_date DESC"), text("id DESC")),
        {"schema": "billing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dispatch_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.invoices.id", ondelete="RESTRICT"), nullable=False
    )
    sales_order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.sales_orders.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.customers.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="'CREATED'")
    dispatch_date: Mapped[date] = mapped_column(Date, nullable=False)
    transporter_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vehicle_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lr_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    packing_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    packing_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ready_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    in_transit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_confirmed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    delivery_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_exception_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    invoice: Mapped[Invoice] = relationship(back_populates="dispatches")
    items: Mapped[list["DispatchItem"]] = relationship(
        back_populates="dispatch", order_by="DispatchItem.id.asc()"
    )
    status_history: Mapped[list["DispatchStatusHistory"]] = relationship(
        back_populates="dispatch", order_by="DispatchStatusHistory.changed_at.asc(), DispatchStatusHistory.id.asc()"
    )


class DispatchItem(Base):
    """Per-SKU dispatched & delivered quantities supporting partial dispatch and discrepancy log."""

    __tablename__ = "dispatch_items"
    __table_args__ = (
        CheckConstraint("dispatched_qty_pkts > 0", name="di_qty_pos"),
        CheckConstraint(
            "received_qty_pkts IS NULL OR (received_qty_pkts >= 0 AND received_qty_pkts <= dispatched_qty_pkts)",
            name="di_rec_bounds",
        ),
        CheckConstraint("discrepancy_qty_pkts >= 0", name="di_disc_non_neg"),
        UniqueConstraint("dispatch_id", "invoice_item_id", name="uq_di_dsp_inv_item"),
        {"schema": "billing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dispatch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.dispatches.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.invoice_items.id", ondelete="RESTRICT"), nullable=False
    )
    pack_size_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"), nullable=False
    )
    dispatched_qty_pkts: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_code_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    received_qty_pkts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discrepancy_qty_pkts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    discrepancy_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    dispatch: Mapped[Dispatch] = relationship(back_populates="items")


class DispatchStatusHistory(Base):
    """Append-only Dispatch & Delivery status progression timeline."""

    __tablename__ = "dispatch_status_history"
    __table_args__ = (
        CheckConstraint("from_status IS DISTINCT FROM to_status", name="dsh_no_noop"),
        Index("idx_dsh_dispatch_time", "dispatch_id", "changed_at"),
        {"schema": "billing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dispatch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("billing.dispatches.id", ondelete="RESTRICT"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    changed_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    dispatch: Mapped[Dispatch] = relationship(back_populates="status_history")
