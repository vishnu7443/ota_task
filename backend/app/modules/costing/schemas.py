"""Pydantic schemas for Phase 9 Product Costing, Batch Overheads & Variance Costing."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class AddRunOverheadRequest(BaseModel):
    overhead_type: str = Field(
        pattern=r"^(DIRECT_LABOUR|GAS_POWER|PACKAGING_LABOUR|FACTORY_RENT|MACHINE_DEPRECIATION|OTHER_PRODUCTION_EXPENSE)$"
    )
    amount_paisa: int = Field(gt=0, le=1_000_000_000)
    notes: str | None = Field(default=None, max_length=500)


class FinalizeRunCostingRequest(BaseModel):
    overheads: list[AddRunOverheadRequest] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=500)


class AddMonthlyPoolOverheadRequest(BaseModel):
    period_month: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")
    overhead_type: str = Field(
        pattern=r"^(DIRECT_LABOUR|GAS_POWER|PACKAGING_LABOUR|FACTORY_RENT|MACHINE_DEPRECIATION|OTHER_PRODUCTION_EXPENSE)$"
    )
    amount_paisa: int = Field(gt=0, le=1_000_000_000)
    notes: str | None = Field(default=None, max_length=500)


class VoidOverheadRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 5:
            raise ValueError("Reason must be at least 5 non-whitespace characters.")
        return s


class ProductionOverheadOut(BaseModel):
    id: int
    production_run_id: int | None = None
    period_month: str
    overhead_type: str
    allocation_scope: str
    amount_paisa: int
    notes: str | None = None
    is_voided: bool
    void_reason: str | None = None
    voided_by_name: str | None = None
    voided_at: datetime | None = None
    recorded_by_name: str
    recorded_at: datetime


class MaterialCostLineOut(BaseModel):
    material_id: int
    material_code: str
    material_name: str
    issue_phase: str
    display_uom: str
    planned_qty_base: Decimal
    actual_consumed_qty_base: Decimal
    damaged_qty_base: Decimal
    wasted_qty_base: Decimal
    returned_unused_qty_base: Decimal
    planned_cost_paisa: int
    actual_cost_paisa: int
    damaged_cost_paisa: int
    wasted_cost_paisa: int
    cost_variance_paisa: int


class ProductionCostSummaryOut(BaseModel):
    id: int
    production_run_id: int
    run_number: str
    run_date: date
    pack_size_id: int
    sku_code: str
    display_name: str
    snapshot_version: int
    is_current: bool
    cost_status: str
    valuation_method: str
    planned_raw_cost_paisa: int
    planned_pkg_cost_paisa: int
    planned_overhead_cost_paisa: int
    planned_total_cost_paisa: int
    planned_cost_per_packet_paisa: Decimal
    raw_material_cost_paisa: int
    good_packaging_cost_paisa: int
    damaged_packaging_cost_paisa: int
    packaging_cost_paisa: int
    raw_wastage_cost_paisa: int
    rejected_output_cost_impact_paisa: int
    direct_labour_paisa: int
    gas_power_paisa: int
    other_direct_overhead_paisa: int
    direct_overhead_paisa: int
    allocated_overhead_paisa: int
    total_cost_paisa: int
    expected_output_pkts: int
    good_packets: int
    rejected_packets: int
    cost_per_packet_paisa: int | None = None
    exact_cost_per_packet_paisa: Decimal | None = None
    selling_price_snapshot_paisa: int
    gross_margin_per_pkt_paisa: int | None = None
    gross_margin_pct: Decimal | None = None
    material_variance_paisa: int
    cost_per_pkt_variance_paisa: int | None = None
    material_lines: list[MaterialCostLineOut] = Field(default_factory=list)
    notes: str | None = None
    computed_by_name: str
    computed_at: datetime


class RunCostingDetailOut(BaseModel):
    production_run_id: int
    run_number: str
    sku_code: str
    display_name: str
    run_status: str
    run_date: date
    current_summary: ProductionCostSummaryOut | None = None
    history_snapshots: list[ProductionCostSummaryOut] = Field(default_factory=list)
    overheads: list[ProductionOverheadOut] = Field(default_factory=list)


class ProductCostAggregateOut(BaseModel):
    pack_size_id: int
    sku_code: str
    display_name: str
    run_count: int
    total_good_packets: int
    total_rejected_packets: int
    total_raw_cost_paisa: int
    total_pkg_cost_paisa: int
    total_overhead_cost_paisa: int
    total_cost_paisa: int
    weighted_avg_cost_per_pkt_paisa: int
    latest_cost_per_pkt_paisa: int
    selling_price_paisa: int
    unit_gross_margin_paisa: int
    unit_gross_margin_pct: Decimal


class CostingDashboardOut(BaseModel):
    valuation_method: str
    total_costed_runs: int
    total_finalized_runs: int
    total_good_packets: int
    total_batch_cost_paisa: int
    total_wastage_and_damage_paisa: int
    runs: list[ProductionCostSummaryOut]
    product_summaries: list[ProductCostAggregateOut]
    monthly_pools: list[ProductionOverheadOut]
