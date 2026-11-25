"""Phase 9: Payment Management, Invoice Allocations, Customer AR & Production Costing schemas.

Revision ID: 0006_phase9_payments_costing
Revises: 0005_phase8_gst_billing_dispatch
Create Date: 2026-11-25 15:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_phase9_payments_costing"
down_revision: Union[str, Sequence[str], None] = "0005_phase8_gst_billing_dispatch"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS finance")
    op.execute("CREATE SCHEMA IF NOT EXISTS costing")

    # Extend billing.fiscal_sequences to issue sequential PMT & RFD document numbers safely
    op.execute(
        "ALTER TABLE billing.fiscal_sequences "
        "DROP CONSTRAINT IF EXISTS chk_fiscal_sequences_fs_doc_type_enum, "
        "DROP CONSTRAINT IF EXISTS chk_fiscal_sequences_chk_fiscal_sequences_fs_doc_type_enum"
    )
    op.execute(
        "ALTER TABLE billing.fiscal_sequences "
        "ADD CONSTRAINT chk_fiscal_sequences_fs_doc_type_enum "
        "CHECK (doc_type IN ('INVOICE', 'CREDIT_NOTE', 'DISPATCH', 'PAYMENT', 'REFUND'))"
    )

    # Ensure paid + credited never exceed invoice grand total at DB level
    op.execute(
        "ALTER TABLE billing.invoices "
        "ADD CONSTRAINT chk_invoices_inv_paid_credited_cap "
        "CHECK (paid_paisa + credited_paisa <= taxable_total_paisa + cgst_total_paisa + sgst_total_paisa + igst_total_paisa + round_off_paisa)"
    )

    # ── FINANCE SCHEMA ──────────────────────────────────────────────────────
    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("payment_number", sa.String(length=32), nullable=False),
        sa.Column("financial_year", sa.String(length=7), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("amount_paisa", sa.BigInteger(), nullable=False),
        sa.Column("allocated_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("refunded_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "unallocated_paisa",
            sa.BigInteger(),
            sa.Computed(
                "CASE WHEN status IN ('REVERSED','REFUNDED') THEN 0::bigint "
                "ELSE GREATEST(0::bigint, amount_paisa - allocated_paisa - refunded_paisa) END",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("payment_mode", sa.String(length=24), nullable=False),
        sa.Column("reference_no", sa.String(length=80), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("is_advance", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="'RECORDED'", nullable=False),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        sa.Column("reversed_by", sa.BigInteger(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_by", sa.BigInteger(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("financial_year ~ '^[0-9]{4}-[0-9]{2}$'", name="chk_payments_pmt_fy_format"),
        sa.CheckConstraint("amount_paisa > 0", name="chk_payments_pmt_amount_pos"),
        sa.CheckConstraint("allocated_paisa >= 0", name="chk_payments_pmt_allocated_non_neg"),
        sa.CheckConstraint("refunded_paisa >= 0", name="chk_payments_pmt_refunded_non_neg"),
        sa.CheckConstraint("allocated_paisa + refunded_paisa <= amount_paisa", name="chk_payments_pmt_cap_bounds"),
        sa.CheckConstraint(
            "payment_mode IN ('CASH','UPI','BANK_TRANSFER','NEFT','RTGS','IMPS','CHEQUE','CARD','OTHER')",
            name="chk_payments_pmt_mode_enum",
        ),
        sa.CheckConstraint(
            "status IN ('RECORDED','PARTIALLY_ALLOCATED','ALLOCATED','PARTIALLY_REFUNDED','REFUNDED','REVERSED')",
            name="chk_payments_pmt_status_enum",
        ),
        sa.CheckConstraint("version >= 1", name="chk_payments_pmt_version_pos"),
        sa.ForeignKeyConstraint(["customer_id"], ["sales.customers.id"], name="fk_payments_customer_id_customers", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by"], ["iam.users.id"], name="fk_payments_recorded_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reversed_by"], ["iam.users.id"], name="fk_payments_reversed_by_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
        sa.UniqueConstraint("payment_number", name="uq_payments_payment_number"),
        schema="finance",
    )
    op.create_index(
        "uq_payments_customer_dup_ref",
        "payments",
        ["customer_id", "payment_date", "amount_paisa", "reference_no"],
        unique=True,
        schema="finance",
        postgresql_where=sa.text("status <> 'REVERSED' AND reference_no IS NOT NULL"),
    )
    op.create_index(
        "idx_payments_customer_date",
        "payments",
        ["customer_id", sa.text("payment_date DESC"), sa.text("id DESC")],
        unique=False,
        schema="finance",
    )
    op.create_index(
        "idx_payments_status_date",
        "payments",
        ["status", sa.text("payment_date DESC")],
        unique=False,
        schema="finance",
    )

    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("payment_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("allocated_paisa", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="'ACTIVE'", nullable=False),
        sa.Column("allocated_by", sa.BigInteger(), nullable=False),
        sa.Column("allocated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("reversed_by", sa.BigInteger(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("allocated_paisa > 0", name="chk_payment_allocations_pa_amount_pos"),
        sa.CheckConstraint("status IN ('ACTIVE', 'REVERSED')", name="chk_payment_allocations_pa_status_enum"),
        sa.ForeignKeyConstraint(["allocated_by"], ["iam.users.id"], name="fk_pa_allocated_by_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing.invoices.id"], name="fk_pa_invoice_id_invoices", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_id"], ["finance.payments.id"], name="fk_pa_payment_id_payments", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reversed_by"], ["iam.users.id"], name="fk_pa_reversed_by_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_payment_allocations"),
        schema="finance",
    )
    op.create_index("idx_pa_payment_status", "payment_allocations", ["payment_id", "status"], unique=False, schema="finance")
    op.create_index("idx_pa_invoice_status", "payment_allocations", ["invoice_id", "status"], unique=False, schema="finance")

    op.create_table(
        "payment_refunds",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("refund_number", sa.String(length=32), nullable=False),
        sa.Column("financial_year", sa.String(length=7), nullable=False),
        sa.Column("payment_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("refund_date", sa.Date(), nullable=False),
        sa.Column("amount_paisa", sa.BigInteger(), nullable=False),
        sa.Column("refund_mode", sa.String(length=24), nullable=False),
        sa.Column("reference_no", sa.String(length=80), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="'POSTED'", nullable=False),
        sa.Column("refunded_by", sa.BigInteger(), nullable=False),
        sa.Column("refunded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("financial_year ~ '^[0-9]{4}-[0-9]{2}$'", name="chk_payment_refunds_rfd_fy_format"),
        sa.CheckConstraint("amount_paisa > 0", name="chk_payment_refunds_rfd_amount_pos"),
        sa.CheckConstraint(
            "refund_mode IN ('CASH','UPI','BANK_TRANSFER','NEFT','RTGS','IMPS','CHEQUE','CARD','OTHER')",
            name="chk_payment_refunds_rfd_mode_enum",
        ),
        sa.CheckConstraint("length(trim(reason)) >= 5", name="chk_payment_refunds_rfd_reason_len"),
        sa.CheckConstraint("status IN ('POSTED')", name="chk_payment_refunds_rfd_status_enum"),
        sa.ForeignKeyConstraint(["customer_id"], ["sales.customers.id"], name="fk_rfd_customer_id_customers", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_id"], ["finance.payments.id"], name="fk_rfd_payment_id_payments", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["refunded_by"], ["iam.users.id"], name="fk_rfd_refunded_by_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_payment_refunds"),
        sa.UniqueConstraint("refund_number", name="uq_payment_refunds_refund_number"),
        schema="finance",
    )
    op.create_index("idx_refunds_payment", "payment_refunds", ["payment_id"], unique=False, schema="finance")
    op.create_index("idx_refunds_customer_date", "payment_refunds", ["customer_id", sa.text("refund_date DESC")], unique=False, schema="finance")

    op.create_table(
        "customer_receivables",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("original_paisa", sa.BigInteger(), nullable=False),
        sa.Column("credited_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("paid_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "outstanding_paisa",
            sa.BigInteger(),
            sa.Computed("original_paisa - credited_paisa - paid_paisa", persisted=True),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("original_paisa >= 0", name="chk_customer_receivables_ar_orig_non_neg"),
        sa.CheckConstraint("credited_paisa >= 0", name="chk_customer_receivables_ar_cred_non_neg"),
        sa.CheckConstraint("paid_paisa >= 0", name="chk_customer_receivables_ar_paid_non_neg"),
        sa.CheckConstraint("credited_paisa + paid_paisa <= original_paisa", name="chk_customer_receivables_ar_non_negative"),
        sa.ForeignKeyConstraint(["customer_id"], ["sales.customers.id"], name="fk_ar_customer_id_customers", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing.invoices.id"], name="fk_ar_invoice_id_invoices", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_customer_receivables"),
        sa.UniqueConstraint("invoice_id", name="uq_customer_receivables_invoice_id"),
        schema="finance",
    )
    op.create_index("idx_ar_customer_due", "customer_receivables", ["customer_id", "due_date"], unique=False, schema="finance")

    # ── COSTING SCHEMA ──────────────────────────────────────────────────────
    op.create_table(
        "production_overheads",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("production_run_id", sa.BigInteger(), nullable=True),
        sa.Column("period_month", sa.String(length=7), nullable=False),
        sa.Column("overhead_type", sa.String(length=32), nullable=False),
        sa.Column("allocation_scope", sa.String(length=20), nullable=False),
        sa.Column("amount_paisa", sa.BigInteger(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_voided", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("voided_by", sa.BigInteger(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_by", sa.BigInteger(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("period_month ~ '^[0-9]{4}-[0-9]{2}$'", name="chk_production_overheads_po_period_format"),
        sa.CheckConstraint(
            "overhead_type IN ('DIRECT_LABOUR','GAS_POWER','PACKAGING_LABOUR','FACTORY_RENT','MACHINE_DEPRECIATION','OTHER_PRODUCTION_EXPENSE')",
            name="chk_production_overheads_po_type_enum",
        ),
        sa.CheckConstraint("allocation_scope IN ('DIRECT_RUN', 'MONTHLY_POOL')", name="chk_production_overheads_po_scope_enum"),
        sa.CheckConstraint(
            "(allocation_scope = 'DIRECT_RUN' AND production_run_id IS NOT NULL) OR "
            "(allocation_scope = 'MONTHLY_POOL' AND production_run_id IS NULL)",
            name="chk_production_overheads_po_scope_run_match",
        ),
        sa.CheckConstraint("amount_paisa > 0", name="chk_production_overheads_po_amount_pos"),
        sa.ForeignKeyConstraint(["production_run_id"], ["production.production_runs.id"], name="fk_cost_overheads_run", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by"], ["iam.users.id"], name="fk_cost_overheads_rec_by", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["voided_by"], ["iam.users.id"], name="fk_cost_overheads_void_by", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_production_overheads"),
        schema="costing",
    )
    op.create_index("idx_cost_overheads_run", "production_overheads", ["production_run_id"], unique=False, schema="costing")
    op.create_index("idx_cost_overheads_period", "production_overheads", ["period_month", "allocation_scope"], unique=False, schema="costing")

    op.create_table(
        "production_cost_summaries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("production_run_id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("cost_status", sa.String(length=16), server_default="'FINALIZED'", nullable=False),
        sa.Column("valuation_method", sa.String(length=24), nullable=False),
        sa.Column("planned_raw_cost_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("planned_pkg_cost_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("planned_overhead_cost_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("planned_total_cost_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("planned_cost_per_packet_paisa", sa.Numeric(precision=18, scale=6), server_default="0", nullable=False),
        sa.Column("raw_material_cost_paisa", sa.BigInteger(), nullable=False),
        sa.Column("good_packaging_cost_paisa", sa.BigInteger(), nullable=False),
        sa.Column("damaged_packaging_cost_paisa", sa.BigInteger(), nullable=False),
        sa.Column("packaging_cost_paisa", sa.BigInteger(), nullable=False),
        sa.Column("raw_wastage_cost_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("rejected_output_cost_impact_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("direct_labour_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("gas_power_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("other_direct_overhead_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("direct_overhead_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("allocated_overhead_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total_cost_paisa", sa.BigInteger(), nullable=False),
        sa.Column("expected_output_pkts", sa.Integer(), nullable=False),
        sa.Column("good_packets", sa.Integer(), nullable=False),
        sa.Column("rejected_packets", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_per_packet_paisa", sa.BigInteger(), nullable=True),
        sa.Column("exact_cost_per_packet_paisa", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("selling_price_snapshot_paisa", sa.BigInteger(), nullable=False),
        sa.Column("gross_margin_per_pkt_paisa", sa.BigInteger(), nullable=True),
        sa.Column("gross_margin_pct", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("material_variance_paisa", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("cost_breakdown_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("computed_by", sa.BigInteger(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("snapshot_version >= 1", name="chk_pcs_version_pos"),
        sa.CheckConstraint("cost_status IN ('PRELIMINARY', 'FINALIZED')", name="chk_pcs_status_enum"),
        sa.CheckConstraint("valuation_method IN ('FIFO', 'WEIGHTED_AVERAGE', 'LAST_PRICE')", name="chk_pcs_val_method_enum"),
        sa.CheckConstraint("total_cost_paisa >= 0", name="chk_pcs_total_non_neg"),
        sa.CheckConstraint("good_packets >= 0", name="chk_pcs_good_non_neg"),
        sa.CheckConstraint("rejected_packets >= 0", name="chk_pcs_rej_non_neg"),
        sa.ForeignKeyConstraint(["computed_by"], ["iam.users.id"], name="fk_pcs_computed_by", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_run_id"], ["production.production_runs.id"], name="fk_pcs_run_id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_production_cost_summaries"),
        sa.UniqueConstraint("production_run_id", "snapshot_version", name="uq_pcs_run_version"),
        schema="costing",
    )
    op.create_index(
        "uq_pcs_current_run",
        "production_cost_summaries",
        ["production_run_id"],
        unique=True,
        schema="costing",
        postgresql_where=sa.text("is_current IS TRUE"),
    )

    # Backfill CustomerReceivable for any pre-existing non-DRAFT invoices
    op.execute(
        """
        INSERT INTO finance.customer_receivables
            (customer_id, invoice_id, invoice_date, due_date, original_paisa, credited_paisa, paid_paisa)
        SELECT
            customer_id,
            id,
            invoice_date,
            due_date,
            grand_total_paisa,
            credited_paisa,
            paid_paisa
        FROM billing.invoices
        WHERE doc_status <> 'DRAFT'
        ON CONFLICT (invoice_id) DO NOTHING;
        """
    )

    # ── DATABASE INTEGRITY & IMMUTABILITY TRIGGERS ──────────────────────────
    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance.fn_protect_posted_payment_immutability()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Posted customer payment (%) cannot be deleted; issue a reversal instead.', OLD.id USING ERRCODE = '42501';
            END IF;
            IF NEW.payment_number IS DISTINCT FROM OLD.payment_number
                OR NEW.financial_year IS DISTINCT FROM OLD.financial_year
                OR NEW.customer_id IS DISTINCT FROM OLD.customer_id
                OR NEW.payment_date IS DISTINCT FROM OLD.payment_date
                OR NEW.amount_paisa IS DISTINCT FROM OLD.amount_paisa
                OR NEW.payment_mode IS DISTINCT FROM OLD.payment_mode
                OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
                OR NEW.recorded_by IS DISTINCT FROM OLD.recorded_by
                OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at
                OR (OLD.status = 'REVERSED' AND NEW.status IS DISTINCT FROM 'REVERSED') THEN
                RAISE EXCEPTION 'Immutable fields on payment (%) cannot be modified after posting.', OLD.id USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_payment_immutability
        BEFORE UPDATE OR DELETE ON finance.payments
        FOR EACH ROW EXECUTE FUNCTION finance.fn_protect_posted_payment_immutability();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance.fn_protect_allocation_immutability()
        RETURNS TRIGGER AS $$
        DECLARE
            v_pmt_avail BIGINT;
            v_inv_rem BIGINT;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Payment allocation (%) cannot be deleted; reverse the allocation instead.', OLD.id USING ERRCODE = '42501';
            END IF;
            IF TG_OP = 'UPDATE' THEN
                IF NEW.payment_id IS DISTINCT FROM OLD.payment_id
                    OR NEW.invoice_id IS DISTINCT FROM OLD.invoice_id
                    OR NEW.allocated_paisa IS DISTINCT FROM OLD.allocated_paisa
                    OR NEW.allocated_by IS DISTINCT FROM OLD.allocated_by
                    OR NEW.allocated_at IS DISTINCT FROM OLD.allocated_at
                    OR (OLD.status = 'REVERSED' AND NEW.status IS DISTINCT FROM 'REVERSED') THEN
                    RAISE EXCEPTION 'Posted payment allocation (%) cannot be altered once recorded.', OLD.id USING ERRCODE = '42501';
                END IF;
                RETURN NEW;
            END IF;

            -- INSERT guard: enforce payment cap & invoice remaining cap independently in DB
            SELECT (amount_paisa - refunded_paisa) - COALESCE((
                SELECT SUM(pa.allocated_paisa) FROM finance.payment_allocations pa
                WHERE pa.payment_id = NEW.payment_id AND pa.status = 'ACTIVE'
            ), 0)
            INTO v_pmt_avail
            FROM finance.payments WHERE id = NEW.payment_id AND status NOT IN ('REVERSED','REFUNDED');

            IF v_pmt_avail IS NULL OR NEW.allocated_paisa > v_pmt_avail THEN
                RAISE EXCEPTION 'Allocation (% paise) exceeds available unallocated balance on payment %.', NEW.allocated_paisa, NEW.payment_id USING ERRCODE = '23514';
            END IF;

            SELECT (grand_total_paisa - credited_paisa) - COALESCE((
                SELECT SUM(pa.allocated_paisa) FROM finance.payment_allocations pa
                WHERE pa.invoice_id = NEW.invoice_id AND pa.status = 'ACTIVE'
            ), 0)
            INTO v_inv_rem
            FROM billing.invoices WHERE id = NEW.invoice_id AND doc_status = 'ISSUED';

            IF v_inv_rem IS NULL OR NEW.allocated_paisa > v_inv_rem THEN
                RAISE EXCEPTION 'Allocation (% paise) exceeds remaining outstanding balance on invoice %.', NEW.allocated_paisa, NEW.invoice_id USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_payment_allocation_integrity
        BEFORE INSERT OR UPDATE OR DELETE ON finance.payment_allocations
        FOR EACH ROW EXECUTE FUNCTION finance.fn_protect_allocation_immutability();
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_payment_refunds_append_only
        BEFORE UPDATE OR DELETE ON finance.payment_refunds
        FOR EACH ROW EXECUTE FUNCTION audit.fn_prevent_mutation();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance.fn_protect_receivable_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Customer receivable record (%) cannot be deleted.', OLD.id USING ERRCODE = '42501';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_customer_receivable_no_delete
        BEFORE DELETE ON finance.customer_receivables
        FOR EACH ROW EXECUTE FUNCTION finance.fn_protect_receivable_delete();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION costing.fn_protect_cost_summary_immutability()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Historical production cost snapshot (%) cannot be deleted.', OLD.id USING ERRCODE = '42501';
            END IF;
            -- Allow ONLY superseding is_current = TRUE -> FALSE; all monetary & quantity fields stay frozen forever!
            IF OLD.is_current IS FALSE
                OR NEW.is_current IS TRUE
                OR NEW.production_run_id IS DISTINCT FROM OLD.production_run_id
                OR NEW.snapshot_version IS DISTINCT FROM OLD.snapshot_version
                OR NEW.cost_status IS DISTINCT FROM OLD.cost_status
                OR NEW.valuation_method IS DISTINCT FROM OLD.valuation_method
                OR NEW.raw_material_cost_paisa IS DISTINCT FROM OLD.raw_material_cost_paisa
                OR NEW.packaging_cost_paisa IS DISTINCT FROM OLD.packaging_cost_paisa
                OR NEW.direct_overhead_paisa IS DISTINCT FROM OLD.direct_overhead_paisa
                OR NEW.allocated_overhead_paisa IS DISTINCT FROM OLD.allocated_overhead_paisa
                OR NEW.total_cost_paisa IS DISTINCT FROM OLD.total_cost_paisa
                OR NEW.cost_per_packet_paisa IS DISTINCT FROM OLD.cost_per_packet_paisa
                OR NEW.exact_cost_per_packet_paisa IS DISTINCT FROM OLD.exact_cost_per_packet_paisa
                OR NEW.cost_breakdown_snapshot IS DISTINCT FROM OLD.cost_breakdown_snapshot THEN
                RAISE EXCEPTION 'Historical production cost snapshot (%) cannot be modified.', OLD.id USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_cost_summary_immutability
        BEFORE UPDATE OR DELETE ON costing.production_cost_summaries
        FOR EACH ROW EXECUTE FUNCTION costing.fn_protect_cost_summary_immutability();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION costing.fn_protect_overhead_immutability()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Production overhead entry (%) cannot be deleted; void it with a reason instead.', OLD.id USING ERRCODE = '42501';
            END IF;
            IF OLD.is_voided IS TRUE
                OR NEW.is_voided IS FALSE
                OR NEW.production_run_id IS DISTINCT FROM OLD.production_run_id
                OR NEW.period_month IS DISTINCT FROM OLD.period_month
                OR NEW.overhead_type IS DISTINCT FROM OLD.overhead_type
                OR NEW.allocation_scope IS DISTINCT FROM OLD.allocation_scope
                OR NEW.amount_paisa IS DISTINCT FROM OLD.amount_paisa THEN
                RAISE EXCEPTION 'Immutable overhead fields (%) cannot be altered.', OLD.id USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_overhead_immutability
        BEFORE UPDATE OR DELETE ON costing.production_overheads
        FOR EACH ROW EXECUTE FUNCTION costing.fn_protect_overhead_immutability();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_overhead_immutability ON costing.production_overheads")
    op.execute("DROP FUNCTION IF EXISTS costing.fn_protect_overhead_immutability()")
    op.execute("DROP TRIGGER IF EXISTS trg_cost_summary_immutability ON costing.production_cost_summaries")
    op.execute("DROP FUNCTION IF EXISTS costing.fn_protect_cost_summary_immutability()")
    op.execute("DROP TRIGGER IF EXISTS trg_customer_receivable_no_delete ON finance.customer_receivables")
    op.execute("DROP FUNCTION IF EXISTS finance.fn_protect_receivable_delete()")
    op.execute("DROP TRIGGER IF EXISTS trg_payment_refunds_append_only ON finance.payment_refunds")
    op.execute("DROP TRIGGER IF EXISTS trg_payment_allocation_integrity ON finance.payment_allocations")
    op.execute("DROP FUNCTION IF EXISTS finance.fn_protect_allocation_immutability()")
    op.execute("DROP TRIGGER IF EXISTS trg_payment_immutability ON finance.payments")
    op.execute("DROP FUNCTION IF EXISTS finance.fn_protect_posted_payment_immutability()")

    op.drop_index("uq_pcs_current_run", table_name="production_cost_summaries", schema="costing")
    op.drop_table("production_cost_summaries", schema="costing")
    op.drop_index("idx_cost_overheads_period", table_name="production_overheads", schema="costing")
    op.drop_index("idx_cost_overheads_run", table_name="production_overheads", schema="costing")
    op.drop_table("production_overheads", schema="costing")

    op.drop_index("idx_ar_customer_due", table_name="customer_receivables", schema="finance")
    op.drop_table("customer_receivables", schema="finance")
    op.drop_index("idx_refunds_customer_date", table_name="payment_refunds", schema="finance")
    op.drop_index("idx_refunds_payment", table_name="payment_refunds", schema="finance")
    op.drop_table("payment_refunds", schema="finance")
    op.drop_index("idx_pa_invoice_status", table_name="payment_allocations", schema="finance")
    op.drop_index("idx_pa_payment_status", table_name="payment_allocations", schema="finance")
    op.drop_table("payment_allocations", schema="finance")
    op.drop_index("idx_payments_status_date", table_name="payments", schema="finance")
    op.drop_index("idx_payments_customer_date", table_name="payments", schema="finance")
    op.drop_index("uq_payments_customer_dup_ref", table_name="payments", schema="finance")
    op.drop_table("payments", schema="finance")

    op.execute(
        "ALTER TABLE billing.invoices "
        "DROP CONSTRAINT IF EXISTS chk_invoices_inv_paid_credited_cap, "
        "DROP CONSTRAINT IF EXISTS chk_invoices_chk_invoices_inv_paid_credited_cap"
    )
    op.execute(
        "ALTER TABLE billing.fiscal_sequences "
        "DROP CONSTRAINT IF EXISTS chk_fiscal_sequences_fs_doc_type_enum, "
        "DROP CONSTRAINT IF EXISTS chk_fiscal_sequences_chk_fiscal_sequences_fs_doc_type_enum"
    )
    op.execute("DELETE FROM billing.fiscal_sequences WHERE doc_type IN ('PAYMENT', 'REFUND')")
    op.execute(
        "ALTER TABLE billing.fiscal_sequences "
        "ADD CONSTRAINT chk_fiscal_sequences_fs_doc_type_enum "
        "CHECK (doc_type IN ('INVOICE', 'CREDIT_NOTE', 'DISPATCH'))"
    )

    op.execute("DROP SCHEMA IF EXISTS costing")
    op.execute("DROP SCHEMA IF EXISTS finance")
