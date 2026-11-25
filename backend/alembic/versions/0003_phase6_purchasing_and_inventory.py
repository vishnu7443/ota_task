"""Phase 6 purchasing, materials, UOM conversions, stock adjustments, cost lots, and extended ledger

Revision ID: 0003_phase6_purchasing_inv
Revises: 0002_phase5_order_lifecycle
Create Date: 2026-11-25 11:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_phase6_purchasing_inv"
down_revision: str | Sequence[str] | None = "0002_phase5_order_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS purchasing")
    op.execute("CREATE SCHEMA IF NOT EXISTS production")

    # --- PRODUCTION MATERIALS & UNIT CONVERSIONS SUBSET ---
    op.create_table(
        "materials",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("material_category", sa.String(length=24), nullable=False),
        sa.Column("unit_dimension", sa.String(length=16), nullable=False),
        sa.Column("base_uom", sa.String(length=16), nullable=False),
        sa.Column("display_uom", sa.String(length=16), nullable=False),
        sa.Column("reorder_level_base", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "material_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL')",
            name="chk_materials_mat_category_enum",
        ),
        sa.CheckConstraint(
            "unit_dimension IN ('MASS', 'VOLUME', 'COUNT')",
            name="chk_materials_mat_dim_enum",
        ),
        sa.CheckConstraint(
            "(unit_dimension = 'MASS' AND base_uom = 'g') OR "
            "(unit_dimension = 'VOLUME' AND base_uom = 'ml') OR "
            "(unit_dimension = 'COUNT' AND base_uom = 'piece')",
            name="chk_materials_mat_dim_base_match",
        ),
        sa.CheckConstraint("reorder_level_base >= 0", name="chk_materials_mat_reorder_non_neg"),
        sa.PrimaryKeyConstraint("id", name="pk_materials"),
        sa.UniqueConstraint("code", name="uq_materials_code"),
        schema="production",
    )

    op.create_table(
        "unit_conversions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("from_uom", sa.String(length=16), nullable=False),
        sa.Column("to_base_uom", sa.String(length=16), nullable=False),
        sa.Column("unit_dimension", sa.String(length=16), nullable=False),
        sa.Column("multiplier", sa.Numeric(18, 6), nullable=False),
        sa.CheckConstraint(
            "unit_dimension IN ('MASS', 'VOLUME', 'COUNT')",
            name="chk_unit_conversions_uom_dim_enum",
        ),
        sa.CheckConstraint("multiplier > 0", name="chk_unit_conversions_uom_multiplier_pos"),
        sa.PrimaryKeyConstraint("id", name="pk_unit_conversions"),
        sa.UniqueConstraint("from_uom", "to_base_uom", name="uq_uom_pair"),
        schema="production",
    )

    # --- PURCHASING ---
    op.create_table(
        "suppliers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("contact_person", sa.String(length=120), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=160), nullable=True),
        sa.Column("gstin", sa.String(length=15), nullable=True),
        sa.Column("state_name", sa.String(length=80), nullable=False),
        sa.Column("state_code", sa.String(length=2), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "gstin IS NULL OR gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'",
            name="chk_suppliers_gstin_format",
        ),
        sa.CheckConstraint("state_code ~ '^[0-9]{2}$'", name="chk_suppliers_state_code_format"),
        sa.CheckConstraint(
            "gstin IS NULL OR SUBSTRING(gstin FROM 1 FOR 2) = state_code",
            name="chk_suppliers_gstin_matches_state",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_suppliers"),
        sa.UniqueConstraint("code", name="uq_suppliers_code"),
        schema="purchasing",
    )
    op.create_index("idx_suppliers_active_name", "suppliers", ["is_active", "name"], unique=False, schema="purchasing")

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("po_number", sa.String(length=32), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("expected_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("subtotal_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("tax_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("submitted_by", sa.BigInteger(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.BigInteger(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','APPROVED','REJECTED','PARTIALLY_RECEIVED','RECEIVED','CLOSED','CANCELLED')",
            name="chk_purchase_orders_po_status_enum",
        ),
        sa.CheckConstraint("subtotal_paisa >= 0", name="chk_purchase_orders_po_subtotal_non_negative"),
        sa.CheckConstraint("tax_paisa >= 0", name="chk_purchase_orders_po_tax_non_negative"),
        sa.CheckConstraint("total_paisa >= 0", name="chk_purchase_orders_po_total_non_negative"),
        sa.CheckConstraint("version >= 1", name="chk_purchase_orders_po_version_positive"),
        sa.ForeignKeyConstraint(["approved_by"], ["iam.users.id"], name="fk_purchase_orders_approved_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["iam.users.id"], name="fk_purchase_orders_created_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rejected_by"], ["iam.users.id"], name="fk_purchase_orders_rejected_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by"], ["iam.users.id"], name="fk_purchase_orders_submitted_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_id"], ["purchasing.suppliers.id"], name="fk_purchase_orders_supplier_id_suppliers", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_purchase_orders"),
        sa.UniqueConstraint("po_number", name="uq_purchase_orders_po_number"),
        schema="purchasing",
    )
    op.create_index("idx_po_supplier_date", "purchase_orders", ["supplier_id", sa.text("order_date DESC"), sa.text("id DESC")], unique=False, schema="purchasing")

    op.create_table(
        "purchase_order_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("purchase_order_id", sa.BigInteger(), nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=False),
        sa.Column("entered_qty", sa.Numeric(18, 3), nullable=False),
        sa.Column("entered_uom", sa.String(length=16), nullable=False),
        sa.Column("ordered_qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("received_qty_base", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("rejected_qty_base", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("unit_rate_paisa", sa.BigInteger(), nullable=False),
        sa.Column("gst_rate_bps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("line_subtotal_paisa", sa.BigInteger(), nullable=False),
        sa.Column("line_tax_paisa", sa.BigInteger(), nullable=False),
        sa.Column("line_total_paisa", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("entered_qty > 0", name="chk_purchase_order_items_poi_entered_qty_positive"),
        sa.CheckConstraint("ordered_qty_base > 0", name="chk_purchase_order_items_poi_ordered_base_positive"),
        sa.CheckConstraint("received_qty_base >= 0", name="chk_purchase_order_items_poi_received_base_non_negative"),
        sa.CheckConstraint("rejected_qty_base >= 0", name="chk_purchase_order_items_poi_rejected_base_non_negative"),
        sa.CheckConstraint("unit_rate_paisa >= 0", name="chk_purchase_order_items_poi_rate_non_negative"),
        sa.CheckConstraint("gst_rate_bps >= 0 AND gst_rate_bps <= 2800", name="chk_purchase_order_items_poi_gst_valid"),
        sa.CheckConstraint("line_subtotal_paisa >= 0", name="chk_purchase_order_items_poi_subtotal_non_negative"),
        sa.CheckConstraint("line_tax_paisa >= 0", name="chk_purchase_order_items_poi_tax_non_negative"),
        sa.CheckConstraint("line_total_paisa >= 0", name="chk_purchase_order_items_poi_total_non_negative"),
        sa.ForeignKeyConstraint(["material_id"], ["production.materials.id"], name="fk_purchase_order_items_material_id_materials", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchasing.purchase_orders.id"], name="fk_purchase_order_items_purchase_order_id_purchase_orders", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_purchase_order_items"),
        sa.UniqueConstraint("purchase_order_id", "material_id", name="uq_poi_po_material"),
        schema="purchasing",
    )

    op.create_table(
        "purchase_receipts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("receipt_number", sa.String(length=32), nullable=False),
        sa.Column("client_receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", sa.BigInteger(), nullable=True),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column("supplier_bill_ref", sa.String(length=64), nullable=True),
        sa.Column("receipt_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("subtotal_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("input_gst_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("discrepancy_notes", sa.Text(), nullable=True),
        sa.Column("received_by", sa.BigInteger(), nullable=False),
        sa.Column("submitted_by", sa.BigInteger(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.BigInteger(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by", sa.BigInteger(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','VERIFIED','POSTED','RECEIVED','CLOSED','CANCELLED')",
            name="chk_purchase_receipts_pr_status_enum",
        ),
        sa.CheckConstraint("subtotal_paisa >= 0", name="chk_purchase_receipts_pr_subtotal_non_negative"),
        sa.CheckConstraint("input_gst_paisa >= 0", name="chk_purchase_receipts_pr_gst_non_negative"),
        sa.CheckConstraint("total_paisa >= 0", name="chk_purchase_receipts_pr_total_non_negative"),
        sa.CheckConstraint("version >= 1", name="chk_purchase_receipts_pr_version_positive"),
        sa.ForeignKeyConstraint(["posted_by"], ["iam.users.id"], name="fk_purchase_receipts_posted_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchasing.purchase_orders.id"], name="fk_purchase_receipts_purchase_order_id_purchase_orders", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["received_by"], ["iam.users.id"], name="fk_purchase_receipts_received_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by"], ["iam.users.id"], name="fk_purchase_receipts_submitted_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_id"], ["purchasing.suppliers.id"], name="fk_purchase_receipts_supplier_id_suppliers", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by"], ["iam.users.id"], name="fk_purchase_receipts_verified_by_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_purchase_receipts"),
        sa.UniqueConstraint("client_receipt_id", name="uq_purchase_receipts_client_receipt_id"),
        sa.UniqueConstraint("receipt_number", name="uq_purchase_receipts_receipt_number"),
        schema="purchasing",
    )
    op.create_index("idx_pr_supplier_date", "purchase_receipts", ["supplier_id", sa.text("receipt_date DESC"), sa.text("id DESC")], unique=False, schema="purchasing")
    op.create_index("idx_pr_po", "purchase_receipts", ["purchase_order_id"], unique=False, schema="purchasing")

    op.create_table(
        "purchase_receipt_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("purchase_receipt_id", sa.BigInteger(), nullable=False),
        sa.Column("purchase_order_item_id", sa.BigInteger(), nullable=True),
        sa.Column("material_id", sa.BigInteger(), nullable=False),
        sa.Column("entered_uom", sa.String(length=16), nullable=False),
        sa.Column("received_qty_entered", sa.Numeric(18, 3), nullable=False),
        sa.Column("rejected_qty_entered", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("accepted_qty_entered", sa.Numeric(18, 3), nullable=False),
        sa.Column("received_qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("rejected_qty_base", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("accepted_qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("entered_unit_rate_paisa", sa.BigInteger(), nullable=False),
        sa.Column("gst_rate_bps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unit_cost_paisa_per_base", sa.Numeric(18, 6), nullable=False),
        sa.Column("line_subtotal_paisa", sa.BigInteger(), nullable=False),
        sa.Column("line_tax_paisa", sa.BigInteger(), nullable=False),
        sa.Column("line_total_paisa", sa.BigInteger(), nullable=False),
        sa.Column("batch_code", sa.String(length=40), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("received_qty_entered > 0", name="chk_purchase_receipt_items_pri_rec_entered_pos"),
        sa.CheckConstraint("rejected_qty_entered >= 0", name="chk_purchase_receipt_items_pri_rej_entered_non_neg"),
        sa.CheckConstraint("accepted_qty_entered >= 0", name="chk_purchase_receipt_items_pri_acc_entered_non_neg"),
        sa.CheckConstraint("received_qty_base > 0", name="chk_purchase_receipt_items_pri_rec_base_pos"),
        sa.CheckConstraint("rejected_qty_base >= 0", name="chk_purchase_receipt_items_pri_rej_base_non_neg"),
        sa.CheckConstraint("accepted_qty_base >= 0", name="chk_purchase_receipt_items_pri_acc_base_non_neg"),
        sa.CheckConstraint("accepted_qty_entered + rejected_qty_entered = received_qty_entered", name="chk_purchase_receipt_items_pri_entered_split_match"),
        sa.CheckConstraint("accepted_qty_base + rejected_qty_base = received_qty_base", name="chk_purchase_receipt_items_pri_base_split_match"),
        sa.CheckConstraint("entered_unit_rate_paisa >= 0", name="chk_purchase_receipt_items_pri_rate_non_neg"),
        sa.CheckConstraint("gst_rate_bps >= 0 AND gst_rate_bps <= 2800", name="chk_purchase_receipt_items_pri_gst_valid"),
        sa.CheckConstraint("unit_cost_paisa_per_base >= 0", name="chk_purchase_receipt_items_pri_unit_cost_non_neg"),
        sa.CheckConstraint("line_subtotal_paisa >= 0", name="chk_purchase_receipt_items_pri_sub_non_neg"),
        sa.CheckConstraint("line_tax_paisa >= 0", name="chk_purchase_receipt_items_pri_tax_non_neg"),
        sa.CheckConstraint("line_total_paisa >= 0", name="chk_purchase_receipt_items_pri_tot_non_neg"),
        sa.ForeignKeyConstraint(["material_id"], ["production.materials.id"], name="fk_purchase_receipt_items_material_id_materials", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["purchase_order_item_id"], ["purchasing.purchase_order_items.id"], name="fk_purchase_receipt_items_purchase_order_item_id_purcha_5e93", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["purchase_receipt_id"], ["purchasing.purchase_receipts.id"], name="fk_purchase_receipt_items_purchase_receipt_id_purchase__a252", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_purchase_receipt_items"),
        schema="purchasing",
    )

    # --- EXTEND INVENTORY TABLES & LEDGER FOR RAW/PACKAGING + LOTS + ADJUSTMENTS ---
    op.create_table(
        "cost_lots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("item_category", sa.String(length=20), nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=True),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=True),
        sa.Column("source_doc_type", sa.String(length=24), nullable=False),
        sa.Column("source_doc_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_code", sa.String(length=40), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("original_qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("remaining_qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_cost_paisa_per_base", sa.Numeric(18, 6), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL', 'FINISHED_GOOD')", name="chk_cost_lots_lot_item_category_enum"),
        sa.CheckConstraint("(material_id IS NOT NULL AND pack_size_id IS NULL) OR (pack_size_id IS NOT NULL AND material_id IS NULL)", name="chk_cost_lots_lot_one_item"),
        sa.CheckConstraint("source_doc_type IN ('OPENING_BALANCE','PURCHASE_RECEIPT','PRODUCTION_RUN','CREDIT_NOTE','STOCK_ADJUSTMENT')", name="chk_cost_lots_lot_source_doc_enum"),
        sa.CheckConstraint("original_qty_base > 0", name="chk_cost_lots_lot_orig_qty_pos"),
        sa.CheckConstraint("remaining_qty_base >= 0 AND remaining_qty_base <= original_qty_base", name="chk_cost_lots_lot_rem_qty_bounds"),
        sa.CheckConstraint("unit_cost_paisa_per_base >= 0", name="chk_cost_lots_lot_unit_cost_non_neg"),
        sa.ForeignKeyConstraint(["material_id"], ["production.materials.id"], name="fk_cost_lots_material_id_materials", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pack_size_id"], ["sales.pack_sizes.id"], name="fk_cost_lots_pack_size_id_pack_sizes", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_cost_lots"),
        schema="inventory",
    )
    op.create_index("idx_lots_fifo_open", "cost_lots", ["material_id", "received_at", "id"], unique=False, schema="inventory", postgresql_where=sa.text("remaining_qty_base > 0 AND material_id IS NOT NULL"))
    op.create_index("idx_lots_fg_fefo", "cost_lots", ["pack_size_id", sa.text("expiry_date ASC NULLS LAST"), "received_at", "id"], unique=False, schema="inventory", postgresql_where=sa.text("remaining_qty_base > 0 AND pack_size_id IS NOT NULL"))

    op.create_table(
        "stock_adjustments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("adjustment_number", sa.String(length=32), nullable=False),
        sa.Column("item_category", sa.String(length=20), nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=True),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=True),
        sa.Column("adjustment_type", sa.String(length=24), nullable=False),
        sa.Column("entered_qty", sa.Numeric(18, 3), nullable=False),
        sa.Column("entered_uom", sa.String(length=16), nullable=False),
        sa.Column("delta_qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_cost_paisa_per_base", sa.Numeric(18, 6), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_by", sa.BigInteger(), nullable=False),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL', 'FINISHED_GOOD')", name="chk_stock_adjustments_adj_item_category_enum"),
        sa.CheckConstraint("(item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL') AND material_id IS NOT NULL AND pack_size_id IS NULL) OR (item_category = 'FINISHED_GOOD' AND pack_size_id IS NOT NULL AND material_id IS NULL)", name="chk_stock_adjustments_adj_one_item"),
        sa.CheckConstraint("adjustment_type IN ('DAMAGED','EXPIRED','MISSING','COUNT_CORRECTION','SUPPLIER_RETURN','OTHER')", name="chk_stock_adjustments_adj_type_enum"),
        sa.CheckConstraint("delta_qty_base <> 0", name="chk_stock_adjustments_adj_delta_nonzero"),
        sa.CheckConstraint("entered_qty <> 0", name="chk_stock_adjustments_adj_entered_nonzero"),
        sa.CheckConstraint("unit_cost_paisa_per_base >= 0", name="chk_stock_adjustments_adj_unit_cost_non_neg"),
        sa.CheckConstraint("length(trim(reason)) >= 5", name="chk_stock_adjustments_adj_reason_min_len"),
        sa.CheckConstraint("status IN ('DRAFT','PENDING_APPROVAL','POSTED','REJECTED')", name="chk_stock_adjustments_adj_status_enum"),
        sa.ForeignKeyConstraint(["approved_by"], ["iam.users.id"], name="fk_stock_adjustments_approved_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["material_id"], ["production.materials.id"], name="fk_stock_adjustments_material_id_materials", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pack_size_id"], ["sales.pack_sizes.id"], name="fk_stock_adjustments_pack_size_id_pack_sizes", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by"], ["iam.users.id"], name="fk_stock_adjustments_requested_by_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_stock_adjustments"),
        sa.UniqueConstraint("adjustment_number", name="uq_stock_adjustments_adjustment_number"),
        schema="inventory",
    )

    # Extend opening_balances
    op.add_column("opening_balances", sa.Column("material_id", sa.BigInteger(), nullable=True), schema="inventory")
    op.create_foreign_key("fk_opening_balances_material_id_materials", "opening_balances", "materials", ["material_id"], ["id"], source_schema="inventory", referent_schema="production", ondelete="RESTRICT")
    op.create_check_constraint(
        "chk_opening_balances_ob_one_item",
        "opening_balances",
        "(item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL') AND material_id IS NOT NULL AND pack_size_id IS NULL) OR (item_category = 'FINISHED_GOOD' AND pack_size_id IS NOT NULL AND material_id IS NULL)",
        schema="inventory",
    )
    op.create_index("uq_ob_batch_material", "opening_balances", ["batch_ref", "material_id"], unique=True, schema="inventory", postgresql_where=sa.text("material_id IS NOT NULL"))

    # Extend inventory_balances
    op.add_column("inventory_balances", sa.Column("material_id", sa.BigInteger(), nullable=True), schema="inventory")
    op.create_foreign_key("fk_inventory_balances_material_id_materials", "inventory_balances", "materials", ["material_id"], ["id"], source_schema="inventory", referent_schema="production", ondelete="RESTRICT")
    op.create_check_constraint(
        "chk_inventory_balances_bal_one_item",
        "inventory_balances",
        "(item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL') AND material_id IS NOT NULL AND pack_size_id IS NULL) OR (item_category = 'FINISHED_GOOD' AND pack_size_id IS NOT NULL AND material_id IS NULL)",
        schema="inventory",
    )
    op.create_index("uq_bal_material", "inventory_balances", ["material_id"], unique=True, schema="inventory", postgresql_where=sa.text("material_id IS NOT NULL"))

    # Extend inventory_movements
    op.add_column("inventory_movements", sa.Column("material_id", sa.BigInteger(), nullable=True), schema="inventory")
    op.add_column("inventory_movements", sa.Column("entered_qty", sa.Numeric(18, 3), nullable=True), schema="inventory")
    op.add_column("inventory_movements", sa.Column("entered_uom", sa.String(length=16), nullable=True), schema="inventory")
    op.add_column("inventory_movements", sa.Column("reference_code", sa.String(length=64), nullable=True), schema="inventory")
    op.add_column("inventory_movements", sa.Column("notes", sa.Text(), nullable=True), schema="inventory")
    op.add_column("inventory_movements", sa.Column("purchase_receipt_item_id", sa.BigInteger(), nullable=True), schema="inventory")
    op.add_column("inventory_movements", sa.Column("stock_adjustment_id", sa.BigInteger(), nullable=True), schema="inventory")

    op.create_foreign_key("fk_inventory_movements_material_id_materials", "inventory_movements", "materials", ["material_id"], ["id"], source_schema="inventory", referent_schema="production", ondelete="RESTRICT")
    op.create_foreign_key("fk_inventory_movements_purchase_receipt_item_id", "inventory_movements", "purchase_receipt_items", ["purchase_receipt_item_id"], ["id"], source_schema="inventory", referent_schema="purchasing", ondelete="RESTRICT")
    op.create_foreign_key("fk_inventory_movements_stock_adjustment_id", "inventory_movements", "stock_adjustments", ["stock_adjustment_id"], ["id"], source_schema="inventory", referent_schema="inventory", ondelete="RESTRICT")

    op.drop_constraint("chk_inventory_movements_mov_type_enum", "inventory_movements", schema="inventory", type_="check")
    op.drop_constraint("chk_inventory_movements_mov_source_doc_type_enum", "inventory_movements", schema="inventory", type_="check")
    op.drop_constraint("chk_inventory_movements_mov_opening_source_required", "inventory_movements", schema="inventory", type_="check")

    op.create_check_constraint(
        "chk_inventory_movements_mov_one_item",
        "inventory_movements",
        "(item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL') AND material_id IS NOT NULL AND pack_size_id IS NULL) OR (item_category = 'FINISHED_GOOD' AND pack_size_id IS NOT NULL AND material_id IS NULL)",
        schema="inventory",
    )
    op.create_check_constraint(
        "chk_inventory_movements_mov_type_enum",
        "inventory_movements",
        "movement_type IN ('OPENING','PURCHASE_IN','PROD_ISSUE_OUT','PACKAGING_DAMAGE_OUT','PROD_OUTPUT_IN','PROD_RETURN_IN','DISPATCH_OUT','CREDIT_RETURN_IN','SUPPLIER_RETURN','DAMAGE_WASTAGE','ADJUSTMENT')",
        schema="inventory",
    )
    op.create_check_constraint(
        "chk_inventory_movements_mov_source_doc_type_enum",
        "inventory_movements",
        "source_doc_type IN ('OPENING_BALANCE','PURCHASE_RECEIPT','PRODUCTION_RUN','DISPATCH','CREDIT_NOTE','STOCK_ADJUSTMENT','SUPPLIER_RETURN')",
        schema="inventory",
    )
    op.create_check_constraint(
        "chk_inventory_movements_mov_source_required",
        "inventory_movements",
        "(source_doc_type = 'OPENING_BALANCE' AND opening_balance_id IS NOT NULL) OR "
        "(source_doc_type = 'PURCHASE_RECEIPT' AND purchase_receipt_item_id IS NOT NULL) OR "
        "(source_doc_type IN ('STOCK_ADJUSTMENT', 'SUPPLIER_RETURN') AND stock_adjustment_id IS NOT NULL) OR "
        "source_doc_type IN ('PRODUCTION_RUN', 'DISPATCH', 'CREDIT_NOTE')",
        schema="inventory",
    )
    op.create_check_constraint(
        "chk_inventory_movements_mov_sign_direction",
        "inventory_movements",
        "(movement_type IN ('OPENING','PURCHASE_IN','PROD_OUTPUT_IN','PROD_RETURN_IN','CREDIT_RETURN_IN') AND signed_qty_base > 0) OR "
        "(movement_type IN ('PROD_ISSUE_OUT','PACKAGING_DAMAGE_OUT','DISPATCH_OUT','SUPPLIER_RETURN','DAMAGE_WASTAGE') AND signed_qty_base < 0) OR "
        "(movement_type = 'ADJUSTMENT' AND signed_qty_base <> 0)",
        schema="inventory",
    )
    op.create_index("idx_mov_material_time", "inventory_movements", ["material_id", sa.text("occurred_at ASC"), sa.text("id ASC")], unique=False, schema="inventory", postgresql_where=sa.text("material_id IS NOT NULL"))

    # Update balance sync trigger to maintain BOTH finished goods AND raw/packaging materials atomically
    op.execute(
        """
        CREATE OR REPLACE FUNCTION inventory.fn_sync_balance_from_movement()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.pack_size_id IS NOT NULL THEN
                INSERT INTO inventory.inventory_balances (item_category, pack_size_id, on_hand_qty_base, reserved_qty_base)
                VALUES (NEW.item_category, NEW.pack_size_id, 0, 0)
                ON CONFLICT (pack_size_id) WHERE pack_size_id IS NOT NULL DO NOTHING;

                UPDATE inventory.inventory_balances
                SET on_hand_qty_base = on_hand_qty_base + NEW.signed_qty_base,
                    updated_at = NOW()
                WHERE pack_size_id = NEW.pack_size_id;
            ELSIF NEW.material_id IS NOT NULL THEN
                INSERT INTO inventory.inventory_balances (item_category, material_id, on_hand_qty_base, reserved_qty_base)
                VALUES (NEW.item_category, NEW.material_id, 0, 0)
                ON CONFLICT (material_id) WHERE material_id IS NOT NULL DO NOTHING;

                UPDATE inventory.inventory_balances
                SET on_hand_qty_base = on_hand_qty_base + NEW.signed_qty_base,
                    updated_at = NOW()
                WHERE material_id = NEW.material_id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION inventory.fn_sync_balance_from_movement()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.pack_size_id IS NOT NULL THEN
                INSERT INTO inventory.inventory_balances (item_category, pack_size_id, on_hand_qty_base, reserved_qty_base)
                VALUES (NEW.item_category, NEW.pack_size_id, NEW.signed_qty_base, 0)
                ON CONFLICT (pack_size_id) WHERE pack_size_id IS NOT NULL
                DO UPDATE SET
                    on_hand_qty_base = inventory.inventory_balances.on_hand_qty_base + NEW.signed_qty_base,
                    updated_at = NOW();
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.drop_index("idx_mov_material_time", table_name="inventory_movements", schema="inventory")
    op.drop_constraint("chk_inventory_movements_mov_sign_direction", "inventory_movements", schema="inventory", type_="check")
    op.drop_constraint("chk_inventory_movements_mov_source_required", "inventory_movements", schema="inventory", type_="check")
    op.drop_constraint("chk_inventory_movements_mov_source_doc_type_enum", "inventory_movements", schema="inventory", type_="check")
    op.drop_constraint("chk_inventory_movements_mov_type_enum", "inventory_movements", schema="inventory", type_="check")
    op.drop_constraint("chk_inventory_movements_mov_one_item", "inventory_movements", schema="inventory", type_="check")

    op.create_check_constraint(
        "chk_inventory_movements_mov_type_enum",
        "inventory_movements",
        "movement_type IN ('OPENING','PURCHASE_IN','PROD_ISSUE_OUT','PACKAGING_DAMAGE_OUT','PROD_OUTPUT_IN','PROD_RETURN_IN','DISPATCH_OUT','CREDIT_RETURN_IN','ADJUSTMENT')",
        schema="inventory",
    )
    op.create_check_constraint(
        "chk_inventory_movements_mov_source_doc_type_enum",
        "inventory_movements",
        "source_doc_type IN ('OPENING_BALANCE','PURCHASE_RECEIPT','PRODUCTION_RUN','DISPATCH','CREDIT_NOTE','STOCK_ADJUSTMENT')",
        schema="inventory",
    )
    op.create_check_constraint(
        "chk_inventory_movements_mov_opening_source_required",
        "inventory_movements",
        "(source_doc_type = 'OPENING_BALANCE' AND opening_balance_id IS NOT NULL) OR (source_doc_type <> 'OPENING_BALANCE')",
        schema="inventory",
    )

    op.drop_constraint("fk_inventory_movements_stock_adjustment_id", "inventory_movements", schema="inventory", type_="foreignkey")
    op.drop_constraint("fk_inventory_movements_purchase_receipt_item_id", "inventory_movements", schema="inventory", type_="foreignkey")
    op.drop_constraint("fk_inventory_movements_material_id_materials", "inventory_movements", schema="inventory", type_="foreignkey")
    op.drop_column("inventory_movements", "stock_adjustment_id", schema="inventory")
    op.drop_column("inventory_movements", "purchase_receipt_item_id", schema="inventory")
    op.drop_column("inventory_movements", "notes", schema="inventory")
    op.drop_column("inventory_movements", "reference_code", schema="inventory")
    op.drop_column("inventory_movements", "entered_uom", schema="inventory")
    op.drop_column("inventory_movements", "entered_qty", schema="inventory")
    op.drop_column("inventory_movements", "material_id", schema="inventory")

    op.drop_index("uq_bal_material", table_name="inventory_balances", schema="inventory")
    op.drop_constraint("chk_inventory_balances_bal_one_item", "inventory_balances", schema="inventory", type_="check")
    op.drop_constraint("fk_inventory_balances_material_id_materials", "inventory_balances", schema="inventory", type_="foreignkey")
    op.drop_column("inventory_balances", "material_id", schema="inventory")

    op.drop_index("uq_ob_batch_material", table_name="opening_balances", schema="inventory")
    op.drop_constraint("chk_opening_balances_ob_one_item", "opening_balances", schema="inventory", type_="check")
    op.drop_constraint("fk_opening_balances_material_id_materials", "opening_balances", schema="inventory", type_="foreignkey")
    op.drop_column("opening_balances", "material_id", schema="inventory")

    op.drop_table("stock_adjustments", schema="inventory")
    op.drop_index("idx_lots_fg_fefo", table_name="cost_lots", schema="inventory")
    op.drop_index("idx_lots_fifo_open", table_name="cost_lots", schema="inventory")
    op.drop_table("cost_lots", schema="inventory")

    op.drop_table("purchase_receipt_items", schema="purchasing")
    op.drop_index("idx_pr_po", table_name="purchase_receipts", schema="purchasing")
    op.drop_index("idx_pr_supplier_date", table_name="purchase_receipts", schema="purchasing")
    op.drop_table("purchase_receipts", schema="purchasing")
    op.drop_table("purchase_order_items", schema="purchasing")
    op.drop_index("idx_po_supplier_date", table_name="purchase_orders", schema="purchasing")
    op.drop_table("purchase_orders", schema="purchasing")
    op.drop_index("idx_suppliers_active_name", table_name="suppliers", schema="purchasing")
    op.drop_table("suppliers", schema="purchasing")

    op.drop_table("unit_conversions", schema="production")
    op.drop_table("materials", schema="production")
    op.execute("DROP SCHEMA IF EXISTS purchasing")
    op.execute("DROP SCHEMA IF EXISTS production")
