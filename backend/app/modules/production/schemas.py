"""Pydantic request and response schemas for Phase 7 BOM & Production Management."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

# ── Catalog & Recipe Templates ──────────────────────────────────────────────


class ProductOut(BaseModel):
    id: int
    product_code: str
    name: str
    category: str
    hsn_code: str
    gst_rate_bps: int
    is_active: bool


class PackSizeOut(BaseModel):
    id: int
    product_id: int
    product_code: str
    product_name: str
    sku_code: str
    display_name: str
    pack_weight_g: int
    packets_per_carton: int
    base_selling_price_paisa: int
    is_active: bool
    has_active_bom: bool
    active_bom_version_no: int | None = None


class RecipeTemplateOut(BaseModel):
    id: int
    code: str
    name: str
    product_id: int | None = None
    base_yield_weight_g: Decimal
    notes: str | None = None
    is_active: bool


class ProductionCatalogOut(BaseModel):
    products: list[ProductOut]
    pack_sizes: list[PackSizeOut]
    recipe_templates: list[RecipeTemplateOut]


class CreatePackSizeRequest(BaseModel):
    product_id: int = Field(gt=0)
    sku_code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Z0-9\-_]+$")
    display_name: str = Field(min_length=3, max_length=140)
    pack_weight_g: int = Field(gt=0)
    packets_per_carton: int = Field(gt=0)
    base_selling_price_paisa: int = Field(ge=0, default=0)


class CreateMaterialRequest(BaseModel):
    code: str = Field(min_length=3, max_length=32, pattern=r"^[A-Z0-9\-_]+$")
    name: str = Field(min_length=2, max_length=120)
    material_category: str = Field(pattern=r"^(RAW_MATERIAL|PACKAGING_MATERIAL)$")
    unit_dimension: str = Field(pattern=r"^(MASS|VOLUME|COUNT)$")
    display_uom: str = Field(min_length=1, max_length=16)
    reorder_level_display: Decimal = Field(ge=0, default=Decimal(0))


# ── BOM Management ──────────────────────────────────────────────────────────


class BomComponentOut(BaseModel):
    id: int
    material_id: int
    material_code: str
    material_name: str
    material_category: str
    unit_dimension: str
    input_role: str
    std_qty_base: Decimal
    display_qty: Decimal
    display_uom: str
    base_uom: str
    sort_order: int


class BomVersionOut(BaseModel):
    id: int
    bom_header_id: int
    version_no: int
    recipe_template_id: int | None = None
    recipe_template_name: str | None = None
    expected_yield_pkts: int
    batch_multiplier: Decimal
    status: str
    effective_date: date | None = None
    notes: str | None = None
    created_by_name: str
    activated_by_name: str | None = None
    activated_at: datetime | None = None
    created_at: datetime
    run_count: int = 0
    is_locked: bool = False
    components: list[BomComponentOut]


class BomHeaderOut(BaseModel):
    id: int
    pack_size_id: int
    sku_code: str
    display_name: str
    product_id: int
    product_name: str
    pack_weight_g: int
    packets_per_carton: int
    active_version_id: int | None = None
    active_version: BomVersionOut | None = None
    all_versions: list[BomVersionOut]


class BomComponentInput(BaseModel):
    material_id: int = Field(gt=0)
    input_role: str = Field(pattern=r"^(COOKING_RAW|PACKAGING)$")
    display_qty: Decimal = Field(gt=0)
    display_uom: str = Field(min_length=1, max_length=16)


class CreateBomVersionRequest(BaseModel):
    pack_size_id: int = Field(gt=0)
    recipe_template_id: int | None = Field(default=None, gt=0)
    expected_yield_pkts: int = Field(gt=0)
    effective_date: date | None = None
    notes: str | None = Field(default=None, max_length=1000)
    components: list[BomComponentInput] = Field(min_length=1)
    activate: bool = False


class UpdateDraftBomVersionRequest(BaseModel):
    expected_yield_pkts: int = Field(gt=0)
    effective_date: date | None = None
    notes: str | None = Field(default=None, max_length=1000)
    components: list[BomComponentInput] = Field(min_length=1)


# ── BOM Calculator ──────────────────────────────────────────────────────────


class MaterialRequirementOut(BaseModel):
    material_id: int
    material_code: str
    material_name: str
    material_category: str
    unit_dimension: str
    input_role: str
    bom_std_qty_base: Decimal
    exact_scaled_qty_base: Decimal
    standard_qty_base: Decimal
    was_rounded_up: bool
    rounding_note: str | None = None
    display_qty: Decimal
    display_uom: str
    base_uom: str
    display_factor: Decimal
    on_hand_qty_base: Decimal
    reserved_qty_base: Decimal
    available_qty_base: Decimal
    additional_required_base: Decimal
    is_shortage: bool


class BomCalculationOut(BaseModel):
    pack_size_id: int
    sku_code: str
    display_name: str
    bom_version_id: int
    version_no: int
    batch_multiplier: Decimal
    expected_output_pkts: int
    requirements: list[MaterialRequirementOut]
    has_shortages: bool
    shortage_summary: str


class BomCalculateRequest(BaseModel):
    pack_size_id: int = Field(gt=0)
    batch_multiplier: Decimal | None = Field(default=None, gt=0)
    target_output_pkts: int | None = Field(default=None, gt=0)
    bom_version_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_scale_mode(self) -> "BomCalculateRequest":
        if self.batch_multiplier is None and self.target_output_pkts is None:
            self.batch_multiplier = Decimal("1.0000")
        return self


# ── Production Run Lifecycle ────────────────────────────────────────────────


class CreateProductionRunRequest(BaseModel):
    pack_size_id: int = Field(gt=0)
    batch_multiplier: Decimal | None = Field(default=None, gt=0)
    target_output_pkts: int | None = Field(default=None, gt=0)
    run_date: date | None = None
    notes: str | None = Field(default=None, max_length=1000)
    plan_immediately: bool = False


class MaterialIssueInput(BaseModel):
    material_id: int = Field(gt=0)
    issued_qty: Decimal = Field(ge=0)
    issued_uom: str = Field(min_length=1, max_length=16)


class StartProductionRequest(BaseModel):
    items: list[MaterialIssueInput] = Field(min_length=1)
    require_all_bom_stock: bool = True
    notes: str | None = Field(default=None, max_length=500)


class MaterialConsumptionInput(BaseModel):
    material_id: int = Field(gt=0)
    actual_consumed_qty: Decimal | None = Field(default=None, ge=0)
    actual_good_used_qty: Decimal | None = Field(default=None, ge=0)
    damaged_packaging_qty: Decimal = Field(ge=0, default=Decimal(0))
    returned_unused_qty: Decimal = Field(ge=0, default=Decimal(0))
    wasted_qty: Decimal = Field(ge=0, default=Decimal(0))
    uom: str = Field(min_length=1, max_length=16)


class ExtraWastageInput(BaseModel):
    material_id: int | None = Field(default=None, gt=0)
    wastage_type: str = Field(
        pattern=r"^(DAMAGED_PACKAGING|RAW_MATERIAL_WASTAGE|REJECTED_FINISHED_GOOD|COOKING_SCRAP|BURNT_BATCH|SPILLAGE|OTHER)$"
    )
    qty: Decimal = Field(gt=0)
    uom: str = Field(min_length=1, max_length=16)
    reason: str = Field(min_length=3, max_length=500)


class CompleteProductionRequest(BaseModel):
    good_output_pkts: int = Field(ge=0)
    rejected_output_pkts: int = Field(ge=0, default=0)
    batch_code: str = Field(min_length=2, max_length=40)
    expiry_date: date | None = None
    quality_remarks: str | None = Field(default=None, max_length=1000)
    consumptions: list[MaterialConsumptionInput] = Field(min_length=1)
    extra_wastages: list[ExtraWastageInput] = []

    @model_validator(mode="after")
    def validate_total_output(self) -> "CompleteProductionRequest":
        if self.good_output_pkts + self.rejected_output_pkts <= 0:
            raise ValueError("Total output (good + rejected packets) must be greater than zero.")
        return self


class CancelProductionReturnItem(BaseModel):
    material_id: int = Field(gt=0)
    returned_qty: Decimal = Field(ge=0)
    uom: str = Field(min_length=1, max_length=16)


class CancelProductionRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
    returned_items: list[CancelProductionReturnItem] = []


class AcknowledgeAlertRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


# ── Production Run Outputs ──────────────────────────────────────────────────


class MaterialIssueOut(BaseModel):
    id: int
    material_id: int
    material_code: str
    material_name: str
    material_category: str
    issue_phase: str
    planned_qty_base: Decimal
    issued_qty_base: Decimal
    actual_consumed_qty_base: Decimal
    actual_good_used_base: Decimal
    damaged_qty_base: Decimal
    returned_unused_qty_base: Decimal
    wasted_qty_base: Decimal
    cost_absorbed_paisa: int
    display_uom: str
    base_uom: str
    display_factor: Decimal
    available_qty_base: Decimal
    issued_by_name: str | None = None
    issued_at: datetime | None = None


class ProductionOutputOut(BaseModel):
    id: int
    good_qty_pkts: int
    rejected_qty_pkts: int
    total_qty_pkts: int
    batch_code: str
    expiry_date: date | None = None
    quality_remarks: str | None = None
    recorded_by_name: str
    recorded_at: datetime


class WastageOut(BaseModel):
    id: int
    material_id: int | None = None
    material_code: str | None = None
    material_name: str | None = None
    pack_size_id: int | None = None
    wastage_type: str
    qty_base: Decimal
    uom: str
    cost_impact_paisa: int
    reason: str
    recorded_by_name: str
    recorded_at: datetime


class VarianceOut(BaseModel):
    id: int
    variance_scope: str
    material_id: int | None = None
    material_code: str | None = None
    material_name: str | None = None
    planned_qty_base: Decimal
    actual_qty_base: Decimal
    variance_qty_base: Decimal
    variance_pct: Decimal | None = None
    tolerance_pct: Decimal
    is_flagged: bool
    formula_explanation: str
    display_uom: str
    base_uom: str
    display_factor: Decimal
    computed_at: datetime


class VarianceAlertOut(BaseModel):
    id: int
    production_run_id: int
    run_number: str
    sku_code: str
    production_variance_id: int
    alert_type: str
    message: str
    status: str
    acknowledged_by_name: str | None = None
    acknowledged_at: datetime | None = None
    acknowledgement_note: str | None = None
    created_at: datetime


class ProductionRunOut(BaseModel):
    id: int
    run_number: str
    pack_size_id: int
    sku_code: str
    display_name: str
    packets_per_carton: int
    bom_version_id: int
    version_no: int
    bom_status: str
    bom_expected_yield_pkts: int
    batch_multiplier: Decimal
    expected_output_pkts: int
    actual_good_output_pkts: int
    rejected_output_pkts: int
    status: str
    run_date: date
    planned_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    posted_at: datetime | None = None
    cancelled_at: datetime | None = None
    supervisor_name: str
    posted_by_name: str | None = None
    quality_remarks: str | None = None
    notes: str | None = None
    total_material_cost_paisa: int
    material_issues: list[MaterialIssueOut]
    outputs: list[ProductionOutputOut]
    wastages: list[WastageOut]
    variances: list[VarianceOut]
    alerts: list[VarianceAlertOut]


class ProductionRunSummaryOut(BaseModel):
    id: int
    run_number: str
    pack_size_id: int
    sku_code: str
    display_name: str
    bom_version_id: int
    version_no: int
    batch_multiplier: Decimal
    expected_output_pkts: int
    actual_good_output_pkts: int
    rejected_output_pkts: int
    status: str
    run_date: date
    supervisor_name: str
    has_flagged_variance: bool
    open_alert_count: int
    damaged_packaging_qty: Decimal


class ShortageItemOut(BaseModel):
    material_id: int
    material_code: str
    material_name: str
    display_uom: str
    base_uom: str
    display_factor: Decimal
    required_qty_base: Decimal
    available_qty_base: Decimal
    shortage_qty_base: Decimal


class ProductionDashboardOut(BaseModel):
    total_runs: int
    draft_count: int
    planned_count: int
    in_progress_count: int
    completed_count: int
    posted_count: int
    cancelled_count: int
    total_expected_output_pkts: int
    total_good_output_pkts: int
    total_rejected_output_pkts: int
    total_damaged_packaging_units: Decimal
    flagged_variance_count: int
    open_alerts_count: int
    upcoming_shortages: list[ShortageItemOut]
    open_alerts: list[VarianceAlertOut]
    runs: list[ProductionRunSummaryOut]


class ProductionVarianceReportRow(BaseModel):
    run_id: int
    run_number: str
    run_date: date
    sku_code: str
    display_name: str
    bom_version_no: int
    batch_multiplier: Decimal
    expected_output_pkts: int
    actual_good_output_pkts: int
    rejected_output_pkts: int
    yield_variance_pct: Decimal | None = None
    oil_variance_pct: Decimal | None = None
    damaged_packaging_qty: Decimal
    status: str
    flagged_count: int
