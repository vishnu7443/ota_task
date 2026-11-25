"""SQLAlchemy 2.0 models for costing schema: ProductionOverheads & append-only ProductionCostSummaries."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProductionOverhead(Base):
    """Explicitly configured direct-run or monthly-pool factory overhead (labour, gas/power, etc.)."""

    __tablename__ = "production_overheads"
    __table_args__ = (
        CheckConstraint("period_month ~ '^[0-9]{4}-[0-9]{2}$'", name="po_period_format"),
        CheckConstraint(
            "overhead_type IN ('DIRECT_LABOUR','GAS_POWER','PACKAGING_LABOUR','FACTORY_RENT','MACHINE_DEPRECIATION','OTHER_PRODUCTION_EXPENSE')",
            name="po_type_enum",
        ),
        CheckConstraint("allocation_scope IN ('DIRECT_RUN', 'MONTHLY_POOL')", name="po_scope_enum"),
        CheckConstraint(
            "(allocation_scope = 'DIRECT_RUN' AND production_run_id IS NOT NULL) OR "
            "(allocation_scope = 'MONTHLY_POOL' AND production_run_id IS NULL)",
            name="po_scope_run_match",
        ),
        CheckConstraint("amount_paisa > 0", name="po_amount_pos"),
        Index("idx_cost_overheads_run", "production_run_id"),
        Index("idx_cost_overheads_period", "period_month", "allocation_scope"),
        {"schema": "costing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    production_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("production.production_runs.id", ondelete="RESTRICT"), nullable=True
    )
    period_month: Mapped[str] = mapped_column(String(7), nullable=False)
    overhead_type: Mapped[str] = mapped_column(String(32), nullable=False)
    allocation_scope: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_voided: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    voided_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProductionCostSummary(Base):
    """Immutable versioned batch costing snapshot per ProductionRun preserving full history."""

    __tablename__ = "production_cost_summaries"
    __table_args__ = (
        CheckConstraint("snapshot_version >= 1", name="pcs_version_pos"),
        CheckConstraint("cost_status IN ('PRELIMINARY', 'FINALIZED')", name="pcs_status_enum"),
        CheckConstraint(
            "valuation_method IN ('FIFO', 'WEIGHTED_AVERAGE', 'LAST_PRICE')",
            name="pcs_val_method_enum",
        ),
        CheckConstraint("total_cost_paisa >= 0", name="pcs_total_non_neg"),
        CheckConstraint("good_packets >= 0", name="pcs_good_non_neg"),
        CheckConstraint("rejected_packets >= 0", name="pcs_rej_non_neg"),
        UniqueConstraint("production_run_id", "snapshot_version", name="uq_pcs_run_version"),
        Index(
            "uq_pcs_current_run",
            "production_run_id",
            unique=True,
            postgresql_where=text("is_current IS TRUE"),
        ),
        {"schema": "costing"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    production_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("production.production_runs.id", ondelete="RESTRICT"), nullable=False
    )
    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    cost_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="'FINALIZED'")
    valuation_method: Mapped[str] = mapped_column(String(24), nullable=False)
    planned_raw_cost_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    planned_pkg_cost_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    planned_overhead_cost_paisa: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    planned_total_cost_paisa: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    planned_cost_per_packet_paisa: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, server_default="0"
    )
    raw_material_cost_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    good_packaging_cost_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    damaged_packaging_cost_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    packaging_cost_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw_wastage_cost_paisa: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    rejected_output_cost_impact_paisa: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    direct_labour_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    gas_power_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    other_direct_overhead_paisa: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    direct_overhead_paisa: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    allocated_overhead_paisa: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    total_cost_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_output_pkts: Mapped[int] = mapped_column(Integer, nullable=False)
    good_packets: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_packets: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_per_packet_paisa: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    exact_cost_per_packet_paisa: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    selling_price_snapshot_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gross_margin_per_pkt_paisa: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    gross_margin_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    material_variance_paisa: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    cost_breakdown_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    computed_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
