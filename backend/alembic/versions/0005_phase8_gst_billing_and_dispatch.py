"""Phase 8 GST Billing, Credit Notes, Dispatch Management, Delivery Tracking & Ledger Integration.

Revision ID: 0005_phase8_gst_billing_dispatch
Revises: 0004_phase7_bom_production
Create Date: 2026-11-25 14:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_phase8_gst_billing_dispatch"
down_revision: str | Sequence[str] | None = "0004_phase7_bom_production"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS billing")

    # --- FISCAL SEQUENCES ---
    op.create_table(
        "fiscal_sequences",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("doc_type", sa.String(length=16), nullable=False),
        sa.Column("financial_year", sa.String(length=7), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("last_seq_no", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("doc_type IN ('INVOICE', 'CREDIT_NOTE', 'DISPATCH')", name="chk_fiscal_sequences_fs_doc_type_enum"),
        sa.CheckConstraint("financial_year ~ '^[0-9]{4}-[0-9]{2}$'", name="chk_fiscal_sequences_fs_fy_format"),
        sa.CheckConstraint("last_seq_no >= 0", name="chk_fiscal_sequences_fs_seq_non_neg"),
        sa.PrimaryKeyConstraint("id", name="pk_fiscal_sequences"),
        sa.UniqueConstraint("doc_type", "financial_year", name="uq_fiscal_seq_type_fy"),
        schema="billing",
    )

    # --- INVOICES ---
    op.create_table(
        "invoices",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("draft_ref", sa.String(length=40), nullable=False),
        sa.Column("invoice_number", sa.String(length=32), nullable=True),
        sa.Column("financial_year", sa.String(length=7), nullable=False),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_name", sa.String(length=160), nullable=False),
        sa.Column("customer_type", sa.String(length=20), nullable=False),
        sa.Column("seller_legal_name", sa.String(length=200), nullable=False),
        sa.Column("seller_gstin", sa.String(length=15), nullable=False),
        sa.Column("seller_state_name", sa.String(length=80), nullable=False),
        sa.Column("seller_state_code", sa.String(length=2), nullable=False),
        sa.Column("seller_address", sa.Text(), nullable=False),
        sa.Column("buyer_gstin", sa.String(length=15), nullable=True),
        sa.Column("place_of_supply_state_name", sa.String(length=80), nullable=False),
        sa.Column("place_of_supply_state_code", sa.String(length=2), nullable=False),
        sa.Column("billing_address_snapshot", sa.Text(), nullable=False),
        sa.Column("shipping_address_snapshot", sa.Text(), nullable=False),
        sa.Column("nature_of_supply", sa.String(length=16), nullable=False),
        sa.Column("supply_type", sa.String(length=16), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("payment_terms", sa.String(length=80), nullable=False),
        sa.Column("doc_status", sa.String(length=24), server_default="DRAFT", nullable=False),
        sa.Column("payment_status", sa.String(length=20), server_default="UNPAID", nullable=False),
        sa.Column("dispatch_status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column("discount_total_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("taxable_total_paisa", sa.BigInteger(), nullable=False),
        sa.Column("cgst_total_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("sgst_total_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("igst_total_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("round_off_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "grand_total_paisa",
            sa.BigInteger(),
            sa.Computed(
                "taxable_total_paisa + cgst_total_paisa + sgst_total_paisa + igst_total_paisa + round_off_paisa",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("paid_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("credited_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "outstanding_paisa",
            sa.BigInteger(),
            sa.Computed(
                "GREATEST(0::bigint, taxable_total_paisa + cgst_total_paisa + sgst_total_paisa + igst_total_paisa + round_off_paisa - credited_paisa - paid_paisa)",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("amount_in_words", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("legal_declaration", sa.Text(), nullable=False),
        sa.Column("tax_calculation_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("verified_by", sa.BigInteger(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_remarks", sa.Text(), nullable=True),
        sa.Column("issued_by", sa.BigInteger(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("financial_year ~ '^[0-9]{4}-[0-9]{2}$'", name="chk_invoices_inv_fy_format"),
        sa.CheckConstraint("nature_of_supply IN ('B2B', 'B2C')", name="chk_invoices_inv_nature_enum"),
        sa.CheckConstraint("supply_type IN ('INTRA_STATE', 'INTER_STATE')", name="chk_invoices_inv_supply_enum"),
        sa.CheckConstraint("doc_status IN ('DRAFT', 'ISSUED', 'CANCELLED_BY_CN')", name="chk_invoices_inv_doc_status_enum"),
        sa.CheckConstraint("payment_status IN ('UNPAID', 'PARTIALLY_PAID', 'PAID', 'CREDITED')", name="chk_invoices_inv_payment_status_enum"),
        sa.CheckConstraint("dispatch_status IN ('PENDING', 'PARTIAL', 'DISPATCHED')", name="chk_invoices_inv_dispatch_status_enum"),
        sa.CheckConstraint("discount_total_paisa >= 0", name="chk_invoices_inv_disc_non_neg"),
        sa.CheckConstraint("taxable_total_paisa >= 0", name="chk_invoices_inv_taxable_non_neg"),
        sa.CheckConstraint("cgst_total_paisa >= 0", name="chk_invoices_inv_cgst_non_neg"),
        sa.CheckConstraint("sgst_total_paisa >= 0", name="chk_invoices_inv_sgst_non_neg"),
        sa.CheckConstraint("igst_total_paisa >= 0", name="chk_invoices_inv_igst_non_neg"),
        sa.CheckConstraint("round_off_paisa >= -100 AND round_off_paisa <= 100", name="chk_invoices_inv_round_off_bounds"),
        sa.CheckConstraint("paid_paisa >= 0", name="chk_invoices_inv_paid_non_neg"),
        sa.CheckConstraint("credited_paisa >= 0", name="chk_invoices_inv_credited_non_neg"),
        sa.CheckConstraint("version >= 1", name="chk_invoices_inv_version_pos"),
        sa.CheckConstraint(
            "(supply_type = 'INTRA_STATE' AND igst_total_paisa = 0 AND cgst_total_paisa = sgst_total_paisa) OR "
            "(supply_type = 'INTER_STATE' AND cgst_total_paisa = 0 AND sgst_total_paisa = 0)",
            name="chk_invoices_inv_gst_split",
        ),
        sa.CheckConstraint(
            "(doc_status = 'DRAFT' AND invoice_number IS NULL) OR "
            "(doc_status IN ('ISSUED', 'CANCELLED_BY_CN') AND invoice_number IS NOT NULL AND issued_by IS NOT NULL AND issued_at IS NOT NULL)",
            name="chk_invoices_inv_issued_number_required",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["iam.users.id"], name="fk_invoices_created_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["sales.customers.id"], name="fk_invoices_customer_id_customers", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["issued_by"], ["iam.users.id"], name="fk_invoices_issued_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales.sales_orders.id"], name="fk_invoices_sales_order_id_sales_orders", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by"], ["iam.users.id"], name="fk_invoices_verified_by_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_invoices"),
        sa.UniqueConstraint("draft_ref", name="uq_invoices_draft_ref"),
        sa.UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
        schema="billing",
    )
    op.create_index(
        "uq_invoices_active_order",
        "invoices",
        ["sales_order_id"],
        unique=True,
        schema="billing",
        postgresql_where=sa.text("doc_status <> 'CANCELLED_BY_CN'"),
    )
    op.create_index("idx_invoices_customer_date", "invoices", ["customer_id", sa.text("invoice_date DESC"), sa.text("id DESC")], unique=False, schema="billing")
    op.create_index("idx_invoices_fy_date_status", "invoices", ["financial_year", "invoice_date", "doc_status"], unique=False, schema="billing")

    op.create_table(
        "invoice_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("sales_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_code", sa.String(length=40), nullable=False),
        sa.Column("product_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("hsn_code", sa.String(length=12), nullable=False),
        sa.Column("qty_pkts", sa.Integer(), nullable=False),
        sa.Column("uom", sa.String(length=16), server_default="packet", nullable=False),
        sa.Column("unit_price_paisa", sa.BigInteger(), nullable=False),
        sa.Column("discount_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("taxable_paisa", sa.BigInteger(), nullable=False),
        sa.Column("gst_rate_bps", sa.Integer(), nullable=False),
        sa.Column("cgst_rate_bps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sgst_rate_bps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("igst_rate_bps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cgst_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("sgst_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("igst_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "line_total_paisa",
            sa.BigInteger(),
            sa.Computed("taxable_paisa + cgst_paisa + sgst_paisa + igst_paisa", persisted=True),
            nullable=False,
        ),
        sa.CheckConstraint("qty_pkts > 0", name="chk_invoice_items_ii_qty_pos"),
        sa.CheckConstraint("unit_price_paisa >= 0", name="chk_invoice_items_ii_price_non_neg"),
        sa.CheckConstraint("discount_paisa >= 0", name="chk_invoice_items_ii_disc_non_neg"),
        sa.CheckConstraint("taxable_paisa >= 0", name="chk_invoice_items_ii_taxable_non_neg"),
        sa.CheckConstraint("gst_rate_bps >= 0", name="chk_invoice_items_ii_gst_bps_non_neg"),
        sa.CheckConstraint("cgst_paisa >= 0", name="chk_invoice_items_ii_cgst_non_neg"),
        sa.CheckConstraint("sgst_paisa >= 0", name="chk_invoice_items_ii_sgst_non_neg"),
        sa.CheckConstraint("igst_paisa >= 0", name="chk_invoice_items_ii_igst_non_neg"),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing.invoices.id"], name="fk_invoice_items_invoice_id_invoices", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pack_size_id"], ["sales.pack_sizes.id"], name="fk_invoice_items_pack_size_id_pack_sizes", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sales_order_item_id"], ["sales.sales_order_items.id"], name="fk_invoice_items_sales_order_item_id_sales_order_items", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_invoice_items"),
        sa.UniqueConstraint("invoice_id", "sales_order_item_id", name="uq_ii_inv_order_item"),
        schema="billing",
    )

    op.create_table(
        "invoice_tax_components",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("hsn_code", sa.String(length=12), nullable=False),
        sa.Column("tax_type", sa.String(length=8), nullable=False),
        sa.Column("rate_bps", sa.Integer(), nullable=False),
        sa.Column("taxable_base_paisa", sa.BigInteger(), nullable=False),
        sa.Column("tax_amount_paisa", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("tax_type IN ('CGST', 'SGST', 'IGST')", name="chk_invoice_tax_components_itc_tax_type_enum"),
        sa.CheckConstraint("rate_bps >= 0", name="chk_invoice_tax_components_itc_rate_non_neg"),
        sa.CheckConstraint("taxable_base_paisa >= 0", name="chk_invoice_tax_components_itc_base_non_neg"),
        sa.CheckConstraint("tax_amount_paisa >= 0", name="chk_invoice_tax_components_itc_amt_non_neg"),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing.invoices.id"], name="fk_invoice_tax_components_invoice_id_invoices", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_invoice_tax_components"),
        sa.UniqueConstraint("invoice_id", "hsn_code", "tax_type", "rate_bps", name="uq_itc_bucket"),
        schema="billing",
    )

    # --- CREDIT NOTES ---
    op.create_table(
        "credit_notes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("draft_ref", sa.String(length=40), nullable=False),
        sa.Column("cn_number", sa.String(length=32), nullable=True),
        sa.Column("financial_year", sa.String(length=7), nullable=False),
        sa.Column("original_invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("supply_type", sa.String(length=16), nullable=False),
        sa.Column("note_type", sa.String(length=24), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="DRAFT", nullable=False),
        sa.Column("cancel_original_invoice", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("taxable_reversed_paisa", sa.BigInteger(), nullable=False),
        sa.Column("cgst_reversed_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("sgst_reversed_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("igst_reversed_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("round_off_reversed_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "total_reversed_paisa",
            sa.BigInteger(),
            sa.Computed(
                "taxable_reversed_paisa + cgst_reversed_paisa + sgst_reversed_paisa + igst_reversed_paisa + round_off_reversed_paisa",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_by", sa.BigInteger(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("financial_year ~ '^[0-9]{4}-[0-9]{2}$'", name="chk_credit_notes_cn_fy_format"),
        sa.CheckConstraint("supply_type IN ('INTRA_STATE', 'INTER_STATE')", name="chk_credit_notes_cn_supply_enum"),
        sa.CheckConstraint("note_type IN ('INVOICE_CANCELLATION', 'SALES_RETURN', 'VALUE_ADJUSTMENT')", name="chk_credit_notes_cn_type_enum"),
        sa.CheckConstraint("status IN ('DRAFT', 'ISSUED')", name="chk_credit_notes_cn_status_enum"),
        sa.CheckConstraint("length(trim(reason)) >= 5", name="chk_credit_notes_cn_reason_len"),
        sa.CheckConstraint("taxable_reversed_paisa >= 0", name="chk_credit_notes_cn_taxable_non_neg"),
        sa.CheckConstraint("cgst_reversed_paisa >= 0", name="chk_credit_notes_cn_cgst_non_neg"),
        sa.CheckConstraint("sgst_reversed_paisa >= 0", name="chk_credit_notes_cn_sgst_non_neg"),
        sa.CheckConstraint("igst_reversed_paisa >= 0", name="chk_credit_notes_cn_igst_non_neg"),
        sa.CheckConstraint(
            "(status = 'DRAFT' AND cn_number IS NULL) OR (status = 'ISSUED' AND cn_number IS NOT NULL AND issued_by IS NOT NULL AND issued_at IS NOT NULL)",
            name="chk_credit_notes_cn_issued_number_required",
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["iam.users.id"], name="fk_credit_notes_approved_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["iam.users.id"], name="fk_credit_notes_created_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["sales.customers.id"], name="fk_credit_notes_customer_id_customers", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["issued_by"], ["iam.users.id"], name="fk_credit_notes_issued_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["original_invoice_id"], ["billing.invoices.id"], name="fk_credit_notes_original_invoice_id_invoices", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_credit_notes"),
        sa.UniqueConstraint("cn_number", name="uq_credit_notes_cn_number"),
        sa.UniqueConstraint("draft_ref", name="uq_credit_notes_draft_ref"),
        schema="billing",
    )

    op.create_table(
        "credit_note_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("credit_note_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_item_id", sa.BigInteger(), nullable=False),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=False),
        sa.Column("qty_pkts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("return_disposition", sa.String(length=24), nullable=False),
        sa.Column("taxable_reversed_paisa", sa.BigInteger(), nullable=False),
        sa.Column("cgst_reversed_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("sgst_reversed_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("igst_reversed_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "line_total_reversed_paisa",
            sa.BigInteger(),
            sa.Computed("taxable_reversed_paisa + cgst_reversed_paisa + sgst_reversed_paisa + igst_reversed_paisa", persisted=True),
            nullable=False,
        ),
        sa.CheckConstraint("qty_pkts >= 0", name="chk_credit_note_items_cni_qty_non_neg"),
        sa.CheckConstraint("return_disposition IN ('NONE_NOT_DISPATCHED', 'RESTOCK_SELLABLE', 'SCRAP_DAMAGED')", name="chk_credit_note_items_cni_disp_enum"),
        sa.CheckConstraint("taxable_reversed_paisa >= 0", name="chk_credit_note_items_cni_taxable_non_neg"),
        sa.CheckConstraint("cgst_reversed_paisa >= 0", name="chk_credit_note_items_cni_cgst_non_neg"),
        sa.CheckConstraint("sgst_reversed_paisa >= 0", name="chk_credit_note_items_cni_sgst_non_neg"),
        sa.CheckConstraint("igst_reversed_paisa >= 0", name="chk_credit_note_items_cni_igst_non_neg"),
        sa.ForeignKeyConstraint(["credit_note_id"], ["billing.credit_notes.id"], name="fk_credit_note_items_credit_note_id_credit_notes", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_item_id"], ["billing.invoice_items.id"], name="fk_credit_note_items_invoice_item_id_invoice_items", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pack_size_id"], ["sales.pack_sizes.id"], name="fk_credit_note_items_pack_size_id_pack_sizes", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_credit_note_items"),
        schema="billing",
    )

    # --- DISPATCHES & DELIVERY TRACKING ---
    op.create_table(
        "dispatches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dispatch_number", sa.String(length=32), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="CREATED", nullable=False),
        sa.Column("dispatch_date", sa.Date(), nullable=False),
        sa.Column("transporter_name", sa.String(length=120), nullable=True),
        sa.Column("vehicle_number", sa.String(length=40), nullable=True),
        sa.Column("lr_number", sa.String(length=64), nullable=True),
        sa.Column("packing_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("packing_remarks", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ready_by", sa.BigInteger(), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_by", sa.BigInteger(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("in_transit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("delivery_confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("delivery_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_remarks", sa.Text(), nullable=True),
        sa.Column("delivery_exception_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "status IN ('CREATED', 'READY_FOR_DISPATCH', 'DISPATCHED', 'IN_TRANSIT', 'DELIVERED', 'DELIVERY_EXCEPTION')",
            name="chk_dispatches_dsp_status_enum",
        ),
        sa.CheckConstraint("version >= 1", name="chk_dispatches_dsp_version_pos"),
        sa.ForeignKeyConstraint(["created_by"], ["iam.users.id"], name="fk_dispatches_created_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["sales.customers.id"], name="fk_dispatches_customer_id_customers", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["delivery_confirmed_by"], ["iam.users.id"], name="fk_dispatches_delivery_confirmed_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dispatched_by"], ["iam.users.id"], name="fk_dispatches_dispatched_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing.invoices.id"], name="fk_dispatches_invoice_id_invoices", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ready_by"], ["iam.users.id"], name="fk_dispatches_ready_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales.sales_orders.id"], name="fk_dispatches_sales_order_id_sales_orders", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_dispatches"),
        sa.UniqueConstraint("dispatch_number", name="uq_dispatches_dispatch_number"),
        schema="billing",
    )
    op.create_index("idx_dispatches_invoice", "dispatches", ["invoice_id"], unique=False, schema="billing")
    op.create_index("idx_dispatches_order", "dispatches", ["sales_order_id"], unique=False, schema="billing")
    op.create_index("idx_dispatches_status_date", "dispatches", ["status", sa.text("dispatch_date DESC"), sa.text("id DESC")], unique=False, schema="billing")

    op.create_table(
        "dispatch_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dispatch_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_item_id", sa.BigInteger(), nullable=False),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=False),
        sa.Column("dispatched_qty_pkts", sa.Integer(), nullable=False),
        sa.Column("batch_code_ref", sa.String(length=120), nullable=True),
        sa.Column("received_qty_pkts", sa.Integer(), nullable=True),
        sa.Column("discrepancy_qty_pkts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("discrepancy_remarks", sa.Text(), nullable=True),
        sa.CheckConstraint("dispatched_qty_pkts > 0", name="chk_dispatch_items_di_qty_pos"),
        sa.CheckConstraint(
            "received_qty_pkts IS NULL OR (received_qty_pkts >= 0 AND received_qty_pkts <= dispatched_qty_pkts)",
            name="chk_dispatch_items_di_rec_bounds",
        ),
        sa.CheckConstraint("discrepancy_qty_pkts >= 0", name="chk_dispatch_items_di_disc_non_neg"),
        sa.ForeignKeyConstraint(["dispatch_id"], ["billing.dispatches.id"], name="fk_dispatch_items_dispatch_id_dispatches", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_item_id"], ["billing.invoice_items.id"], name="fk_dispatch_items_invoice_item_id_invoice_items", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pack_size_id"], ["sales.pack_sizes.id"], name="fk_dispatch_items_pack_size_id_pack_sizes", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_dispatch_items"),
        sa.UniqueConstraint("dispatch_id", "invoice_item_id", name="uq_di_dsp_inv_item"),
        schema="billing",
    )

    op.create_table(
        "dispatch_status_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dispatch_id", sa.BigInteger(), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("changed_by", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("from_status IS DISTINCT FROM to_status", name="chk_dispatch_status_history_dsh_no_noop"),
        sa.ForeignKeyConstraint(["changed_by"], ["iam.users.id"], name="fk_dispatch_status_history_changed_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dispatch_id"], ["billing.dispatches.id"], name="fk_dispatch_status_history_dispatch_id_dispatches", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_dispatch_status_history"),
        schema="billing",
    )
    op.create_index("idx_dsh_dispatch_time", "dispatch_status_history", ["dispatch_id", "changed_at"], unique=False, schema="billing")

    # --- EXTEND INVENTORY LEDGER & STOCK RESERVATIONS ---
    op.add_column("stock_reservations", sa.Column("fulfilled_qty_pkts", sa.Integer(), server_default="0", nullable=False), schema="inventory")
    op.create_check_constraint(
        "chk_stock_reservations_fulfilled_bounds",
        "stock_reservations",
        "fulfilled_qty_pkts >= 0 AND fulfilled_qty_pkts <= reserved_qty_pkts",
        schema="inventory",
    )

    op.add_column("inventory_movements", sa.Column("dispatch_item_id", sa.BigInteger(), nullable=True), schema="inventory")
    op.add_column("inventory_movements", sa.Column("credit_note_item_id", sa.BigInteger(), nullable=True), schema="inventory")
    op.create_foreign_key(
        "fk_inventory_movements_dispatch_item_id",
        "inventory_movements",
        "dispatch_items",
        ["dispatch_item_id"],
        ["id"],
        source_schema="inventory",
        referent_schema="billing",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_inventory_movements_credit_note_item_id",
        "inventory_movements",
        "credit_note_items",
        ["credit_note_item_id"],
        ["id"],
        source_schema="inventory",
        referent_schema="billing",
        ondelete="RESTRICT",
    )
    op.create_index(
        "idx_mov_dispatch_item",
        "inventory_movements",
        ["dispatch_item_id"],
        unique=False,
        schema="inventory",
        postgresql_where=sa.text("dispatch_item_id IS NOT NULL"),
    )
    op.create_index(
        "idx_mov_credit_note_item",
        "inventory_movements",
        ["credit_note_item_id"],
        unique=False,
        schema="inventory",
        postgresql_where=sa.text("credit_note_item_id IS NOT NULL"),
    )

    op.drop_constraint("chk_inventory_movements_mov_source_required", "inventory_movements", schema="inventory", type_="check")
    op.create_check_constraint(
        "chk_inventory_movements_mov_source_required",
        "inventory_movements",
        "(source_doc_type = 'OPENING_BALANCE' AND opening_balance_id IS NOT NULL) OR "
        "(source_doc_type = 'PURCHASE_RECEIPT' AND purchase_receipt_item_id IS NOT NULL) OR "
        "(source_doc_type IN ('STOCK_ADJUSTMENT', 'SUPPLIER_RETURN') AND stock_adjustment_id IS NOT NULL) OR "
        "(source_doc_type = 'PRODUCTION_RUN' AND production_run_id IS NOT NULL) OR "
        "(source_doc_type = 'DISPATCH' AND dispatch_item_id IS NOT NULL) OR "
        "(source_doc_type = 'CREDIT_NOTE' AND credit_note_item_id IS NOT NULL)",
        schema="inventory",
    )

    # --- POSTGRESQL IMMUTABILITY & INTEGRITY TRIGGERS ---
    op.execute(
        """
        CREATE TRIGGER trg_dispatch_status_history_append_only
        BEFORE UPDATE OR DELETE ON billing.dispatch_status_history
        FOR EACH ROW EXECUTE FUNCTION audit.fn_prevent_mutation();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION billing.fn_protect_invoice_immutability()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.doc_status <> 'DRAFT' THEN
                    RAISE EXCEPTION 'Issued or cancelled GST invoice (%) cannot be deleted.', OLD.id USING ERRCODE = '42501';
                END IF;
                RETURN OLD;
            END IF;

            IF OLD.doc_status <> 'DRAFT' THEN
                IF NEW.invoice_number IS DISTINCT FROM OLD.invoice_number
                    OR NEW.draft_ref IS DISTINCT FROM OLD.draft_ref
                    OR NEW.financial_year IS DISTINCT FROM OLD.financial_year
                    OR NEW.sales_order_id IS DISTINCT FROM OLD.sales_order_id
                    OR NEW.customer_id IS DISTINCT FROM OLD.customer_id
                    OR NEW.seller_gstin IS DISTINCT FROM OLD.seller_gstin
                    OR NEW.seller_state_code IS DISTINCT FROM OLD.seller_state_code
                    OR NEW.buyer_gstin IS DISTINCT FROM OLD.buyer_gstin
                    OR NEW.place_of_supply_state_code IS DISTINCT FROM OLD.place_of_supply_state_code
                    OR NEW.nature_of_supply IS DISTINCT FROM OLD.nature_of_supply
                    OR NEW.supply_type IS DISTINCT FROM OLD.supply_type
                    OR NEW.invoice_date IS DISTINCT FROM OLD.invoice_date
                    OR NEW.due_date IS DISTINCT FROM OLD.due_date
                    OR NEW.discount_total_paisa IS DISTINCT FROM OLD.discount_total_paisa
                    OR NEW.taxable_total_paisa IS DISTINCT FROM OLD.taxable_total_paisa
                    OR NEW.cgst_total_paisa IS DISTINCT FROM OLD.cgst_total_paisa
                    OR NEW.sgst_total_paisa IS DISTINCT FROM OLD.sgst_total_paisa
                    OR NEW.igst_total_paisa IS DISTINCT FROM OLD.igst_total_paisa
                    OR NEW.round_off_paisa IS DISTINCT FROM OLD.round_off_paisa
                    OR NEW.amount_in_words IS DISTINCT FROM OLD.amount_in_words
                    OR NEW.tax_calculation_snapshot IS DISTINCT FROM OLD.tax_calculation_snapshot
                    OR NEW.issued_by IS DISTINCT FROM OLD.issued_by
                    OR NEW.issued_at IS DISTINCT FROM OLD.issued_at
                    OR NEW.doc_status = 'DRAFT'
                    OR (OLD.doc_status = 'CANCELLED_BY_CN' AND NEW.doc_status IS DISTINCT FROM 'CANCELLED_BY_CN') THEN
                    RAISE EXCEPTION 'Issued GST invoice (%) cannot be modified or reverted; issue a Credit Note instead.', OLD.id USING ERRCODE = '42501';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_invoice_immutability
        BEFORE UPDATE OR DELETE ON billing.invoices
        FOR EACH ROW EXECUTE FUNCTION billing.fn_protect_invoice_immutability();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION billing.fn_protect_invoice_child_immutability()
        RETURNS TRIGGER AS $$
        DECLARE
            v_status VARCHAR(24);
            v_inv_id BIGINT;
        BEGIN
            v_inv_id := COALESCE(NEW.invoice_id, OLD.invoice_id);
            SELECT doc_status INTO v_status FROM billing.invoices WHERE id = v_inv_id;
            IF v_status IS DISTINCT FROM 'DRAFT' THEN
                RAISE EXCEPTION 'Cannot modify lines/taxes of non-DRAFT invoice % (status %).', v_inv_id, v_status USING ERRCODE = '42501';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_invoice_items_immutability
        BEFORE INSERT OR UPDATE OR DELETE ON billing.invoice_items
        FOR EACH ROW EXECUTE FUNCTION billing.fn_protect_invoice_child_immutability();
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_invoice_tax_components_immutability
        BEFORE INSERT OR UPDATE OR DELETE ON billing.invoice_tax_components
        FOR EACH ROW EXECUTE FUNCTION billing.fn_protect_invoice_child_immutability();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION billing.fn_protect_credit_note_immutability()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status <> 'DRAFT' THEN
                    RAISE EXCEPTION 'Issued Credit Note (%) cannot be deleted.', OLD.id USING ERRCODE = '42501';
                END IF;
                RETURN OLD;
            END IF;
            IF OLD.status <> 'DRAFT' THEN
                RAISE EXCEPTION 'Issued Credit Note (%) is immutable.', OLD.id USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_credit_note_immutability
        BEFORE UPDATE OR DELETE ON billing.credit_notes
        FOR EACH ROW EXECUTE FUNCTION billing.fn_protect_credit_note_immutability();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION billing.fn_guard_over_dispatch()
        RETURNS TRIGGER AS $$
        DECLARE
            v_invoiced_qty INT;
            v_existing_dispatched INT;
        BEGIN
            SELECT qty_pkts INTO v_invoiced_qty
            FROM billing.invoice_items
            WHERE id = NEW.invoice_item_id;

            SELECT COALESCE(SUM(dispatched_qty_pkts), 0) INTO v_existing_dispatched
            FROM billing.dispatch_items
            WHERE invoice_item_id = NEW.invoice_item_id
              AND id IS DISTINCT FROM NEW.id;

            IF v_existing_dispatched + NEW.dispatched_qty_pkts > v_invoiced_qty THEN
                RAISE EXCEPTION 'Over-dispatch blocked on invoice_item %: existing (%) + new (%) > invoiced (%).',
                    NEW.invoice_item_id, v_existing_dispatched, NEW.dispatched_qty_pkts, v_invoiced_qty
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_guard_over_dispatch
        BEFORE INSERT OR UPDATE ON billing.dispatch_items
        FOR EACH ROW EXECUTE FUNCTION billing.fn_guard_over_dispatch();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_guard_over_dispatch ON billing.dispatch_items")
    op.execute("DROP FUNCTION IF EXISTS billing.fn_guard_over_dispatch()")
    op.execute("DROP TRIGGER IF EXISTS trg_credit_note_immutability ON billing.credit_notes")
    op.execute("DROP FUNCTION IF EXISTS billing.fn_protect_credit_note_immutability()")
    op.execute("DROP TRIGGER IF EXISTS trg_invoice_tax_components_immutability ON billing.invoice_tax_components")
    op.execute("DROP TRIGGER IF EXISTS trg_invoice_items_immutability ON billing.invoice_items")
    op.execute("DROP FUNCTION IF EXISTS billing.fn_protect_invoice_child_immutability()")
    op.execute("DROP TRIGGER IF EXISTS trg_invoice_immutability ON billing.invoices")
    op.execute("DROP FUNCTION IF EXISTS billing.fn_protect_invoice_immutability()")
    op.execute("DROP TRIGGER IF EXISTS trg_dispatch_status_history_append_only ON billing.dispatch_status_history")

    op.drop_constraint("chk_inventory_movements_mov_source_required", "inventory_movements", schema="inventory", type_="check")
    op.create_check_constraint(
        "chk_inventory_movements_mov_source_required",
        "inventory_movements",
        "(source_doc_type = 'OPENING_BALANCE' AND opening_balance_id IS NOT NULL) OR "
        "(source_doc_type = 'PURCHASE_RECEIPT' AND purchase_receipt_item_id IS NOT NULL) OR "
        "(source_doc_type IN ('STOCK_ADJUSTMENT', 'SUPPLIER_RETURN') AND stock_adjustment_id IS NOT NULL) OR "
        "(source_doc_type = 'PRODUCTION_RUN' AND production_run_id IS NOT NULL) OR "
        "source_doc_type IN ('DISPATCH', 'CREDIT_NOTE')",
        schema="inventory",
    )
    op.drop_index("idx_mov_credit_note_item", table_name="inventory_movements", schema="inventory")
    op.drop_index("idx_mov_dispatch_item", table_name="inventory_movements", schema="inventory")
    op.drop_constraint("fk_inventory_movements_credit_note_item_id", "inventory_movements", schema="inventory", type_="foreignkey")
    op.drop_constraint("fk_inventory_movements_dispatch_item_id", "inventory_movements", schema="inventory", type_="foreignkey")
    op.drop_column("inventory_movements", "credit_note_item_id", schema="inventory")
    op.drop_column("inventory_movements", "dispatch_item_id", schema="inventory")

    op.drop_constraint("chk_stock_reservations_fulfilled_bounds", "stock_reservations", schema="inventory", type_="check")
    op.drop_column("stock_reservations", "fulfilled_qty_pkts", schema="inventory")

    op.drop_index("idx_dsh_dispatch_time", table_name="dispatch_status_history", schema="billing")
    op.drop_table("dispatch_status_history", schema="billing")
    op.drop_table("dispatch_items", schema="billing")
    op.drop_index("idx_dispatches_status_date", table_name="dispatches", schema="billing")
    op.drop_index("idx_dispatches_order", table_name="dispatches", schema="billing")
    op.drop_index("idx_dispatches_invoice", table_name="dispatches", schema="billing")
    op.drop_table("dispatches", schema="billing")

    op.drop_table("credit_note_items", schema="billing")
    op.drop_table("credit_notes", schema="billing")
    op.drop_table("invoice_tax_components", schema="billing")
    op.drop_table("invoice_items", schema="billing")
    op.drop_index("idx_invoices_fy_date_status", table_name="invoices", schema="billing")
    op.drop_index("idx_invoices_customer_date", table_name="invoices", schema="billing")
    op.drop_index("uq_invoices_active_order", table_name="invoices", schema="billing")
    op.drop_table("invoices", schema="billing")
    op.drop_table("fiscal_sequences", schema="billing")
    op.execute("DROP SCHEMA IF EXISTS billing")
