"""Audit, Variance Alerts, Cross-Module Reconciliation & Discrepancy Resolution models (`audit` schema)."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AuditLog(Base):
    """Immutable append-only centralized log for business, security, and financial events."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_entity_time", "entity_table", "entity_id", text("occurred_at DESC")),
        Index("idx_audit_actor_time", "actor_user_id", text("occurred_at DESC")),
        Index("idx_audit_action_time", "action", text("occurred_at DESC")),
        Index(
            "idx_audit_correlation_ref",
            "correlation_ref",
            postgresql_where=text("correlation_ref IS NOT NULL"),
        ),
        {"schema": "audit"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_schema: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_table: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    correlation_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class VarianceAlert(Base):
    """Automated alert triggered when a production variance exceeds company tolerance."""

    __tablename__ = "variance_alerts"
    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('YIELD_LOSS', 'YIELD_EXCESS', 'MATERIAL_OVERUSE', 'MATERIAL_UNDERUSE', 'PACKAGING_WASTAGE')",
            name="va_type_enum",
        ),
        CheckConstraint("status IN ('OPEN', 'ACKNOWLEDGED')", name="va_status_enum"),
        Index("idx_va_status_time", "status", text("created_at DESC")),
        {"schema": "audit"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    production_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("production.production_runs.id", ondelete="RESTRICT"), nullable=False
    )
    production_variance_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("production.production_variances.id", ondelete="RESTRICT"), nullable=False
    )
    alert_type: Mapped[str] = mapped_column(String(24), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="OPEN")
    acknowledged_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledgement_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReconciliationRun(Base):
    """Deterministic cross-module reconciliation run anchored to explicit period and cutoff timestamp."""

    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        CheckConstraint("financial_year ~ '^[0-9]{4}-[0-9]{2}$'", name="rr_fy_format"),
        CheckConstraint(
            "domain IN ('INVENTORY', 'SALES', 'INVOICE', 'PAYMENT', 'DISPATCH', 'PRODUCTION', 'FULL_SYSTEM')",
            name="rr_domain_enum",
        ),
        CheckConstraint(
            "status IN ('NOT_STARTED', 'IN_PROGRESS', 'RECONCILED', 'DISCREPANCY_FOUND', 'UNDER_REVIEW', 'RESOLVED', 'CLOSED')",
            name="rr_status_enum",
        ),
        CheckConstraint("period_end >= period_start", name="rr_period_order"),
        CheckConstraint("discrepancy_count >= 0 AND resolved_count >= 0", name="rr_counts_non_neg"),
        CheckConstraint("version >= 1", name="rr_version_pos"),
        Index(
            "uq_recon_active_fingerprint",
            "run_fingerprint",
            unique=True,
            postgresql_where=text("status IN ('NOT_STARTED', 'IN_PROGRESS', 'DISCREPANCY_FOUND', 'UNDER_REVIEW')"),
        ),
        Index("idx_recon_domain_status", "domain", "status", text("started_at DESC")),
        {"schema": "audit"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    financial_year: Mapped[str] = mapped_column(String(7), nullable=False)
    domain: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="'IN_PROGRESS'")
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scope_filter: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    run_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    summary_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    discrepancy_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    resolved_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    started_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_rerun_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closure_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    discrepancies: Mapped[list["ReconciliationDiscrepancy"]] = relationship(
        back_populates="reconciliation_run", order_by="ReconciliationDiscrepancy.id.asc()"
    )
    events: Mapped[list["ReconciliationEvent"]] = relationship(
        back_populates="reconciliation_run", order_by="ReconciliationEvent.id.asc()"
    )


class ReconciliationDiscrepancy(Base):
    """Detected cross-module mismatch tracked through investigation, approval, and authorized resolution."""

    __tablename__ = "reconciliation_discrepancies"
    __table_args__ = (
        CheckConstraint(
            "domain IN ('INVENTORY', 'PURCHASING', 'SALES', 'INVOICE', 'GST', 'PAYMENT', 'DISPATCH', 'PRODUCTION')",
            name="rd_domain_enum",
        ),
        CheckConstraint(
            "severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="rd_severity_enum",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'UNDER_REVIEW', 'ACTION_PROPOSED', 'APPROVED', 'RESOLVED', 'CLOSED', 'DISMISSED')",
            name="rd_status_enum",
        ),
        CheckConstraint(
            "corrective_action_type IS NULL OR corrective_action_type IN "
            "('STOCK_ADJUSTMENT', 'ISSUE_INVOICE', 'AR_RECALC_NOTE', 'MANUAL_JOURNAL_NOTE', 'DISPATCH_FOLLOWUP', 'NO_OP_EXPLAINED')",
            name="rd_action_type_enum",
        ),
        CheckConstraint("version >= 1", name="rd_version_pos"),
        Index("idx_rd_run_status", "reconciliation_run_id", "status"),
        Index("idx_rd_domain_status", "domain", "status"),
        {"schema": "audit"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reconciliation_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("audit.reconciliation_runs.id", ondelete="RESTRICT"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(24), nullable=False)
    discrepancy_code: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, server_default="'MEDIUM'")
    entity_schema: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_table: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entity_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    actual_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    difference_summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="'OPEN'")
    assigned_to: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    investigation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_ref_table: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution_ref_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    reconciliation_run: Mapped[ReconciliationRun] = relationship(back_populates="discrepancies")


class ReconciliationEvent(Base):
    """Immutable append-only history log of every reconciliation investigation, approval, and resolution."""

    __tablename__ = "reconciliation_events"
    __table_args__ = (
        Index("idx_re_run_time", "reconciliation_run_id", "occurred_at"),
        Index("idx_re_disc_time", "discrepancy_id", "occurred_at"),
        {"schema": "audit"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reconciliation_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("audit.reconciliation_runs.id", ondelete="RESTRICT"), nullable=False
    )
    discrepancy_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("audit.reconciliation_discrepancies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    actor_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(36), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    reconciliation_run: Mapped[ReconciliationRun] = relationship(back_populates="events")
