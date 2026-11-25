from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    """Immutable append-only log for order creation, edits, approvals, and security events."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_entity_time", "entity_table", "entity_id", text("occurred_at DESC")),
        Index("idx_audit_actor_time", "actor_user_id", text("occurred_at DESC")),
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
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_schema: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_table: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
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
