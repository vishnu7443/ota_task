"""Phase 10: Centralized Audit enhancements, Cross-Module Reconciliation & Investigation Workflow.

Revision ID: 0007_phase10_audit_recon
Revises: 0006_phase9_payments_costing
Create Date: 2026-11-25 16:15:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_phase10_audit_recon"
down_revision: Union[str, Sequence[str], None] = "0006_phase9_payments_costing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend billing.fiscal_sequences to generate REC/YYYY-YY/NNNN sequence numbers
    op.execute(
        "ALTER TABLE billing.fiscal_sequences "
        "DROP CONSTRAINT IF EXISTS chk_fiscal_sequences_fs_doc_type_enum, "
        "DROP CONSTRAINT IF EXISTS chk_fiscal_sequences_chk_fiscal_sequences_fs_doc_type_enum"
    )
    op.execute(
        "ALTER TABLE billing.fiscal_sequences "
        "ADD CONSTRAINT chk_fiscal_sequences_fs_doc_type_enum "
        "CHECK (doc_type IN ('INVOICE', 'CREDIT_NOTE', 'DISPATCH', 'PAYMENT', 'REFUND', 'RECONCILIATION'))"
    )

    # 2. Additive correlation/metadata/action indexing extensions on audit.audit_logs
    op.execute("ALTER TABLE audit.audit_logs ALTER COLUMN action TYPE VARCHAR(48)")
    op.add_column("audit_logs", sa.Column("correlation_ref", sa.String(length=64), nullable=True), schema="audit")
    op.add_column(
        "audit_logs",
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="audit",
    )
    op.create_index(
        "idx_audit_action_time",
        "audit_logs",
        ["action", sa.text("occurred_at DESC")],
        unique=False,
        schema="audit",
    )
    op.create_index(
        "idx_audit_correlation_ref",
        "audit_logs",
        ["correlation_ref"],
        unique=False,
        schema="audit",
        postgresql_where=sa.text("correlation_ref IS NOT NULL"),
    )

    # 3. Reconciliation Runs
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_number", sa.String(length=32), nullable=False),
        sa.Column("financial_year", sa.String(length=7), nullable=False),
        sa.Column("domain", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="'IN_PROGRESS'", nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope_filter", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("run_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("summary_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("discrepancy_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("resolved_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_by", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_rerun_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.BigInteger(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closure_notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("financial_year ~ '^[0-9]{4}-[0-9]{2}$'", name="rr_fy_format"),
        sa.CheckConstraint(
            "domain IN ('INVENTORY', 'SALES', 'INVOICE', 'PAYMENT', 'DISPATCH', 'PRODUCTION', 'FULL_SYSTEM')",
            name="rr_domain_enum",
        ),
        sa.CheckConstraint(
            "status IN ('NOT_STARTED', 'IN_PROGRESS', 'RECONCILED', 'DISCREPANCY_FOUND', 'UNDER_REVIEW', 'RESOLVED', 'CLOSED')",
            name="rr_status_enum",
        ),
        sa.CheckConstraint("period_end >= period_start", name="rr_period_order"),
        sa.CheckConstraint("discrepancy_count >= 0 AND resolved_count >= 0", name="rr_counts_non_neg"),
        sa.CheckConstraint("version >= 1", name="rr_version_pos"),
        sa.ForeignKeyConstraint(["closed_by"], ["iam.users.id"], name="fk_rr_closed_by", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["started_by"], ["iam.users.id"], name="fk_rr_started_by", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_reconciliation_runs"),
        sa.UniqueConstraint("run_number", name="uq_reconciliation_runs_run_number"),
        schema="audit",
    )
    op.create_index(
        "uq_recon_active_fingerprint",
        "reconciliation_runs",
        ["run_fingerprint"],
        unique=True,
        schema="audit",
        postgresql_where=sa.text("status IN ('NOT_STARTED', 'IN_PROGRESS', 'DISCREPANCY_FOUND', 'UNDER_REVIEW')"),
    )
    op.create_index(
        "idx_recon_domain_status",
        "reconciliation_runs",
        ["domain", "status", sa.text("started_at DESC")],
        unique=False,
        schema="audit",
    )

    # 4. Reconciliation Discrepancies
    op.create_table(
        "reconciliation_discrepancies",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("reconciliation_run_id", sa.BigInteger(), nullable=False),
        sa.Column("domain", sa.String(length=24), nullable=False),
        sa.Column("discrepancy_code", sa.String(length=48), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="'MEDIUM'", nullable=False),
        sa.Column("entity_schema", sa.String(length=32), nullable=False),
        sa.Column("entity_table", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("entity_ref", sa.String(length=64), nullable=False),
        sa.Column("expected_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actual_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("difference_summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="'OPEN'", nullable=False),
        sa.Column("assigned_to", sa.BigInteger(), nullable=True),
        sa.Column("investigation_notes", sa.Text(), nullable=True),
        sa.Column("proposed_action", sa.Text(), nullable=True),
        sa.Column("corrective_action_type", sa.String(length=32), nullable=True),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolution_ref_table", sa.String(length=64), nullable=True),
        sa.Column("resolution_ref_id", sa.BigInteger(), nullable=True),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "domain IN ('INVENTORY', 'PURCHASING', 'SALES', 'INVOICE', 'GST', 'PAYMENT', 'DISPATCH', 'PRODUCTION')",
            name="rd_domain_enum",
        ),
        sa.CheckConstraint("severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="rd_severity_enum"),
        sa.CheckConstraint(
            "status IN ('OPEN', 'UNDER_REVIEW', 'ACTION_PROPOSED', 'APPROVED', 'RESOLVED', 'CLOSED', 'DISMISSED')",
            name="rd_status_enum",
        ),
        sa.CheckConstraint(
            "corrective_action_type IS NULL OR corrective_action_type IN "
            "('STOCK_ADJUSTMENT', 'ISSUE_INVOICE', 'AR_RECALC_NOTE', 'MANUAL_JOURNAL_NOTE', 'DISPATCH_FOLLOWUP', 'NO_OP_EXPLAINED')",
            name="rd_action_type_enum",
        ),
        sa.CheckConstraint("version >= 1", name="rd_version_pos"),
        sa.ForeignKeyConstraint(["approved_by"], ["iam.users.id"], name="fk_rd_approved_by", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to"], ["iam.users.id"], name="fk_rd_assigned_to", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reconciliation_run_id"],
            ["audit.reconciliation_runs.id"],
            name="fk_rd_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["resolved_by"], ["iam.users.id"], name="fk_rd_resolved_by", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_reconciliation_discrepancies"),
        schema="audit",
    )
    op.create_index(
        "idx_rd_run_status",
        "reconciliation_discrepancies",
        ["reconciliation_run_id", "status"],
        unique=False,
        schema="audit",
    )
    op.create_index(
        "idx_rd_domain_status",
        "reconciliation_discrepancies",
        ["domain", "status"],
        unique=False,
        schema="audit",
    )

    # 5. Append-Only Reconciliation Events History
    op.create_table(
        "reconciliation_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("reconciliation_run_id", sa.BigInteger(), nullable=False),
        sa.Column("discrepancy_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=36), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["iam.users.id"], name="fk_re_actor", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["discrepancy_id"],
            ["audit.reconciliation_discrepancies.id"],
            name="fk_re_disc",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reconciliation_run_id"],
            ["audit.reconciliation_runs.id"],
            name="fk_re_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_reconciliation_events"),
        schema="audit",
    )
    op.create_index(
        "idx_re_run_time",
        "reconciliation_events",
        ["reconciliation_run_id", "occurred_at"],
        unique=False,
        schema="audit",
    )
    op.create_index(
        "idx_re_disc_time",
        "reconciliation_events",
        ["discrepancy_id", "occurred_at"],
        unique=False,
        schema="audit",
    )

    # 6. Immutability Triggers
    op.execute(
        """
        CREATE TRIGGER trg_reconciliation_events_append_only
        BEFORE UPDATE OR DELETE ON audit.reconciliation_events
        FOR EACH ROW EXECUTE FUNCTION audit.fn_prevent_mutation();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit.fn_protect_reconciliation_run_immutability()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Reconciliation run (%) cannot be deleted.', OLD.id USING ERRCODE = '42501';
            END IF;
            IF NEW.run_number IS DISTINCT FROM OLD.run_number
                OR NEW.financial_year IS DISTINCT FROM OLD.financial_year
                OR NEW.domain IS DISTINCT FROM OLD.domain
                OR NEW.period_start IS DISTINCT FROM OLD.period_start
                OR NEW.period_end IS DISTINCT FROM OLD.period_end
                OR NEW.cutoff_at IS DISTINCT FROM OLD.cutoff_at
                OR NEW.started_by IS DISTINCT FROM OLD.started_by
                OR NEW.started_at IS DISTINCT FROM OLD.started_at
                OR (OLD.status = 'CLOSED' AND NEW.status IS DISTINCT FROM 'CLOSED') THEN
                RAISE EXCEPTION 'Immutable fields or closed status on reconciliation run (%) cannot be modified.', OLD.id USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_reconciliation_run_immutability
        BEFORE UPDATE OR DELETE ON audit.reconciliation_runs
        FOR EACH ROW EXECUTE FUNCTION audit.fn_protect_reconciliation_run_immutability();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_reconciliation_run_immutability ON audit.reconciliation_runs")
    op.execute("DROP FUNCTION IF EXISTS audit.fn_protect_reconciliation_run_immutability()")
    op.execute("DROP TRIGGER IF EXISTS trg_reconciliation_events_append_only ON audit.reconciliation_events")

    op.drop_index("idx_re_disc_time", table_name="reconciliation_events", schema="audit")
    op.drop_index("idx_re_run_time", table_name="reconciliation_events", schema="audit")
    op.drop_table("reconciliation_events", schema="audit")

    op.drop_index("idx_rd_domain_status", table_name="reconciliation_discrepancies", schema="audit")
    op.drop_index("idx_rd_run_status", table_name="reconciliation_discrepancies", schema="audit")
    op.drop_table("reconciliation_discrepancies", schema="audit")

    op.drop_index("idx_recon_domain_status", table_name="reconciliation_runs", schema="audit")
    op.drop_index("uq_recon_active_fingerprint", table_name="reconciliation_runs", schema="audit")
    op.drop_table("reconciliation_runs", schema="audit")

    op.drop_index("idx_audit_correlation_ref", table_name="audit_logs", schema="audit")
    op.drop_index("idx_audit_action_time", table_name="audit_logs", schema="audit")
    op.drop_column("audit_logs", "metadata_json", schema="audit")
    op.drop_column("audit_logs", "correlation_ref", schema="audit")
    op.execute("ALTER TABLE audit.audit_logs ALTER COLUMN action TYPE VARCHAR(32)")

    op.execute(
        "ALTER TABLE billing.fiscal_sequences "
        "DROP CONSTRAINT IF EXISTS chk_fiscal_sequences_fs_doc_type_enum, "
        "DROP CONSTRAINT IF EXISTS chk_fiscal_sequences_chk_fiscal_sequences_fs_doc_type_enum"
    )
    op.execute("DELETE FROM billing.fiscal_sequences WHERE doc_type = 'RECONCILIATION'")
    op.execute(
        "ALTER TABLE billing.fiscal_sequences "
        "ADD CONSTRAINT chk_fiscal_sequences_fs_doc_type_enum "
        "CHECK (doc_type IN ('INVOICE', 'CREDIT_NOTE', 'DISPATCH', 'PAYMENT', 'REFUND'))"
    )
