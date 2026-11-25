"""Pydantic schemas for Phase 8 GST Billing, Credit Notes, Dispatch, Delivery Tracking & Reports."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ── Invoices ────────────────────────────────────────────────────────────────


class InvoiceDiscountOverride(BaseModel):
    sales_order_item_id: int = Field(gt=0)
    discount_paisa: int = Field(ge=0)


class CreateInvoiceRequest(BaseModel):
    sales_order_id: int = Field(gt=0)
    invoice_date: date | None = None
    apply_round_off: bool = False
    notes: str | None = Field(default=None, max_length=1000)
    item_discounts: list[InvoiceDiscountOverride] = Field(default_factory=list)
    issue_immediately: bool = False


class VerifyInvoiceRequest(BaseModel):
    remarks: str | None = Field(default=None, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)


class IssueInvoiceRequest(BaseModel):
    verification_remarks: str | None = Field(default=None, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)


class InvoiceItemOut(BaseModel):
    id: int
    sales_order_item_id: int
    pack_size_id: int
    sku_code: str
    product_name: str
    description: str
    hsn_code: str
    qty_pkts: int
    uom: str
    unit_price_paisa: int
    discount_paisa: int
    taxable_paisa: int
    gst_rate_bps: int
    cgst_rate_bps: int
    sgst_rate_bps: int
    igst_rate_bps: int
    cgst_paisa: int
    sgst_paisa: int
    igst_paisa: int
    line_total_paisa: int
    dispatched_qty_pkts: int = 0
    remaining_dispatch_qty_pkts: int = 0


class InvoiceTaxComponentOut(BaseModel):
    id: int
    hsn_code: str
    tax_type: str
    rate_bps: int
    taxable_base_paisa: int
    tax_amount_paisa: int


class ReadyForBillingOrderOut(BaseModel):
    sales_order_id: int
    order_number: str
    order_date: date
    customer_id: int
    customer_name: str
    customer_gstin: str | None = None
    place_of_supply_state_code: str
    place_of_supply_state_name: str
    supply_type: str
    total_packets: int
    taxable_total_paisa: int
    estimated_tax_paisa: int
    estimated_grand_total_paisa: int
    approved_at: datetime | None = None


class InvoiceSummaryOut(BaseModel):
    id: int
    draft_ref: str
    invoice_number: str | None = None
    financial_year: str
    sales_order_id: int
    order_number: str
    customer_id: int
    customer_name: str
    buyer_gstin: str | None = None
    place_of_supply_state_code: str
    place_of_supply_state_name: str
    nature_of_supply: str
    supply_type: str
    invoice_date: date
    due_date: date
    doc_status: str
    payment_status: str
    dispatch_status: str
    taxable_total_paisa: int
    cgst_total_paisa: int
    sgst_total_paisa: int
    igst_total_paisa: int
    round_off_paisa: int
    grand_total_paisa: int
    credited_paisa: int
    paid_paisa: int
    outstanding_paisa: int
    total_qty_pkts: int = 0
    dispatched_qty_pkts: int = 0
    remaining_dispatch_qty_pkts: int = 0
    issued_at: datetime | None = None
    created_at: datetime


# ── Credit Notes ────────────────────────────────────────────────────────────


class CreditNoteItemInput(BaseModel):
    invoice_item_id: int = Field(gt=0)
    qty_pkts: int = Field(ge=0)
    taxable_override_paisa: int | None = Field(default=None, ge=0)
    return_disposition: str = Field(
        default="NONE_NOT_DISPATCHED",
        pattern=r"^(NONE_NOT_DISPATCHED|RESTOCK_SELLABLE|SCRAP_DAMAGED)$",
    )


class CreateCreditNoteRequest(BaseModel):
    original_invoice_id: int = Field(gt=0)
    note_type: str = Field(
        pattern=r"^(INVOICE_CANCELLATION|SALES_RETURN|VALUE_ADJUSTMENT)$"
    )
    issue_date: date | None = None
    reason: str = Field(min_length=5, max_length=500)
    cancel_original_invoice: bool = False
    items: list[CreditNoteItemInput] = Field(default_factory=list)
    issue_immediately: bool = True

    @field_validator("reason")
    @classmethod
    def check_reason(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 5:
            raise ValueError("Reason must be at least 5 non-whitespace characters.")
        return s


class CreditNoteItemOut(BaseModel):
    id: int
    invoice_item_id: int
    pack_size_id: int
    sku_code: str
    description: str
    qty_pkts: int
    return_disposition: str
    taxable_reversed_paisa: int
    cgst_reversed_paisa: int
    sgst_reversed_paisa: int
    igst_reversed_paisa: int
    line_total_reversed_paisa: int


class CreditNoteOut(BaseModel):
    id: int
    draft_ref: str
    cn_number: str | None = None
    financial_year: str
    original_invoice_id: int
    original_invoice_number: str | None = None
    customer_id: int
    customer_name: str
    supply_type: str
    note_type: str
    issue_date: date
    reason: str
    status: str
    cancel_original_invoice: bool
    taxable_reversed_paisa: int
    cgst_reversed_paisa: int
    sgst_reversed_paisa: int
    igst_reversed_paisa: int
    round_off_reversed_paisa: int
    total_reversed_paisa: int
    created_by_name: str
    approved_by_name: str | None = None
    issued_by_name: str | None = None
    issued_at: datetime | None = None
    created_at: datetime
    items: list[CreditNoteItemOut]


# ── Dispatches & Delivery Tracking ──────────────────────────────────────────


class DispatchItemInput(BaseModel):
    invoice_item_id: int = Field(gt=0)
    dispatched_qty_pkts: int = Field(gt=0)
    batch_code_ref: str | None = Field(default=None, max_length=120)


class CreateDispatchRequest(BaseModel):
    invoice_id: int = Field(gt=0)
    dispatch_date: date | None = None
    transporter_name: str | None = Field(default=None, max_length=120)
    vehicle_number: str | None = Field(default=None, max_length=40)
    lr_number: str | None = Field(default=None, max_length=64)
    packing_verified: bool = True
    packing_remarks: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=500)
    items: list[DispatchItemInput] = Field(min_length=1)
    post_immediately: bool = False


class DispatchActionRemarksRequest(BaseModel):
    remarks: str | None = Field(default=None, max_length=500)
    transporter_name: str | None = Field(default=None, max_length=120)
    vehicle_number: str | None = Field(default=None, max_length=40)
    lr_number: str | None = Field(default=None, max_length=64)
    expected_version: int | None = Field(default=None, ge=1)


class DeliveryItemConfirmation(BaseModel):
    dispatch_item_id: int = Field(gt=0)
    received_qty_pkts: int = Field(ge=0)
    discrepancy_remarks: str | None = Field(default=None, max_length=300)


class UpdateDeliveryStatusRequest(BaseModel):
    target_status: str = Field(pattern=r"^(IN_TRANSIT|DELIVERED|DELIVERY_EXCEPTION)$")
    delivery_date: date | None = None
    remarks: str | None = Field(default=None, max_length=500)
    exception_reason: str | None = Field(default=None, max_length=500)
    items: list[DeliveryItemConfirmation] = Field(default_factory=list)
    expected_version: int | None = Field(default=None, ge=1)


class DispatchItemOut(BaseModel):
    id: int
    invoice_item_id: int
    pack_size_id: int
    sku_code: str
    display_name: str
    dispatched_qty_pkts: int
    batch_code_ref: str | None = None
    received_qty_pkts: int | None = None
    discrepancy_qty_pkts: int
    discrepancy_remarks: str | None = None


class DispatchStatusHistoryOut(BaseModel):
    id: int
    from_status: str | None = None
    to_status: str
    changed_by_name: str
    reason: str | None = None
    changed_at: datetime


class DispatchOut(BaseModel):
    id: int
    dispatch_number: str
    invoice_id: int
    invoice_number: str | None = None
    sales_order_id: int
    order_number: str
    customer_id: int
    customer_name: str
    status: str
    dispatch_date: date
    transporter_name: str | None = None
    vehicle_number: str | None = None
    lr_number: str | None = None
    packing_verified: bool
    packing_remarks: str | None = None
    notes: str | None = None
    created_by_name: str
    created_at: datetime
    ready_by_name: str | None = None
    ready_at: datetime | None = None
    dispatched_by_name: str | None = None
    dispatched_at: datetime | None = None
    in_transit_at: datetime | None = None
    delivery_date: date | None = None
    delivery_confirmed_by_name: str | None = None
    delivery_confirmed_at: datetime | None = None
    delivery_remarks: str | None = None
    delivery_exception_reason: str | None = None
    version: int
    total_dispatched_pkts: int
    total_received_pkts: int
    items: list[DispatchItemOut]
    status_history: list[DispatchStatusHistoryOut]


class ReadyForDispatchInvoiceOut(BaseModel):
    invoice_id: int
    invoice_number: str
    sales_order_id: int
    order_number: str
    customer_id: int
    customer_name: str
    place_of_supply_state_code: str
    invoice_date: date
    dispatch_status: str
    total_qty_pkts: int
    dispatched_qty_pkts: int
    remaining_qty_pkts: int
    fg_on_hand_sufficient: bool


class InvoicePaymentAllocationOut(BaseModel):
    id: int
    payment_id: int
    payment_number: str
    payment_date: date
    payment_mode: str
    reference_no: str | None = None
    allocated_paisa: int
    status: str
    allocated_at: datetime
    reversal_reason: str | None = None


class InvoiceAuditOut(BaseModel):
    id: int
    actor_name: str
    actor_role: str
    action: str
    entity_table: str
    reason: str | None = None
    after_state: dict[str, Any] | None = None
    occurred_at: datetime


class InvoiceDetailOut(InvoiceSummaryOut):
    seller_legal_name: str
    seller_gstin: str
    seller_state_name: str
    seller_state_code: str
    seller_address: str
    customer_type: str
    billing_address_snapshot: str
    shipping_address_snapshot: str
    payment_terms: str
    discount_total_paisa: int
    amount_in_words: str
    notes: str | None = None
    legal_declaration: str
    tax_calculation_snapshot: dict[str, Any]
    created_by_name: str
    verified_by_name: str | None = None
    verified_at: datetime | None = None
    verification_remarks: str | None = None
    issued_by_name: str | None = None
    version: int
    items: list[InvoiceItemOut]
    tax_components: list[InvoiceTaxComponentOut]
    credit_notes: list[CreditNoteOut]
    dispatches: list[DispatchOut]
    allocations: list[InvoicePaymentAllocationOut] = Field(default_factory=list)
    audit_trail: list[InvoiceAuditOut]


# ── Dashboards & Reports ────────────────────────────────────────────────────


class BillingDashboardOut(BaseModel):
    ready_for_billing_count: int
    draft_invoices_count: int
    issued_invoices_count: int
    cancelled_invoices_count: int
    total_taxable_paisa: int
    total_cgst_paisa: int
    total_sgst_paisa: int
    total_igst_paisa: int
    total_invoiced_paisa: int
    total_credited_paisa: int
    total_outstanding_paisa: int
    ready_orders: list[ReadyForBillingOrderOut]
    invoices: list[InvoiceSummaryOut]


class DispatchDashboardOut(BaseModel):
    ready_for_dispatch_invoices_count: int
    created_count: int
    ready_count: int
    dispatched_count: int
    in_transit_count: int
    delivered_count: int
    exception_count: int
    ready_invoices: list[ReadyForDispatchInvoiceOut]
    dispatches: list[DispatchOut]


class SalesInvoiceRegisterRow(BaseModel):
    invoice_id: int
    invoice_number: str
    invoice_date: date
    financial_year: str
    order_number: str
    customer_name: str
    buyer_gstin: str | None = None
    place_of_supply_state_code: str
    nature_of_supply: str
    supply_type: str
    doc_status: str
    dispatch_status: str
    payment_status: str
    taxable_total_paisa: int
    cgst_total_paisa: int
    sgst_total_paisa: int
    igst_total_paisa: int
    round_off_paisa: int
    grand_total_paisa: int
    credited_paisa: int
    outstanding_paisa: int


class GstHsnReportRow(BaseModel):
    hsn_code: str
    supply_type: str
    tax_rate_bps: int
    taxable_value_paisa: int
    cgst_paisa: int
    sgst_paisa: int
    igst_paisa: int
    total_tax_paisa: int


class GstSummaryReportOut(BaseModel):
    gross_taxable_paisa: int
    gross_cgst_paisa: int
    gross_sgst_paisa: int
    gross_igst_paisa: int
    credited_taxable_paisa: int
    credited_cgst_paisa: int
    credited_sgst_paisa: int
    credited_igst_paisa: int
    net_taxable_paisa: int
    net_cgst_paisa: int
    net_sgst_paisa: int
    net_igst_paisa: int
    disclaimer: str
    hsn_rows: list[GstHsnReportRow]


class CustomerSalesSummaryRow(BaseModel):
    customer_id: int
    customer_name: str
    customer_type: str
    buyer_gstin: str | None = None
    state_code: str
    invoice_count: int
    total_qty_pkts: int
    taxable_paisa: int
    gst_paisa: int
    grand_total_paisa: int
    credited_paisa: int
    outstanding_paisa: int


class ProductSalesSummaryRow(BaseModel):
    pack_size_id: int
    sku_code: str
    description: str
    hsn_code: str
    total_qty_pkts: int
    taxable_paisa: int
    cgst_paisa: int
    sgst_paisa: int
    igst_paisa: int
    line_total_paisa: int


class DispatchRegisterRow(BaseModel):
    dispatch_id: int
    dispatch_number: str
    dispatch_date: date
    invoice_number: str
    order_number: str
    customer_name: str
    status: str
    transporter_name: str | None = None
    vehicle_number: str | None = None
    total_dispatched_pkts: int
    total_received_pkts: int
    delivery_date: date | None = None


class BillingReportsBundleOut(BaseModel):
    sales_register: list[SalesInvoiceRegisterRow]
    gst_summary: GstSummaryReportOut
    credit_notes: list[CreditNoteOut]
    dispatch_register: list[DispatchRegisterRow]
    customer_sales: list[CustomerSalesSummaryRow]
    product_sales: list[ProductSalesSummaryRow]
    outstanding_invoices: list[SalesInvoiceRegisterRow]
