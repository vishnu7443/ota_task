"""Phase 4 foundation, IAM, sales masters, orders vertical slice, and opening FG inventory

Revision ID: 0001_phase4_foundation
Revises:
Create Date: 2026-11-25 09:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_phase4_foundation"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS iam")
    op.execute("CREATE SCHEMA IF NOT EXISTS sales")
    op.execute("CREATE SCHEMA IF NOT EXISTS inventory")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")

    # --- IAM ---
    op.create_table(
        "company_profiles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=False),
        sa.Column("gstin", sa.String(length=15), nullable=False),
        sa.Column("state_name", sa.String(length=80), nullable=False),
        sa.Column("state_code", sa.String(length=2), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("variance_tolerance_pct", sa.Numeric(5, 2), server_default="3.00", nullable=False),
        sa.Column("valuation_method", sa.String(length=24), server_default="FIFO", nullable=False),
        sa.Column("is_singleton", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'",
            name="chk_company_profiles_gstin_format",
        ),
        sa.CheckConstraint("state_code ~ '^[0-9]{2}$'", name="chk_company_profiles_state_code_format"),
        sa.CheckConstraint("variance_tolerance_pct >= 0", name="chk_company_profiles_tolerance_non_negative"),
        sa.CheckConstraint(
            "valuation_method IN ('FIFO', 'WEIGHTED_AVERAGE', 'LAST_PRICE')",
            name="chk_company_profiles_valuation_method_enum",
        ),
        sa.CheckConstraint("is_singleton IS TRUE", name="chk_company_profiles_singleton_true"),
        sa.PrimaryKeyConstraint("id", name="pk_company_profiles"),
        sa.UniqueConstraint("is_singleton", name="uq_company_profiles_singleton"),
        schema="iam",
    )

    op.create_table(
        "roles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "code IN ('SALESMAN', 'FACTORY_ADMIN', 'PRODUCTION_SUPERVISOR', 'ACCOUNTANT_AUDITOR', 'OWNER')",
            name="chk_roles_role_code_enum",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("code", name="uq_roles_code"),
        schema="iam",
    )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["iam.roles.id"], name="fk_users_role_id_roles", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("phone", name="uq_users_phone"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        schema="iam",
    )
    op.create_index("idx_users_role_active", "users", ["role_id", "is_active"], unique=False, schema="iam")

    # --- SALES MASTERS ---
    op.create_table(
        "salesman_profiles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("employee_code", sa.String(length=32), nullable=False),
        sa.Column("territory", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["iam.users.id"], name="fk_salesman_profiles_user_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_salesman_profiles"),
        sa.UniqueConstraint("employee_code", name="uq_salesman_profiles_employee_code"),
        sa.UniqueConstraint("user_id", name="uq_salesman_profiles_user_id"),
        schema="sales",
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("customer_type", sa.String(length=20), nullable=False),
        sa.Column("gstin", sa.String(length=15), nullable=True),
        sa.Column("primary_state_name", sa.String(length=80), nullable=False),
        sa.Column("primary_state_code", sa.String(length=2), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("assigned_salesman_id", sa.BigInteger(), nullable=True),
        sa.Column("credit_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("customer_type IN ('RETAILER', 'DISTRIBUTOR')", name="chk_customers_customer_type_enum"),
        sa.CheckConstraint(
            "gstin IS NULL OR gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'",
            name="chk_customers_gstin_format",
        ),
        sa.CheckConstraint("primary_state_code ~ '^[0-9]{2}$'", name="chk_customers_state_code_format"),
        sa.CheckConstraint(
            "gstin IS NULL OR SUBSTRING(gstin FROM 1 FOR 2) = primary_state_code",
            name="chk_customers_gstin_matches_state",
        ),
        sa.CheckConstraint("credit_days >= 0", name="chk_customers_credit_days_non_negative"),
        sa.ForeignKeyConstraint(
            ["assigned_salesman_id"], ["iam.users.id"], name="fk_customers_assigned_salesman_id_users", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_customers"),
        sa.UniqueConstraint("code", name="uq_customers_code"),
        schema="sales",
    )
    op.create_index("idx_customers_salesman_active", "customers", ["assigned_salesman_id", "is_active"], unique=False, schema="sales")

    op.create_table(
        "customer_addresses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("address_type", sa.String(length=16), nullable=False),
        sa.Column("line1", sa.String(length=200), nullable=False),
        sa.Column("line2", sa.String(length=200), nullable=True),
        sa.Column("city", sa.String(length=80), nullable=False),
        sa.Column("state_name", sa.String(length=80), nullable=False),
        sa.Column("state_code", sa.String(length=2), nullable=False),
        sa.Column("pincode", sa.String(length=6), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.CheckConstraint("address_type IN ('BILLING', 'SHIPPING')", name="chk_customer_addresses_address_type_enum"),
        sa.CheckConstraint("state_code ~ '^[0-9]{2}$'", name="chk_customer_addresses_addr_state_code_format"),
        sa.CheckConstraint("pincode ~ '^[0-9]{6}$'", name="chk_customer_addresses_addr_pincode_format"),
        sa.ForeignKeyConstraint(["customer_id"], ["sales.customers.id"], name="fk_customer_addresses_customer_id_customers", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_customer_addresses"),
        schema="sales",
    )
    op.create_index(
        "uq_cust_addr_default",
        "customer_addresses",
        ["customer_id", "address_type"],
        unique=True,
        schema="sales",
        postgresql_where=sa.text("is_default IS TRUE"),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("hsn_code", sa.String(length=12), nullable=False),
        sa.Column("gst_rate_bps", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.CheckConstraint("hsn_code ~ '^[0-9]{4,8}$'", name="chk_products_hsn_format"),
        sa.CheckConstraint(
            "gst_rate_bps >= 0 AND gst_rate_bps <= 2800 AND gst_rate_bps % 2 = 0",
            name="chk_products_gst_rate_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("product_code", name="uq_products_product_code"),
        schema="sales",
    )

    op.create_table(
        "pack_sizes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_code", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=140), nullable=False),
        sa.Column("pack_weight_g", sa.Integer(), nullable=False),
        sa.Column("packets_per_carton", sa.Integer(), nullable=False),
        sa.Column("base_selling_price_paisa", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.CheckConstraint("pack_weight_g > 0", name="chk_pack_sizes_pack_weight_positive"),
        sa.CheckConstraint("packets_per_carton > 0", name="chk_pack_sizes_carton_ratio_positive"),
        sa.CheckConstraint("base_selling_price_paisa >= 0", name="chk_pack_sizes_base_price_non_negative"),
        sa.ForeignKeyConstraint(["product_id"], ["sales.products.id"], name="fk_pack_sizes_product_id_products", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_pack_sizes"),
        sa.UniqueConstraint("product_id", "pack_weight_g", name="uq_pack_sizes_product_weight"),
        sa.UniqueConstraint("sku_code", name="uq_pack_sizes_sku_code"),
        schema="sales",
    )

    op.create_table(
        "price_lists",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.CheckConstraint("NOT (is_default AND customer_id IS NOT NULL)", name="chk_price_lists_default_not_customer_specific"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="chk_price_lists_valid_date_window"),
        sa.ForeignKeyConstraint(["customer_id"], ["sales.customers.id"], name="fk_price_lists_customer_id_customers", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_price_lists"),
        schema="sales",
    )
    op.create_index(
        "uq_pricelist_single_default",
        "price_lists",
        ["is_default"],
        unique=True,
        schema="sales",
        postgresql_where=sa.text("is_default IS TRUE AND is_active IS TRUE"),
    )

    op.create_table(
        "price_list_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("price_list_id", sa.BigInteger(), nullable=False),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=False),
        sa.Column("unit_price_paisa", sa.BigInteger(), nullable=False),
        sa.Column("min_qty", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("unit_price_paisa >= 0", name="chk_price_list_items_unit_price_non_negative"),
        sa.CheckConstraint("min_qty >= 1", name="chk_price_list_items_min_qty_positive"),
        sa.ForeignKeyConstraint(["pack_size_id"], ["sales.pack_sizes.id"], name="fk_price_list_items_pack_size_id_pack_sizes", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["price_list_id"], ["sales.price_lists.id"], name="fk_price_list_items_price_list_id_price_lists", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_price_list_items"),
        sa.UniqueConstraint("price_list_id", "pack_size_id", "min_qty", name="uq_pli_list_sku_qty"),
        schema="sales",
    )

    # --- ORDERS ---
    op.create_table(
        "sales_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_number", sa.String(length=32), nullable=False),
        sa.Column("client_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("salesman_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("shipping_address_id", sa.BigInteger(), nullable=True),
        sa.Column("place_of_supply_state_code", sa.String(length=2), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=28), nullable=False),
        sa.Column("has_shortage", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("place_of_supply_state_code ~ '^[0-9]{2}$'", name="chk_sales_orders_pos_state_format"),
        sa.CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','UNDER_REVIEW','CORRECTION_REQUESTED',"
            "'APPROVED','REJECTED','INVOICED','PARTIALLY_DISPATCHED','DISPATCHED','CANCELLED')",
            name="chk_sales_orders_order_status_enum",
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["iam.users.id"], name="fk_sales_orders_approved_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["sales.customers.id"], name="fk_sales_orders_customer_id_customers", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["salesman_id"], ["iam.users.id"], name="fk_sales_orders_salesman_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["shipping_address_id"], ["sales.customer_addresses.id"], name="fk_sales_orders_shipping_address_id_customer_addresses", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_sales_orders"),
        sa.UniqueConstraint("order_number", name="uq_sales_orders_order_number"),
        sa.UniqueConstraint("salesman_id", "client_order_id", name="uq_sales_orders_idempotency"),
        schema="sales",
    )
    op.create_index("idx_orders_salesman_date", "sales_orders", ["salesman_id", sa.text("order_date DESC"), sa.text("id DESC")], unique=False, schema="sales")
    op.create_index(
        "idx_orders_pending_queue",
        "sales_orders",
        ["status", sa.text("created_at ASC")],
        unique=False,
        schema="sales",
        postgresql_where=sa.text("status IN ('SUBMITTED','UNDER_REVIEW','CORRECTION_REQUESTED','APPROVED','INVOICED')"),
    )

    op.create_table(
        "sales_order_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=False),
        sa.Column("ordered_qty_pkts", sa.Integer(), nullable=False),
        sa.Column("approved_qty_pkts", sa.Integer(), nullable=True),
        sa.Column("unit_price_paisa", sa.BigInteger(), nullable=False),
        sa.Column(
            "line_taxable_paisa",
            sa.BigInteger(),
            sa.Computed("COALESCE(approved_qty_pkts, ordered_qty_pkts)::bigint * unit_price_paisa", persisted=True),
            nullable=False,
        ),
        sa.CheckConstraint("ordered_qty_pkts > 0", name="chk_sales_order_items_ordered_qty_positive"),
        sa.CheckConstraint("approved_qty_pkts IS NULL OR approved_qty_pkts >= 0", name="chk_sales_order_items_approved_qty_non_negative"),
        sa.CheckConstraint("unit_price_paisa >= 0", name="chk_sales_order_items_unit_price_non_negative"),
        sa.ForeignKeyConstraint(["pack_size_id"], ["sales.pack_sizes.id"], name="fk_sales_order_items_pack_size_id_pack_sizes", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales.sales_orders.id"], name="fk_sales_order_items_sales_order_id_sales_orders", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_sales_order_items"),
        sa.UniqueConstraint("sales_order_id", "pack_size_id", name="uq_soi_order_sku"),
        schema="sales",
    )

    op.create_table(
        "sales_order_status_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
        sa.Column("from_status", sa.String(length=28), nullable=True),
        sa.Column("to_status", sa.String(length=28), nullable=False),
        sa.Column("changed_by", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["changed_by"], ["iam.users.id"], name="fk_sales_order_status_history_changed_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales.sales_orders.id"], name="fk_sales_order_status_history_sales_order_id_sales_orders", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_sales_order_status_history"),
        schema="sales",
    )
    op.create_index("idx_osh_order_time", "sales_order_status_history", ["sales_order_id", "changed_at"], unique=False, schema="sales")

    op.create_table(
        "sales_order_approvals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=False),
        sa.Column("decision", sa.String(length=28), nullable=False),
        sa.Column("ordered_total_pkts", sa.Integer(), nullable=False),
        sa.Column("available_total_pkts", sa.Integer(), nullable=False),
        sa.Column("shortage_pkts", sa.Integer(), nullable=False),
        sa.Column("stock_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "decision IN ('APPROVED', 'REJECTED', 'CORRECTION_REQUESTED', 'HELD_SHORTAGE', 'PENDING_REVIEW')",
            name="chk_sales_order_approvals_approval_decision_enum",
        ),
        sa.CheckConstraint("ordered_total_pkts > 0", name="chk_sales_order_approvals_ordered_total_positive"),
        sa.CheckConstraint("available_total_pkts >= 0", name="chk_sales_order_approvals_available_total_non_negative"),
        sa.CheckConstraint("shortage_pkts >= 0", name="chk_sales_order_approvals_shortage_non_negative"),
        sa.CheckConstraint("NOT (decision = 'APPROVED' AND shortage_pkts > 0)", name="chk_sales_order_approvals_no_approve_with_shortage"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["iam.users.id"], name="fk_sales_order_approvals_reviewed_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales.sales_orders.id"], name="fk_sales_order_approvals_sales_order_id_sales_orders", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_sales_order_approvals"),
        schema="sales",
    )

    # --- INVENTORY (PHASE 4 OPENING & FG BALANCE LEDGER SUBSET) ---
    op.create_table(
        "opening_balances",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_ref", sa.String(length=40), nullable=False),
        sa.Column("item_category", sa.String(length=20), nullable=False),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=True),
        sa.Column("opening_qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_cost_paisa_per_base", sa.Numeric(18, 6), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL', 'FINISHED_GOOD')", name="chk_opening_balances_ob_item_category_enum"),
        sa.CheckConstraint("opening_qty_base > 0", name="chk_opening_balances_ob_qty_positive"),
        sa.CheckConstraint("unit_cost_paisa_per_base >= 0", name="chk_opening_balances_ob_cost_non_negative"),
        sa.ForeignKeyConstraint(["created_by"], ["iam.users.id"], name="fk_opening_balances_created_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pack_size_id"], ["sales.pack_sizes.id"], name="fk_opening_balances_pack_size_id_pack_sizes", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_opening_balances"),
        schema="inventory",
    )
    op.create_index(
        "uq_ob_batch_pack_size",
        "opening_balances",
        ["batch_ref", "pack_size_id"],
        unique=True,
        schema="inventory",
        postgresql_where=sa.text("pack_size_id IS NOT NULL"),
    )

    op.create_table(
        "inventory_balances",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("item_category", sa.String(length=20), nullable=False),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=True),
        sa.Column("on_hand_qty_base", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("reserved_qty_base", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("available_qty_base", sa.Numeric(18, 3), sa.Computed("on_hand_qty_base - reserved_qty_base", persisted=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL', 'FINISHED_GOOD')", name="chk_inventory_balances_bal_item_category_enum"),
        sa.CheckConstraint("on_hand_qty_base >= 0", name="chk_inventory_balances_bal_on_hand_non_negative"),
        sa.CheckConstraint("reserved_qty_base >= 0", name="chk_inventory_balances_bal_reserved_non_negative"),
        sa.CheckConstraint("reserved_qty_base <= on_hand_qty_base", name="chk_inventory_balances_bal_reserved_cap"),
        sa.ForeignKeyConstraint(["pack_size_id"], ["sales.pack_sizes.id"], name="fk_inventory_balances_pack_size_id_pack_sizes", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_balances"),
        schema="inventory",
    )
    op.create_index(
        "uq_bal_pack_size",
        "inventory_balances",
        ["pack_size_id"],
        unique=True,
        schema="inventory",
        postgresql_where=sa.text("pack_size_id IS NOT NULL"),
    )

    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("item_category", sa.String(length=20), nullable=False),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=True),
        sa.Column("movement_type", sa.String(length=28), nullable=False),
        sa.Column("signed_qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_cost_paisa_per_base", sa.Numeric(18, 6), nullable=False),
        sa.Column("total_cost_paisa", sa.BigInteger(), nullable=False),
        sa.Column("source_doc_type", sa.String(length=24), nullable=False),
        sa.Column("opening_balance_id", sa.BigInteger(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("item_category IN ('RAW_MATERIAL', 'PACKAGING_MATERIAL', 'FINISHED_GOOD')", name="chk_inventory_movements_mov_item_category_enum"),
        sa.CheckConstraint(
            "movement_type IN ('OPENING','PURCHASE_IN','PROD_ISSUE_OUT','PACKAGING_DAMAGE_OUT',"
            "'PROD_OUTPUT_IN','PROD_RETURN_IN','DISPATCH_OUT','CREDIT_RETURN_IN','ADJUSTMENT')",
            name="chk_inventory_movements_mov_type_enum",
        ),
        sa.CheckConstraint("signed_qty_base <> 0", name="chk_inventory_movements_mov_qty_nonzero"),
        sa.CheckConstraint("unit_cost_paisa_per_base >= 0", name="chk_inventory_movements_mov_unit_cost_non_negative"),
        sa.CheckConstraint("total_cost_paisa >= 0", name="chk_inventory_movements_mov_total_cost_non_negative"),
        sa.CheckConstraint(
            "source_doc_type IN ('OPENING_BALANCE','PURCHASE_RECEIPT','PRODUCTION_RUN','DISPATCH','CREDIT_NOTE','STOCK_ADJUSTMENT')",
            name="chk_inventory_movements_mov_source_doc_type_enum",
        ),
        sa.CheckConstraint(
            "(source_doc_type = 'OPENING_BALANCE' AND opening_balance_id IS NOT NULL) OR (source_doc_type <> 'OPENING_BALANCE')",
            name="chk_inventory_movements_mov_opening_source_required",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["iam.users.id"], name="fk_inventory_movements_created_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["opening_balance_id"], ["inventory.opening_balances.id"], name="fk_inventory_movements_opening_balance_id_opening_balances", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pack_size_id"], ["sales.pack_sizes.id"], name="fk_inventory_movements_pack_size_id_pack_sizes", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_movements"),
        schema="inventory",
    )
    op.create_index(
        "idx_mov_pack_time",
        "inventory_movements",
        ["pack_size_id", sa.text("occurred_at ASC"), sa.text("id ASC")],
        unique=False,
        schema="inventory",
        postgresql_where=sa.text("pack_size_id IS NOT NULL"),
    )

    # --- AUDIT ---
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("entity_schema", sa.String(length=32), nullable=False),
        sa.Column("entity_table", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["iam.users.id"], name="fk_audit_logs_actor_user_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
        schema="audit",
    )
    op.create_index("idx_audit_entity_time", "audit_logs", ["entity_table", "entity_id", sa.text("occurred_at DESC")], unique=False, schema="audit")
    op.create_index("idx_audit_actor_time", "audit_logs", ["actor_user_id", sa.text("occurred_at DESC")], unique=False, schema="audit")

    # --- POSTGRESQL IMMUTABILITY & LEDGER BALANCE SYNC TRIGGERS ---
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit.fn_prevent_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Table %.% is append-only; updates and deletes are forbidden.', TG_TABLE_SCHEMA, TG_TABLE_NAME
                USING ERRCODE = '42501';
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_inventory_movements_append_only
        BEFORE UPDATE OR DELETE ON inventory.inventory_movements
        FOR EACH ROW EXECUTE FUNCTION audit.fn_prevent_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit.audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit.fn_prevent_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_order_status_history_append_only
        BEFORE UPDATE OR DELETE ON sales.sales_order_status_history
        FOR EACH ROW EXECUTE FUNCTION audit.fn_prevent_mutation();
        """
    )

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

    op.execute(
        """
        CREATE TRIGGER trg_sync_inventory_balance
        AFTER INSERT ON inventory.inventory_movements
        FOR EACH ROW EXECUTE FUNCTION inventory.fn_sync_balance_from_movement();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_sync_inventory_balance ON inventory.inventory_movements")
    op.execute("DROP FUNCTION IF EXISTS inventory.fn_sync_balance_from_movement()")
    op.execute("DROP TRIGGER IF EXISTS trg_order_status_history_append_only ON sales.sales_order_status_history")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit.audit_logs")
    op.execute("DROP TRIGGER IF EXISTS trg_inventory_movements_append_only ON inventory.inventory_movements")
    op.execute("DROP FUNCTION IF EXISTS audit.fn_prevent_mutation()")

    op.drop_table("audit_logs", schema="audit")
    op.drop_table("inventory_movements", schema="inventory")
    op.drop_table("inventory_balances", schema="inventory")
    op.drop_table("opening_balances", schema="inventory")
    op.drop_table("sales_order_approvals", schema="sales")
    op.drop_table("sales_order_status_history", schema="sales")
    op.drop_table("sales_order_items", schema="sales")
    op.drop_table("sales_orders", schema="sales")
    op.drop_table("price_list_items", schema="sales")
    op.drop_table("price_lists", schema="sales")
    op.drop_table("pack_sizes", schema="sales")
    op.drop_table("products", schema="sales")
    op.drop_table("customer_addresses", schema="sales")
    op.drop_table("customers", schema="sales")
    op.drop_table("salesman_profiles", schema="sales")
    op.drop_table("users", schema="iam")
    op.drop_table("roles", schema="iam")
    op.drop_table("company_profiles", schema="iam")

    op.execute("DROP SCHEMA IF EXISTS audit")
    op.execute("DROP SCHEMA IF EXISTS inventory")
    op.execute("DROP SCHEMA IF EXISTS sales")
    op.execute("DROP SCHEMA IF EXISTS iam")
