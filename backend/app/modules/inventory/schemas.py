from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class MaterialSummaryResponse(BaseModel):
    id: int
    code: str
    name: str
    material_category: str
    unit_dimension: str
    base_uom: str
    display_uom: str
    reorder_level_base: Decimal
    is_active: bool


class InventoryBalanceSummaryResponse(BaseModel):
    item_type: str  # "MATERIAL" | "PACK_SIZE"
    item_id: int
    item_category: str  # RAW_MATERIAL | PACKAGING_MATERIAL | FINISHED_GOOD
    code: str
    name: str
    unit_dimension: str
    base_uom: str
    display_uom: str
    display_factor: Decimal
    reorder_level_base: Decimal
    opening_qty_base: Decimal
    received_qty_base: Decimal
    issued_qty_base: Decimal
    dispatched_qty_base: Decimal
    adjusted_qty_base: Decimal
    physical_qty_base: Decimal
    reserved_qty_base: Decimal
    available_qty_base: Decimal
    is_low_stock: bool
    open_lot_value_paisa: int


class InventoryLedgerEntryResponse(BaseModel):
    id: int
    occurred_at: datetime
    item_category: str
    item_type: str
    item_id: int
    item_code: str
    item_name: str
    base_uom: str
    display_uom: str
    movement_type: str
    entered_qty: Decimal | None = None
    entered_uom: str | None = None
    signed_qty_base: Decimal
    unit_cost_paisa_per_base: Decimal
    total_cost_paisa: int
    source_doc_type: str
    reference_code: str | None = None
    notes: str | None = None
    actor_name: str
    opening_balance_id: int | None = None
    purchase_receipt_item_id: int | None = None
    stock_adjustment_id: int | None = None


class StockAdjustmentCreateRequest(BaseModel):
    item_type: str = Field(pattern="^(MATERIAL|PACK_SIZE)$")
    item_id: int = Field(gt=0)
    adjustment_type: str = Field(
        pattern="^(DAMAGED|EXPIRED|MISSING|COUNT_CORRECTION|SUPPLIER_RETURN|OTHER)$"
    )
    entered_qty: Decimal
    entered_uom: str = Field(min_length=1, max_length=16)
    unit_cost_paisa_per_base: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=5, max_length=500)
    post_immediately: bool = False

    @field_validator("entered_qty")
    @classmethod
    def check_nonzero(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("Adjustment quantity cannot be zero.")
        return v

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 5:
            raise ValueError("Reason must be at least 5 non-whitespace characters.")
        return s


class StockAdjustmentActionReasonRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 5:
            raise ValueError("Reason must be at least 5 non-whitespace characters.")
        return s


class StockAdjustmentResponse(BaseModel):
    id: int
    adjustment_number: str
    item_category: str
    item_type: str
    item_id: int
    item_code: str
    item_name: str
    base_uom: str
    display_uom: str
    adjustment_type: str
    entered_qty: Decimal
    entered_uom: str
    delta_qty_base: Decimal
    unit_cost_paisa_per_base: Decimal
    reason: str
    status: str
    requested_by_name: str
    approved_by_name: str | None = None
    rejection_reason: str | None = None
    requested_at: datetime
    posted_at: datetime | None = None


class InventoryDashboardResponse(BaseModel):
    total_items: int
    raw_material_count: int
    packaging_material_count: int
    finished_good_count: int
    low_stock_count: int
    pending_adjustments_count: int
    total_stock_value_paisa: int
    items: list[InventoryBalanceSummaryResponse]


class PurchaseReceiptReportRow(BaseModel):
    receipt_id: int
    receipt_number: str
    receipt_date: date
    po_number: str | None = None
    supplier_code: str
    supplier_name: str
    material_code: str
    material_name: str
    entered_uom: str
    received_qty_entered: Decimal
    rejected_qty_entered: Decimal
    accepted_qty_entered: Decimal
    accepted_qty_base: Decimal
    base_uom: str
    entered_unit_rate_paisa: int
    line_total_paisa: int
    batch_code: str | None = None
    status: str


class StockReportsSummaryResponse(BaseModel):
    current_stock: list[InventoryBalanceSummaryResponse]
    low_stock_items: list[InventoryBalanceSummaryResponse]
    purchase_receipts: list[PurchaseReceiptReportRow]
    adjustments: list[StockAdjustmentResponse]
