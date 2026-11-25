"""Production domain SQLAlchemy models — RecipeTemplates, BOM, Versions, Production Runs, Material Issues, Outputs, Wastages, Variances.

Tables reside in `production` PostgreSQL schema following Phase 3 relational architecture.
Financial overhead allocation / final costing (Step 8) is intentionally deferred beyond Phase 7.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RecipeTemplate(Base):
    """Shared bulk cooking formula for a snack family (e.g. Murukku Base Mix)."""

    __tablename__ = "recipe_templates"
    __table_args__ = (
        CheckConstraint("base_yield_weight_g > 0", name="rt_yield_pos"),
        {"schema": "production"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sales.products.id", ondelete="RESTRICT"), nullable=True
    )
    base_yield_weight_g: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class BomHeader(Base):
    """1:1 BOM container per PackSize SKU pointing to the currently active BomVersion."""

    __tablename__ = "bom_headers"
    __table_args__ = ({"schema": "production"},)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pack_size_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    active_version_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    versions: Mapped[list["BomVersion"]] = relationship(
        back_populates="bom_header", order_by="BomVersion.version_no.desc()"
    )


class BomVersion(Base):
    """Immutable versioned BOM recipe snapshot for a specific PackSize."""

    __tablename__ = "bom_versions"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'SUPERSEDED')", name="bv_status_enum"),
        CheckConstraint("version_no > 0", name="bv_version_pos"),
        CheckConstraint("expected_yield_pkts > 0", name="bv_yield_pos"),
        CheckConstraint("batch_multiplier > 0", name="bv_batch_mult_pos"),
        Index(
            "uq_bv_active_header",
            "bom_header_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        UniqueConstraint("bom_header_id", "version_no", name="uq_bv_header_version"),
        {"schema": "production"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    bom_header_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("production.bom_headers.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    recipe_template_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("production.recipe_templates.id", ondelete="RESTRICT"),
        nullable=True,
    )
    expected_yield_pkts: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, server_default="1.0000"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="'DRAFT'")
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    activated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    bom_header: Mapped[BomHeader] = relationship(back_populates="versions")
    components: Mapped[list["BomComponent"]] = relationship(
        back_populates="bom_version", order_by="BomComponent.sort_order.asc()"
    )


class BomComponent(Base):
    """Single ingredient or packaging line belonging to an immutable BomVersion."""

    __tablename__ = "bom_components"
    __table_args__ = (
        CheckConstraint("input_role IN ('COOKING_RAW', 'PACKAGING')", name="bc_role_enum"),
        CheckConstraint("std_qty_base > 0", name="bc_qty_pos"),
        CheckConstraint("display_qty > 0", name="bc_disp_qty_pos"),
        UniqueConstraint("bom_version_id", "material_id", name="uq_bc_version_material"),
        {"schema": "production"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    bom_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("production.bom_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    material_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("production.materials.id", ondelete="RESTRICT"),
        nullable=False,
    )
    input_role: Mapped[str] = mapped_column(String(20), nullable=False)
    std_qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    display_qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    display_uom: Mapped[str] = mapped_column(String(16), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    bom_version: Mapped[BomVersion] = relationship(back_populates="components")


class ProductionRun(Base):
    """Production batch header pinned deterministically to its originating BomVersion."""

    __tablename__ = "production_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','PLANNED','IN_PROGRESS','COMPLETED','POSTED','CANCELLED')",
            name="pr_status_enum",
        ),
        CheckConstraint("batch_multiplier > 0", name="pr_batch_mult_pos"),
        CheckConstraint("expected_output_pkts > 0", name="pr_expected_pos"),
        CheckConstraint("actual_good_output_pkts >= 0", name="pr_actual_non_neg"),
        CheckConstraint("rejected_output_pkts >= 0", name="pr_rejected_non_neg"),
        CheckConstraint("version >= 1", name="pr_version_pos"),
        Index("idx_prun_status_date", "status", text("run_date DESC"), text("id DESC")),
        {"schema": "production"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    pack_size_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"), nullable=False
    )
    bom_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("production.bom_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_multiplier: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    expected_output_pkts: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_good_output_pkts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rejected_output_pkts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="'DRAFT'")
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supervisor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    posted_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    quality_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    material_issues: Mapped[list["ProductionMaterialIssue"]] = relationship(
        back_populates="production_run", order_by="ProductionMaterialIssue.id.asc()"
    )
    outputs: Mapped[list["ProductionOutput"]] = relationship(
        back_populates="production_run", order_by="ProductionOutput.id.asc()"
    )
    wastages: Mapped[list["ProductionWastage"]] = relationship(
        back_populates="production_run", order_by="ProductionWastage.id.asc()"
    )
    variances: Mapped[list["ProductionVariance"]] = relationship(
        back_populates="production_run", order_by="ProductionVariance.id.asc()"
    )


class ProductionMaterialIssue(Base):
    """Distinguishes planned, issued, actual consumed, unused returned, and wasted material per run."""

    __tablename__ = "production_material_issues"
    __table_args__ = (
        CheckConstraint("issue_phase IN ('RAW_ISSUE', 'PACKAGING_PACK')", name="pmi_phase_enum"),
        CheckConstraint("planned_qty_base >= 0", name="pmi_planned_non_neg"),
        CheckConstraint("issued_qty_base >= 0", name="pmi_issued_non_neg"),
        CheckConstraint("actual_consumed_qty_base >= 0", name="pmi_consumed_non_neg"),
        CheckConstraint("actual_good_used_base >= 0", name="pmi_good_non_neg"),
        CheckConstraint("damaged_qty_base >= 0", name="pmi_damaged_non_neg"),
        CheckConstraint("returned_unused_qty_base >= 0", name="pmi_returned_non_neg"),
        CheckConstraint("wasted_qty_base >= 0", name="pmi_wasted_non_neg"),
        CheckConstraint("cost_absorbed_paisa >= 0", name="pmi_cost_non_neg"),
        UniqueConstraint(
            "production_run_id", "material_id", "issue_phase", name="uq_pmi_run_mat_phase"
        ),
        {"schema": "production"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    production_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("production.production_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    material_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("production.materials.id", ondelete="RESTRICT"),
        nullable=False,
    )
    issue_phase: Mapped[str] = mapped_column(String(20), nullable=False)
    planned_qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    issued_qty_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0"
    )
    actual_consumed_qty_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0"
    )
    actual_good_used_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0"
    )
    damaged_qty_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0"
    )
    returned_unused_qty_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0"
    )
    wasted_qty_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, server_default="0"
    )
    cost_absorbed_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    issued_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=True
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    production_run: Mapped[ProductionRun] = relationship(back_populates="material_issues")


class ProductionOutput(Base):
    """Finished product good & rejected output record with food-grade batch traceability."""

    __tablename__ = "production_outputs"
    __table_args__ = (
        CheckConstraint("good_qty_pkts >= 0", name="po_good_qty_non_neg"),
        CheckConstraint("rejected_qty_pkts >= 0", name="po_rej_qty_non_neg"),
        CheckConstraint(
            "good_qty_pkts + rejected_qty_pkts > 0", name="po_total_output_pos"
        ),
        {"schema": "production"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    production_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("production.production_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    pack_size_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"), nullable=False
    )
    good_qty_pkts: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_qty_pkts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    batch_code: Mapped[str] = mapped_column(String(40), nullable=False)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    quality_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    production_run: Mapped[ProductionRun] = relationship(back_populates="outputs")


class ProductionWastage(Base):
    """Separate record of damaged packaging, raw wastage, or rejected finished goods."""

    __tablename__ = "production_wastages"
    __table_args__ = (
        CheckConstraint(
            "wastage_type IN ('DAMAGED_PACKAGING','RAW_MATERIAL_WASTAGE','REJECTED_FINISHED_GOOD','COOKING_SCRAP','BURNT_BATCH','SPILLAGE','OTHER')",
            name="pw_type_enum",
        ),
        CheckConstraint("qty_base > 0", name="pw_qty_pos"),
        CheckConstraint("cost_impact_paisa >= 0", name="pw_cost_non_neg"),
        {"schema": "production"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    production_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("production.production_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    material_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("production.materials.id", ondelete="RESTRICT"),
        nullable=True,
    )
    pack_size_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("sales.pack_sizes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    wastage_type: Mapped[str] = mapped_column(String(28), nullable=False)
    qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    uom: Mapped[str] = mapped_column(String(16), nullable=False)
    cost_impact_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam.users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    production_run: Mapped[ProductionRun] = relationship(back_populates="wastages")


class ProductionVariance(Base):
    """Deterministic planned-vs-actual variance record preserving formula & reproducibility."""

    __tablename__ = "production_variances"
    __table_args__ = (
        CheckConstraint(
            "variance_scope IN ('YIELD','RAW_CONSUMPTION','PACKAGING_BATCH_BOM','PACKAGING_OUTPUT_SCALED')",
            name="pv_scope_enum",
        ),
        CheckConstraint("planned_qty_base >= 0", name="pv_planned_non_neg"),
        CheckConstraint("actual_qty_base >= 0", name="pv_actual_non_neg"),
        CheckConstraint("tolerance_pct >= 0", name="pv_tolerance_non_neg"),
        {"schema": "production"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    production_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("production.production_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    variance_scope: Mapped[str] = mapped_column(String(28), nullable=False)
    material_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("production.materials.id", ondelete="RESTRICT"),
        nullable=True,
    )
    planned_qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    actual_qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    variance_qty_base: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    variance_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    tolerance_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    formula_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    production_run: Mapped[ProductionRun] = relationship(back_populates="variances")
