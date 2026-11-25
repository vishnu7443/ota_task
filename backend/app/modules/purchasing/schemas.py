import re
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_STATE_RE = re.compile(r"^[0-9]{2}$")


class SupplierCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=160)
    contact_person: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=160)
    gstin: str | None = Field(default=None, max_length=15)
    state_name: str = Field(min_length=2, max_length=80)
    state_code: str = Field(min_length=2, max_length=2)
    address: str = Field(min_length=3, max_length=500)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def clean_code(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("state_code")
    @classmethod
    def check_state_code(cls, v: str) -> str:
        s = v.strip()
        if not _STATE_RE.match(s):
            raise ValueError("State code must be a 2-digit GST state code (e.g. '33').")
        return s

    @field_validator("gstin")
    @classmethod
    def check_gstin(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        s = v.strip().upper()
        if not _GSTIN_RE.match(s):
            raise ValueError("GSTIN must match 15-character Indian GST format.")
        return s

    @model_validator(mode="after")
    def validate_gstin_state_prefix(self) -> "SupplierCreateRequest":
        if self.gstin and self.gstin[:2] != self.state_code:
            raise ValueError("GSTIN first 2 digits must match supplier state_code.")
        return self


class SupplierUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    contact_person: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=160)
    gstin: str | None = Field(default=None, max_length=15)
    state_name: str = Field(min_length=2, max_length=80)
    state_code: str = Field(min_length=2, max_length=2)
    address: str = Field(min_length=3, max_length=500)
    is_active: bool = True

    @field_validator("state_code")
    @classmethod
    def check_state_code(cls, v: str) -> str:
        s = v.strip()
        if not _STATE_RE.match(s):
            raise ValueError("State code must be a 2-digit GST state code.")
        return s

    @field_validator("gstin")
    @classmethod
    def check_gstin(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        s = v.strip().upper()
        if not _GSTIN_RE.match(s):
            raise ValueError("GSTIN must match 15-character Indian GST format.")
        return s

    @model_validator(mode="after")
    def validate_gstin_state_prefix(self) -> "SupplierUpdateRequest":
        if self.gstin and self.gstin[:2] != self.state_code:
            raise ValueError("GSTIN first 2 digits must match supplier state_code.")
        return self


class SupplierResponse(BaseModel):
    id: int
    code: str
    name: str
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    gstin: str | None = None
    state_name: str
    state_code: str
    address: str
    is_active: bool
    po_count: int = 0
    receipt_count: int = 0
    total_purchased_paisa: int = 0
    created_at: datetime
    updated_at: datetime


class PurchaseOrderItemInput(BaseModel):
    material_id: int = Field(gt=0)
    entered_qty: Decimal = Field(gt=0)
    entered_uom: str = Field(min_length=1, max_length=16)
    unit_rate_paisa: int = Field(ge=0, le=100_000_000)
    gst_rate_bps: int = Field(default=0, ge=0, le=2800)


class PurchaseOrderCreateRequest(BaseModel):
    supplier_id: int = Field(gt=0)
    order_date: date | None = None
    expected_date: date | None = None
    notes: str | None = Field(default=None, max_length=500)
    submit_immediately: bool = False
    items: list[PurchaseOrderItemInput] = Field(min_length=1, max_length=50)

    @field_validator("items")
    @classmethod
    def unique_materials(cls, items: list[PurchaseOrderItemInput]) -> list[PurchaseOrderItemInput]:
        seen: set[int] = set()
        for it in items:
            if it.material_id in seen:
                raise ValueError(f"Duplicate material_id ({it.material_id}) in purchase order.")
            seen.add(it.material_id)
        return items


class PurchaseOrderActionReasonRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def check_reason(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 5:
            raise ValueError("Reason must be at least 5 non-whitespace characters.")
        return s


class PurchaseOrderItemResponse(BaseModel):
    id: int
    material_id: int
    material_code: str
    material_name: str
    material_category: str
    base_uom: str
    display_uom: str
    entered_qty: Decimal
    entered_uom: str
    ordered_qty_base: Decimal
    received_qty_base: Decimal
    rejected_qty_base: Decimal
    remaining_qty_base: Decimal
    unit_rate_paisa: int
    gst_rate_bps: int
    line_subtotal_paisa: int
    line_tax_paisa: int
    line_total_paisa: int


class PurchaseOrderSummaryResponse(BaseModel):
    id: int
    po_number: str
    supplier_id: int
    supplier_code: str
    supplier_name: str
    order_date: date
    expected_date: date | None = None
    status: str
    subtotal_paisa: int
    tax_paisa: int
    total_paisa: int
    notes: str | None = None
    rejection_reason: str | None = None
    created_by_name: str
    approved_by_name: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    item_count: int = 0


class GoodsReceiptItemInput(BaseModel):
    purchase_order_item_id: int | None = Field(default=None, gt=0)
    material_id: int = Field(gt=0)
    entered_uom: str = Field(min_length=1, max_length=16)
    received_qty_entered: Decimal = Field(gt=0)
    rejected_qty_entered: Decimal = Field(default=Decimal(0), ge=0)
    unit_rate_paisa: int | None = Field(default=None, ge=0, le=100_000_000)
    gst_rate_bps: int | None = Field(default=None, ge=0, le=2800)
    batch_code: str | None = Field(default=None, max_length=40)
    expiry_date: date | None = None
    rejection_reason: str | None = Field(default=None, max_length=500)
    allow_excess: bool = False

    @model_validator(mode="after")
    def validate_rejected_vs_received(self) -> "GoodsReceiptItemInput":
        if self.rejected_qty_entered > self.received_qty_entered:
            raise ValueError("Rejected/damaged quantity cannot exceed total received quantity.")
        if self.rejected_qty_entered > 0 and (
            not self.rejection_reason or len(self.rejection_reason.strip()) < 3
        ):
            raise ValueError("Rejection reason is required when recording rejected/damaged quantity.")
        return self


class GoodsReceiptCreateRequest(BaseModel):
    client_receipt_id: UUID
    purchase_order_id: int | None = Field(default=None, gt=0)
    supplier_id: int | None = Field(default=None, gt=0)
    supplier_bill_ref: str | None = Field(default=None, max_length=64)
    receipt_date: date | None = None
    discrepancy_notes: str | None = Field(default=None, max_length=500)
    submit_immediately: bool = False
    items: list[GoodsReceiptItemInput] = Field(min_length=1, max_length=50)


class GoodsReceiptItemResponse(BaseModel):
    id: int
    purchase_order_item_id: int | None = None
    material_id: int
    material_code: str
    material_name: str
    base_uom: str
    display_uom: str
    entered_uom: str
    received_qty_entered: Decimal
    rejected_qty_entered: Decimal
    accepted_qty_entered: Decimal
    received_qty_base: Decimal
    rejected_qty_base: Decimal
    accepted_qty_base: Decimal
    entered_unit_rate_paisa: int
    gst_rate_bps: int
    unit_cost_paisa_per_base: Decimal
    line_subtotal_paisa: int
    line_tax_paisa: int
    line_total_paisa: int
    batch_code: str | None = None
    expiry_date: date | None = None
    rejection_reason: str | None = None


class GoodsReceiptSummaryResponse(BaseModel):
    id: int
    receipt_number: str
    client_receipt_id: UUID
    purchase_order_id: int | None = None
    po_number: str | None = None
    supplier_id: int
    supplier_code: str
    supplier_name: str
    supplier_bill_ref: str | None = None
    receipt_date: date
    status: str
    subtotal_paisa: int
    input_gst_paisa: int
    total_paisa: int
    discrepancy_notes: str | None = None
    is_duplicate_replay: bool = False
    received_by_name: str
    verified_by_name: str | None = None
    posted_by_name: str | None = None
    posted_at: datetime | None = None
    created_at: datetime


class GoodsReceiptDetailResponse(GoodsReceiptSummaryResponse):
    items: list[GoodsReceiptItemResponse]


class PurchaseOrderDetailResponse(PurchaseOrderSummaryResponse):
    items: list[PurchaseOrderItemResponse]
    receipts: list[GoodsReceiptSummaryResponse] = []


class SupplierDetailResponse(SupplierResponse):
    purchase_orders: list[PurchaseOrderSummaryResponse] = []
    purchase_receipts: list[GoodsReceiptSummaryResponse] = []
