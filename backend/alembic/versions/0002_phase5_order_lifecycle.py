"""Phase 5 order lifecycle metadata, price auditability, history guard, and stock reservations

Revision ID: 0002_phase5_order_lifecycle
Revises: 0001_phase4_foundation
Create Date: 2026-11-25 10:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase5_order_lifecycle"
down_revision: str | Sequence[str] | None = "0001_phase4_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Sales order admin/rejection/cancellation audit metadata + version lock
    op.add_column("sales_orders", sa.Column("admin_remarks", sa.Text(), nullable=True), schema="sales")
    op.add_column("sales_orders", sa.Column("rejected_by", sa.BigInteger(), nullable=True), schema="sales")
    op.add_column(
        "sales_orders",
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        schema="sales",
    )
    op.add_column("sales_orders", sa.Column("rejection_reason", sa.Text(), nullable=True), schema="sales")
    op.add_column("sales_orders", sa.Column("cancelled_by", sa.BigInteger(), nullable=True), schema="sales")
    op.add_column(
        "sales_orders",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        schema="sales",
    )
    op.add_column("sales_orders", sa.Column("cancellation_reason", sa.Text(), nullable=True), schema="sales")
    op.add_column(
        "sales_orders",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        schema="sales",
    )
    op.create_foreign_key(
        "fk_sales_orders_rejected_by_users",
        "sales_orders",
        "users",
        ["rejected_by"],
        ["id"],
        source_schema="sales",
        referent_schema="iam",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_sales_orders_cancelled_by_users",
        "sales_orders",
        "users",
        ["cancelled_by"],
        ["id"],
        source_schema="sales",
        referent_schema="iam",
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "chk_sales_orders_version_positive",
        "sales_orders",
        "version >= 1",
        schema="sales",
    )
    op.create_index(
        "idx_orders_admin_date",
        "sales_orders",
        [sa.text("order_date DESC"), sa.text("id DESC")],
        unique=False,
        schema="sales",
    )
    op.create_index(
        "idx_orders_customer_date",
        "sales_orders",
        ["customer_id", sa.text("order_date DESC"), sa.text("id DESC")],
        unique=False,
        schema="sales",
    )

    # 2. Preserve original price-list unit price even when Admin overrides unit_price_paisa
    op.add_column(
        "sales_order_items",
        sa.Column("original_unit_price_paisa", sa.BigInteger(), nullable=True),
        schema="sales",
    )
    op.execute(
        "UPDATE sales.sales_order_items SET original_unit_price_paisa = unit_price_paisa "
        "WHERE original_unit_price_paisa IS NULL"
    )
    op.alter_column(
        "sales_order_items",
        "original_unit_price_paisa",
        existing_type=sa.BigInteger(),
        nullable=False,
        schema="sales",
    )
    op.create_check_constraint(
        "chk_sales_order_items_orig_price_non_negative",
        "sales_order_items",
        "original_unit_price_paisa >= 0",
        schema="sales",
    )

    # 3. Forbid duplicate no-op status transitions at PostgreSQL constraint level
    op.create_check_constraint(
        "chk_sales_order_status_history_no_noop_transition",
        "sales_order_status_history",
        "from_status IS DISTINCT FROM to_status",
        schema="sales",
    )

    # 4. Expand approval decision enum cleanly to allow CANCELLED audit snapshot
    op.drop_constraint(
        "chk_sales_order_approvals_approval_decision_enum",
        "sales_order_approvals",
        schema="sales",
        type_="check",
    )
    op.create_check_constraint(
        "chk_sales_order_approvals_approval_decision_enum",
        "sales_order_approvals",
        "decision IN ('APPROVED', 'REJECTED', 'CORRECTION_REQUESTED', 'HELD_SHORTAGE', 'PENDING_REVIEW', 'CANCELLED')",
        schema="sales",
    )

    # 5. Per-order-item stock reservation traceability table
    op.create_table(
        "stock_reservations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
        sa.Column("sales_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=False),
        sa.Column("reserved_qty_pkts", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reserved_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "reserved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("released_by", sa.BigInteger(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("reserved_qty_pkts > 0", name="chk_stock_reservations_qty_positive"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'RELEASED', 'FULFILLED')",
            name="chk_stock_reservations_status_enum",
        ),
        sa.ForeignKeyConstraint(
            ["pack_size_id"],
            ["sales.pack_sizes.id"],
            name="fk_stock_reservations_pack_size_id_pack_sizes",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["released_by"],
            ["iam.users.id"],
            name="fk_stock_reservations_released_by_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reserved_by"],
            ["iam.users.id"],
            name="fk_stock_reservations_reserved_by_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sales_order_id"],
            ["sales.sales_orders.id"],
            name="fk_stock_reservations_sales_order_id_sales_orders",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sales_order_item_id"],
            ["sales.sales_order_items.id"],
            name="fk_stock_reservations_sales_order_item_id_sales_order_items",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_stock_reservations"),
        schema="inventory",
    )
    op.create_index(
        "uq_stock_res_active_item",
        "stock_reservations",
        ["sales_order_item_id"],
        unique=True,
        schema="inventory",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "idx_stock_res_pack_active",
        "stock_reservations",
        ["pack_size_id"],
        unique=False,
        schema="inventory",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "idx_stock_res_order_status",
        "stock_reservations",
        ["sales_order_id", "status"],
        unique=False,
        schema="inventory",
    )


def downgrade() -> None:
    op.drop_index("idx_stock_res_order_status", table_name="stock_reservations", schema="inventory")
    op.drop_index("idx_stock_res_pack_active", table_name="stock_reservations", schema="inventory")
    op.drop_index("uq_stock_res_active_item", table_name="stock_reservations", schema="inventory")
    op.drop_table("stock_reservations", schema="inventory")

    op.drop_constraint(
        "chk_sales_order_approvals_approval_decision_enum",
        "sales_order_approvals",
        schema="sales",
        type_="check",
    )
    op.create_check_constraint(
        "chk_sales_order_approvals_approval_decision_enum",
        "sales_order_approvals",
        "decision IN ('APPROVED', 'REJECTED', 'CORRECTION_REQUESTED', 'HELD_SHORTAGE', 'PENDING_REVIEW')",
        schema="sales",
    )

    op.drop_constraint(
        "chk_sales_order_status_history_no_noop_transition",
        "sales_order_status_history",
        schema="sales",
        type_="check",
    )

    op.drop_constraint(
        "chk_sales_order_items_orig_price_non_negative",
        "sales_order_items",
        schema="sales",
        type_="check",
    )
    op.drop_column("sales_order_items", "original_unit_price_paisa", schema="sales")

    op.drop_index("idx_orders_customer_date", table_name="sales_orders", schema="sales")
    op.drop_index("idx_orders_admin_date", table_name="sales_orders", schema="sales")
    op.drop_constraint(
        "chk_sales_orders_version_positive",
        "sales_orders",
        schema="sales",
        type_="check",
    )
    op.drop_constraint(
        "fk_sales_orders_cancelled_by_users",
        "sales_orders",
        schema="sales",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_sales_orders_rejected_by_users",
        "sales_orders",
        schema="sales",
        type_="foreignkey",
    )
    op.drop_column("sales_orders", "version", schema="sales")
    op.drop_column("sales_orders", "cancellation_reason", schema="sales")
    op.drop_column("sales_orders", "cancelled_at", schema="sales")
    op.drop_column("sales_orders", "cancelled_by", schema="sales")
    op.drop_column("sales_orders", "rejection_reason", schema="sales")
    op.drop_column("sales_orders", "rejected_at", schema="sales")
    op.drop_column("sales_orders", "rejected_by", schema="sales")
    op.drop_column("sales_orders", "admin_remarks", schema="sales")
