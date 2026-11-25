"""Phase 7 BOM management, BOM versioning triggers, production runs, material issues, outputs, wastages, variances, and ledger/lot extensions.

Revision ID: 0004_phase7_bom_production
Revises: 0003_phase6_purchasing_inv
Create Date: 2026-11-25 13:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase7_bom_production"
down_revision: str | Sequence[str] | None = "0003_phase6_purchasing_inv"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- PRODUCTION BOM & RECIPE TEMPLATES ---
    op.create_table(
        "recipe_templates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("base_yield_weight_g", sa.Numeric(18, 3), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("base_yield_weight_g > 0", name="chk_recipe_templates_rt_yield_pos"),
        sa.ForeignKeyConstraint(["product_id"], ["sales.products.id"], name="fk_recipe_templates_product_id_products", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_recipe_templates"),
        sa.UniqueConstraint("code", name="uq_recipe_templates_code"),
        schema="production",
    )

    op.create_table(
        "bom_headers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=False),
        sa.Column("active_version_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["pack_size_id"], ["sales.pack_sizes.id"], name="fk_bom_headers_pack_size_id_pack_sizes", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_bom_headers"),
        sa.UniqueConstraint("pack_size_id", name="uq_bom_headers_pack_size_id"),
        schema="production",
    )

    op.create_table(
        "bom_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("bom_header_id", sa.BigInteger(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("recipe_template_id", sa.BigInteger(), nullable=True),
        sa.Column("expected_yield_pkts", sa.Integer(), nullable=False),
        sa.Column("batch_multiplier", sa.Numeric(10, 4), server_default="1.0000", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("activated_by", sa.BigInteger(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'SUPERSEDED')", name="chk_bom_versions_bv_status_enum"),
        sa.CheckConstraint("version_no > 0", name="chk_bom_versions_bv_version_pos"),
        sa.CheckConstraint("expected_yield_pkts > 0", name="chk_bom_versions_bv_yield_pos"),
        sa.CheckConstraint("batch_multiplier > 0", name="chk_bom_versions_bv_batch_mult_pos"),
        sa.ForeignKeyConstraint(["activated_by"], ["iam.users.id"], name="fk_bom_versions_activated_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["bom_header_id"], ["production.bom_headers.id"], name="fk_bom_versions_bom_header_id_bom_headers", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["iam.users.id"], name="fk_bom_versions_created_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recipe_template_id"], ["production.recipe_templates.id"], name="fk_bom_versions_recipe_template_id_recipe_templates", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_bom_versions"),
        sa.UniqueConstraint("bom_header_id", "version_no", name="uq_bv_header_version"),
        schema="production",
    )
    op.create_index(
        "uq_bv_active_header",
        "bom_versions",
        ["bom_header_id"],
        unique=True,
        schema="production",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "bom_components",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("bom_version_id", sa.BigInteger(), nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=False),
        sa.Column("input_role", sa.String(length=20), nullable=False),
        sa.Column("std_qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("display_qty", sa.Numeric(18, 3), nullable=False),
        sa.Column("display_uom", sa.String(length=16), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("input_role IN ('COOKING_RAW', 'PACKAGING')", name="chk_bom_components_bc_role_enum"),
        sa.CheckConstraint("std_qty_base > 0", name="chk_bom_components_bc_qty_pos"),
        sa.CheckConstraint("display_qty > 0", name="chk_bom_components_bc_disp_qty_pos"),
        sa.ForeignKeyConstraint(["bom_version_id"], ["production.bom_versions.id"], name="fk_bom_components_bom_version_id_bom_versions", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["material_id"], ["production.materials.id"], name="fk_bom_components_material_id_materials", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_bom_components"),
        sa.UniqueConstraint("bom_version_id", "material_id", name="uq_bc_version_material"),
        schema="production",
    )

    # --- PRODUCTION EXECUTION, MATERIAL ISSUES, OUTPUTS, WASTAGES, VARIANCES ---
    op.create_table(
        "production_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_number", sa.String(length=32), nullable=False),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=False),
        sa.Column("bom_version_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_multiplier", sa.Numeric(10, 4), nullable=False),
        sa.Column("expected_output_pkts", sa.Integer(), nullable=False),
        sa.Column("actual_good_output_pkts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_output_pkts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("planned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supervisor_id", sa.BigInteger(), nullable=False),
        sa.Column("posted_by", sa.BigInteger(), nullable=True),
        sa.Column("quality_remarks", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT','PLANNED','IN_PROGRESS','COMPLETED','POSTED','CANCELLED')", name="chk_production_runs_pr_status_enum"),
        sa.CheckConstraint("batch_multiplier > 0", name="chk_production_runs_pr_batch_mult_pos"),
        sa.CheckConstraint("expected_output_pkts > 0", name="chk_production_runs_pr_expected_pos"),
        sa.CheckConstraint("actual_good_output_pkts >= 0", name="chk_production_runs_pr_actual_non_neg"),
        sa.CheckConstraint("rejected_output_pkts >= 0", name="chk_production_runs_pr_rejected_non_neg"),
        sa.CheckConstraint("version >= 1", name="chk_production_runs_pr_version_pos"),
        sa.ForeignKeyConstraint(["bom_version_id"], ["production.bom_versions.id"], name="fk_production_runs_bom_version_id_bom_versions", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pack_size_id"], ["sales.pack_sizes.id"], name="fk_production_runs_pack_size_id_pack_sizes", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by"], ["iam.users.id"], name="fk_production_runs_posted_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supervisor_id"], ["iam.users.id"], name="fk_production_runs_supervisor_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_production_runs"),
        sa.UniqueConstraint("run_number", name="uq_production_runs_run_number"),
        schema="production",
    )
    op.create_index("idx_prun_status_date", "production_runs", ["status", sa.text("run_date DESC"), sa.text("id DESC")], unique=False, schema="production")

    op.create_table(
        "production_material_issues",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("production_run_id", sa.BigInteger(), nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=False),
        sa.Column("issue_phase", sa.String(length=20), nullable=False),
        sa.Column("planned_qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("issued_qty_base", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("actual_consumed_qty_base", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("actual_good_used_base", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("damaged_qty_base", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("returned_unused_qty_base", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("wasted_qty_base", sa.Numeric(18, 3), server_default="0", nullable=False),
        sa.Column("cost_absorbed_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("issued_by", sa.BigInteger(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("issue_phase IN ('RAW_ISSUE', 'PACKAGING_PACK')", name="chk_production_material_issues_pmi_phase_enum"),
        sa.CheckConstraint("planned_qty_base >= 0", name="chk_production_material_issues_pmi_planned_non_neg"),
        sa.CheckConstraint("issued_qty_base >= 0", name="chk_production_material_issues_pmi_issued_non_neg"),
        sa.CheckConstraint("actual_consumed_qty_base >= 0", name="chk_production_material_issues_pmi_consumed_non_neg"),
        sa.CheckConstraint("actual_good_used_base >= 0", name="chk_production_material_issues_pmi_good_non_neg"),
        sa.CheckConstraint("damaged_qty_base >= 0", name="chk_production_material_issues_pmi_damaged_non_neg"),
        sa.CheckConstraint("returned_unused_qty_base >= 0", name="chk_production_material_issues_pmi_returned_non_neg"),
        sa.CheckConstraint("wasted_qty_base >= 0", name="chk_production_material_issues_pmi_wasted_non_neg"),
        sa.CheckConstraint("cost_absorbed_paisa >= 0", name="chk_production_material_issues_pmi_cost_non_neg"),
        sa.ForeignKeyConstraint(["issued_by"], ["iam.users.id"], name="fk_production_material_issues_issued_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["material_id"], ["production.materials.id"], name="fk_production_material_issues_material_id_materials", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_run_id"], ["production.production_runs.id"], name="fk_production_material_issues_production_run_id_prod_a12f", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_production_material_issues"),
        sa.UniqueConstraint("production_run_id", "material_id", "issue_phase", name="uq_pmi_run_mat_phase"),
        schema="production",
    )

    op.create_table(
        "production_outputs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("production_run_id", sa.BigInteger(), nullable=False),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=False),
        sa.Column("good_qty_pkts", sa.Integer(), nullable=False),
        sa.Column("rejected_qty_pkts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batch_code", sa.String(length=40), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("quality_remarks", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.BigInteger(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("good_qty_pkts >= 0", name="chk_production_outputs_po_good_qty_non_neg"),
        sa.CheckConstraint("rejected_qty_pkts >= 0", name="chk_production_outputs_po_rej_qty_non_neg"),
        sa.CheckConstraint("good_qty_pkts + rejected_qty_pkts > 0", name="chk_production_outputs_po_total_output_pos"),
        sa.ForeignKeyConstraint(["pack_size_id"], ["sales.pack_sizes.id"], name="fk_production_outputs_pack_size_id_pack_sizes", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_run_id"], ["production.production_runs.id"], name="fk_production_outputs_production_run_id_production_runs", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by"], ["iam.users.id"], name="fk_production_outputs_recorded_by_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_production_outputs"),
        schema="production",
    )

    op.create_table(
        "production_wastages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("production_run_id", sa.BigInteger(), nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=True),
        sa.Column("pack_size_id", sa.BigInteger(), nullable=True),
        sa.Column("wastage_type", sa.String(length=28), nullable=False),
        sa.Column("qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("uom", sa.String(length=16), nullable=False),
        sa.Column("cost_impact_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("recorded_by", sa.BigInteger(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "wastage_type IN ('DAMAGED_PACKAGING','RAW_MATERIAL_WASTAGE','REJECTED_FINISHED_GOOD','COOKING_SCRAP','BURNT_BATCH','SPILLAGE','OTHER')",
            name="chk_production_wastages_pw_type_enum",
        ),
        sa.CheckConstraint("qty_base > 0", name="chk_production_wastages_pw_qty_pos"),
        sa.CheckConstraint("cost_impact_paisa >= 0", name="chk_production_wastages_pw_cost_non_neg"),
        sa.ForeignKeyConstraint(["material_id"], ["production.materials.id"], name="fk_production_wastages_material_id_materials", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pack_size_id"], ["sales.pack_sizes.id"], name="fk_production_wastages_pack_size_id_pack_sizes", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_run_id"], ["production.production_runs.id"], name="fk_production_wastages_production_run_id_production_runs", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by"], ["iam.users.id"], name="fk_production_wastages_recorded_by_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_production_wastages"),
        schema="production",
    )

    op.create_table(
        "production_variances",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("production_run_id", sa.BigInteger(), nullable=False),
        sa.Column("variance_scope", sa.String(length=28), nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=True),
        sa.Column("planned_qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("actual_qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("variance_qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("variance_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("tolerance_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("is_flagged", sa.Boolean(), nullable=False),
        sa.Column("formula_explanation", sa.Text(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "variance_scope IN ('YIELD','RAW_CONSUMPTION','PACKAGING_BATCH_BOM','PACKAGING_OUTPUT_SCALED')",
            name="chk_production_variances_pv_scope_enum",
        ),
        sa.CheckConstraint("planned_qty_base >= 0", name="chk_production_variances_pv_planned_non_neg"),
        sa.CheckConstraint("actual_qty_base >= 0", name="chk_production_variances_pv_actual_non_neg"),
        sa.CheckConstraint("tolerance_pct >= 0", name="chk_production_variances_pv_tolerance_non_neg"),
        sa.ForeignKeyConstraint(["material_id"], ["production.materials.id"], name="fk_production_variances_material_id_materials", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_run_id"], ["production.production_runs.id"], name="fk_production_variances_production_run_id_production_runs", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_production_variances"),
        schema="production",
    )

    # --- AUDIT VARIANCE ALERTS ---
    op.create_table(
        "variance_alerts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("production_run_id", sa.BigInteger(), nullable=False),
        sa.Column("production_variance_id", sa.BigInteger(), nullable=False),
        sa.Column("alert_type", sa.String(length=24), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="OPEN", nullable=False),
        sa.Column("acknowledged_by", sa.BigInteger(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledgement_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "alert_type IN ('YIELD_LOSS', 'YIELD_EXCESS', 'MATERIAL_OVERUSE', 'MATERIAL_UNDERUSE', 'PACKAGING_WASTAGE')",
            name="chk_variance_alerts_va_type_enum",
        ),
        sa.CheckConstraint("status IN ('OPEN', 'ACKNOWLEDGED')", name="chk_variance_alerts_va_status_enum"),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["iam.users.id"], name="fk_variance_alerts_acknowledged_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_run_id"], ["production.production_runs.id"], name="fk_variance_alerts_production_run_id_production_runs", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_variance_id"], ["production.production_variances.id"], name="fk_variance_alerts_production_variance_id_production_va_e4b2", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_variance_alerts"),
        schema="audit",
    )
    op.create_index("idx_va_status_time", "variance_alerts", ["status", sa.text("created_at DESC")], unique=False, schema="audit")

    # --- EXTEND INVENTORY LEDGER & ADD COST LOT CONSUMPTIONS ---
    op.add_column("inventory_movements", sa.Column("production_run_id", sa.BigInteger(), nullable=True), schema="inventory")
    op.create_foreign_key(
        "fk_inventory_movements_production_run_id",
        "inventory_movements",
        "production_runs",
        ["production_run_id"],
        ["id"],
        source_schema="inventory",
        referent_schema="production",
        ondelete="RESTRICT",
    )
    op.create_index(
        "idx_mov_production_run",
        "inventory_movements",
        ["production_run_id"],
        unique=False,
        schema="inventory",
        postgresql_where=sa.text("production_run_id IS NOT NULL"),
    )

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

    op.create_table(
        "cost_lot_consumptions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("inventory_movement_id", sa.BigInteger(), nullable=False),
        sa.Column("cost_lot_id", sa.BigInteger(), nullable=False),
        sa.Column("consumed_qty_base", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_cost_paisa_per_base", sa.Numeric(18, 6), nullable=False),
        sa.Column("cost_paisa", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("consumed_qty_base > 0", name="chk_cost_lot_consumptions_clc_qty_positive"),
        sa.CheckConstraint("unit_cost_paisa_per_base >= 0", name="chk_cost_lot_consumptions_clc_unit_cost_non_neg"),
        sa.CheckConstraint("cost_paisa >= 0", name="chk_cost_lot_consumptions_clc_total_cost_non_neg"),
        sa.ForeignKeyConstraint(["cost_lot_id"], ["inventory.cost_lots.id"], name="fk_cost_lot_consumptions_cost_lot_id_cost_lots", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["inventory_movement_id"], ["inventory.inventory_movements.id"], name="fk_cost_lot_consumptions_inventory_movement_id_inventory_mov", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_cost_lot_consumptions"),
        sa.UniqueConstraint("inventory_movement_id", "cost_lot_id", name="uq_clc_mov_lot"),
        schema="inventory",
    )

    # --- POSTGRESQL IMMUTABILITY TRIGGERS FOR BOM VERSIONS & COMPONENTS ---
    op.execute(
        """
        CREATE OR REPLACE FUNCTION production.fn_protect_bom_version_immutability()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status <> 'DRAFT' THEN
                    RAISE EXCEPTION 'Historical or active BOM version (%) cannot be deleted.', OLD.id USING ERRCODE = '42501';
                END IF;
                RETURN OLD;
            END IF;

            IF OLD.status <> 'DRAFT' THEN
                -- Only permitted mutation on non-DRAFT BOM version is ACTIVE -> SUPERSEDED or SUPERSEDED -> ACTIVE transition metadata
                IF NEW.bom_header_id IS DISTINCT FROM OLD.bom_header_id
                    OR NEW.version_no IS DISTINCT FROM OLD.version_no
                    OR NEW.recipe_template_id IS DISTINCT FROM OLD.recipe_template_id
                    OR NEW.expected_yield_pkts IS DISTINCT FROM OLD.expected_yield_pkts
                    OR NEW.batch_multiplier IS DISTINCT FROM OLD.batch_multiplier
                    OR NEW.effective_date IS DISTINCT FROM OLD.effective_date
                    OR NEW.created_by IS DISTINCT FROM OLD.created_by
                    OR NEW.status = 'DRAFT' THEN
                    RAISE EXCEPTION 'Historical or active BOM version (%) cannot be modified in place; create a new BOM version.', OLD.id USING ERRCODE = '42501';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_bom_version_immutability
        BEFORE UPDATE OR DELETE ON production.bom_versions
        FOR EACH ROW EXECUTE FUNCTION production.fn_protect_bom_version_immutability();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION production.fn_protect_bom_component_immutability()
        RETURNS TRIGGER AS $$
        DECLARE
            v_status VARCHAR(20);
            target_version_id BIGINT;
        BEGIN
            target_version_id := COALESCE(NEW.bom_version_id, OLD.bom_version_id);
            SELECT status INTO v_status FROM production.bom_versions WHERE id = target_version_id;
            IF v_status IS DISTINCT FROM 'DRAFT' THEN
                RAISE EXCEPTION 'Cannot mutate components of BOM version % in status %; create a new BOM version instead.', target_version_id, v_status USING ERRCODE = '42501';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_bom_component_immutability
        BEFORE INSERT OR UPDATE OR DELETE ON production.bom_components
        FOR EACH ROW EXECUTE FUNCTION production.fn_protect_bom_component_immutability();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_bom_component_immutability ON production.bom_components")
    op.execute("DROP FUNCTION IF EXISTS production.fn_protect_bom_component_immutability()")
    op.execute("DROP TRIGGER IF EXISTS trg_bom_version_immutability ON production.bom_versions")
    op.execute("DROP FUNCTION IF EXISTS production.fn_protect_bom_version_immutability()")

    op.drop_table("cost_lot_consumptions", schema="inventory")

    op.drop_constraint("chk_inventory_movements_mov_source_required", "inventory_movements", schema="inventory", type_="check")
    op.create_check_constraint(
        "chk_inventory_movements_mov_source_required",
        "inventory_movements",
        "(source_doc_type = 'OPENING_BALANCE' AND opening_balance_id IS NOT NULL) OR "
        "(source_doc_type = 'PURCHASE_RECEIPT' AND purchase_receipt_item_id IS NOT NULL) OR "
        "(source_doc_type IN ('STOCK_ADJUSTMENT', 'SUPPLIER_RETURN') AND stock_adjustment_id IS NOT NULL) OR "
        "source_doc_type IN ('PRODUCTION_RUN', 'DISPATCH', 'CREDIT_NOTE')",
        schema="inventory",
    )
    op.drop_index("idx_mov_production_run", table_name="inventory_movements", schema="inventory")
    op.drop_constraint("fk_inventory_movements_production_run_id", "inventory_movements", schema="inventory", type_="foreignkey")
    op.drop_column("inventory_movements", "production_run_id", schema="inventory")

    op.drop_index("idx_va_status_time", table_name="variance_alerts", schema="audit")
    op.drop_table("variance_alerts", schema="audit")

    op.drop_table("production_variances", schema="production")
    op.drop_table("production_wastages", schema="production")
    op.drop_table("production_outputs", schema="production")
    op.drop_table("production_material_issues", schema="production")
    op.drop_index("idx_prun_status_date", table_name="production_runs", schema="production")
    op.drop_table("production_runs", schema="production")

    op.drop_table("bom_components", schema="production")
    op.drop_index("uq_bv_active_header", table_name="bom_versions", schema="production")
    op.drop_table("bom_versions", schema="production")
    op.drop_table("bom_headers", schema="production")
    op.drop_table("recipe_templates", schema="production")
