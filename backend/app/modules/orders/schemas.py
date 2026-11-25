from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _require_non_blank_reason(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped


class OrderItemInput(BaseModel):
    pack_size_id: int = Field(gt=0)
    ordered_qty_pkts: int = Field(gt=0, le=1_000_000)


class CreateOrderRequest(BaseModel):
    customer_id: int = Field(gt=0)
    client_order_id: UUID
    notes: str | None = Field(default=None, max_length=500)
    items: list[OrderItemInput] = Field(min_length=1, max_length=50)

    @field_validator("items")
    @classmethod
    def ensure_unique_skus(cls, items: list[OrderItemInput]) -> list[OrderItemInput]:
        seen: set[int] = set()
        for item in items:
            if item.pack_size_id in seen:
                raise ValueError(f"Duplicate product SKU ({item.pack_size_id}) in order lines.")
            seen.add(item.pack_size_id)
        return items


class SalesmanResubmitRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=500)
    items: list[OrderItemInput] = Field(min_length=1, max_length=50)

    @field_validator("items")
    @classmethod
    def ensure_unique_skus(cls, items: list[OrderItemInput]) -> list[OrderItemInput]:
        seen: set[int] = set()
        for item in items:
            if item.pack_size_id in seen:
                raise ValueError(f"Duplicate product SKU ({item.pack_size_id}) in order lines.")
            seen.add(item.pack_size_id)
        return items


class AdminOrderItemAdjustment(BaseModel):
    id: int = Field(gt=0)
    approved_qty_pkts: int = Field(ge=0, le=1_000_000)
    unit_price_paisa: int = Field(ge=0, le=100_000_000)


class AdminModifyOrderRequest(BaseModel):
    items: list[AdminOrderItemAdjustment] = Field(default_factory=list)
    admin_remarks: str | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)


class AdminReviewHoldRequest(BaseModel):
    admin_remarks: str | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)


class AdminApproveRequest(BaseModel):
    admin_remarks: str | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)


class AdminReasonRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
    admin_remarks: str | None = Field(default=None, max_length=1000)
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("reason")
    @classmethod
    def check_reason_non_blank(cls, v: str) -> str:
        stripped = _require_non_blank_reason(v) or ""
        if len(stripped) < 5:
            raise ValueError("Reason must be at least 5 non-whitespace characters.")
        return stripped


class OrderReasonRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def check_reason_non_blank(cls, v: str) -> str:
        stripped = _require_non_blank_reason(v) or ""
        if len(stripped) < 5:
            raise ValueError("Reason must be at least 5 non-whitespace characters.")
        return stripped


class OrderItemDetail(BaseModel):
    id: int
    pack_size_id: int
    sku_code: str
    display_name: str
    hsn_code: str
    gst_rate_bps: int
    packets_per_carton: int
    ordered_qty_pkts: int
    approved_qty_pkts: int | None = None
    effective_qty_pkts: int
    original_unit_price_paisa: int
    unit_price_paisa: int
    is_qty_modified: bool = False
    is_price_modified: bool = False
    line_taxable_paisa: int
    live_on_hand_pkts: int
    live_reserved_pkts: int
    live_available_pkts: int
    shortage_pkts: int


class StatusHistoryEntry(BaseModel):
    id: int
    from_status: str | None = None
    to_status: str
    changed_by_name: str
    reason: str | None = None
    changed_at: datetime


class OrderApprovalRecord(BaseModel):
    id: int
    decision: str
    reviewed_by_name: str
    ordered_total_pkts: int
    available_total_pkts: int
    shortage_pkts: int
    stock_snapshot: dict[str, Any]
    remarks: str | None = None
    decided_at: datetime


class StockReservationRecord(BaseModel):
    id: int
    sales_order_item_id: int
    pack_size_id: int
    sku_code: str
    reserved_qty_pkts: int
    status: str
    reserved_by_name: str
    reserved_at: datetime
    released_by_name: str | None = None
    released_at: datetime | None = None
    release_reason: str | None = None


class OrderAuditEntry(BaseModel):
    id: int
    actor_user_id: int | None = None
    actor_name: str
    actor_role: str
    action: str
    entity_table: str
    entity_id: int
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    reason: str | None = None
    occurred_at: datetime


class TaxEstimateBreakdown(BaseModel):
    supply_type: str
    factory_state_code: str
    place_of_supply_state_code: str
    taxable_total_paisa: int
    cgst_total_paisa: int
    sgst_total_paisa: int
    igst_total_paisa: int
    grand_total_paisa: int


class OrderDispatchTrackingItem(BaseModel):
    id: int
    dispatch_number: str
    status: str
    dispatch_date: str
    delivery_date: str | None = None
    vehicle_number: str | None = None
    transporter_name: str | None = None
    total_dispatched_pkts: int
    total_received_pkts: int
    delivery_remarks: str | None = None
    delivery_exception_reason: str | None = None


class OrderSummaryResponse(BaseModel):
    id: int
    order_number: str
    client_order_id: UUID
    order_date: date
    status: str
    has_shortage: bool
    customer_id: int
    customer_code: str
    customer_name: str
    customer_type: str
    place_of_supply_state_code: str
    place_of_supply_state_name: str
    salesman_id: int
    salesman_name: str
    total_packets: int
    ordered_total_packets: int
    taxable_total_paisa: int
    estimated_grand_total_paisa: int
    admin_remarks: str | None = None
    rejection_reason: str | None = None
    cancellation_reason: str | None = None
    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    created_at: datetime
    invoice_id: int | None = None
    invoice_number: str | None = None
    invoice_doc_status: str | None = None
    invoice_dispatch_status: str | None = None
    invoice_paid_paisa: int | None = None
    invoice_outstanding_paisa: int | None = None
    invoice_payment_status: str | None = None


class OrderDetailResponse(OrderSummaryResponse):
    version: int = 1
    customer_gstin: str | None = None
    customer_phone: str | None = None
    salesman_employee_code: str | None = None
    salesman_territory: str | None = None
    notes: str | None = None
    approved_by_name: str | None = None
    rejected_by_name: str | None = None
    rejected_at: datetime | None = None
    cancelled_by_name: str | None = None
    cancelled_at: datetime | None = None
    is_duplicate_replay: bool = False
    invoice_grand_total_paisa: int | None = None
    tax_estimate: TaxEstimateBreakdown
    items: list[OrderItemDetail]
    status_history: list[StatusHistoryEntry]
    approvals: list[OrderApprovalRecord]
    reservations: list[StockReservationRecord] = []
    audit_trail: list[OrderAuditEntry] = []
    dispatches: list[OrderDispatchTrackingItem] = []


class PaginatedOrdersResponse(BaseModel):
    items: list[OrderSummaryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AdminOrdersSummaryResponse(BaseModel):
    total_count: int
    submitted_count: int
    under_review_count: int
    correction_requested_count: int
    pending_verification_count: int
    approved_count: int
    rejected_count: int
    cancelled_count: int
    shortage_count: int
    pending_value_paisa: int
    approved_value_paisa: int
