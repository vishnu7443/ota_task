"""Pydantic v2 schemas for Phase 9 Payments, Invoice Allocations, Refunds, AR, Ageing & Profitability."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AllocationLineInput(BaseModel):
    invoice_id: int = Field(gt=0)
    allocated_paisa: int = Field(gt=0, le=1_000_000_000)


class RecordPaymentRequest(BaseModel):
    customer_id: int = Field(gt=0)
    payment_date: date | None = None
    amount_paisa: int = Field(gt=0, le=1_000_000_000)
    payment_mode: str = Field(
        pattern=r"^(CASH|UPI|BANK_TRANSFER|NEFT|RTGS|IMPS|CHEQUE|CARD|OTHER)$"
    )
    reference_no: str | None = Field(default=None, max_length=80)
    remarks: str | None = Field(default=None, max_length=500)
    client_payment_id: UUID
    allocations: list[AllocationLineInput] = Field(default_factory=list, max_length=100)


class AllocatePaymentRequest(BaseModel):
    allocations: list[AllocationLineInput] = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)


class ReversePaymentRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("reason")
    @classmethod
    def check_reason(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 5:
            raise ValueError("Reversal reason must be at least 5 non-whitespace characters.")
        return s


class ReverseAllocationRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def check_reason(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 5:
            raise ValueError("Reason must be at least 5 non-whitespace characters.")
        return s


class RefundPaymentRequest(BaseModel):
    amount_paisa: int = Field(gt=0, le=1_000_000_000)
    refund_date: date | None = None
    refund_mode: str = Field(
        pattern=r"^(CASH|UPI|BANK_TRANSFER|NEFT|RTGS|IMPS|CHEQUE|CARD|OTHER)$"
    )
    reference_no: str | None = Field(default=None, max_length=80)
    reason: str = Field(min_length=5, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("reason")
    @classmethod
    def check_reason(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 5:
            raise ValueError("Refund reason must be at least 5 non-whitespace characters.")
        return s


class PaymentAllocationOut(BaseModel):
    id: int
    payment_id: int
    payment_number: str
    invoice_id: int
    invoice_number: str
    invoice_date: date
    due_date: date
    invoice_grand_total_paisa: int
    invoice_outstanding_paisa: int
    allocated_paisa: int
    status: str
    allocated_by_name: str
    allocated_at: datetime
    reversed_by_name: str | None = None
    reversed_at: datetime | None = None
    reversal_reason: str | None = None
    notes: str | None = None


class PaymentRefundOut(BaseModel):
    id: int
    refund_number: str
    financial_year: str
    payment_id: int
    customer_id: int
    refund_date: date
    amount_paisa: int
    refund_mode: str
    reference_no: str | None = None
    reason: str
    status: str
    refunded_by_name: str
    refunded_at: datetime


class PaymentOut(BaseModel):
    id: int
    payment_number: str
    financial_year: str
    customer_id: int
    customer_code: str
    customer_name: str
    payment_date: date
    amount_paisa: int
    allocated_paisa: int
    refunded_paisa: int
    unallocated_paisa: int
    payment_mode: str
    reference_no: str | None = None
    remarks: str | None = None
    is_advance: bool
    idempotency_key: UUID
    status: str
    reversal_reason: str | None = None
    reversed_by_name: str | None = None
    reversed_at: datetime | None = None
    recorded_by_name: str
    recorded_at: datetime
    version: int
    allocations: list[PaymentAllocationOut] = Field(default_factory=list)
    refunds: list[PaymentRefundOut] = Field(default_factory=list)


class PaginatedPaymentsOut(BaseModel):
    items: list[PaymentOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class OpenInvoiceForAllocationOut(BaseModel):
    invoice_id: int
    invoice_number: str
    order_number: str
    invoice_date: date
    due_date: date
    grand_total_paisa: int
    credited_paisa: int
    paid_paisa: int
    outstanding_paisa: int
    payment_status: str
    days_past_due: int
    is_overdue: bool


class CustomerArSummaryRow(BaseModel):
    customer_id: int
    customer_code: str
    customer_name: str
    customer_type: str
    gstin: str | None = None
    state_name: str
    credit_days: int
    salesman_name: str | None = None
    total_invoiced_paisa: int
    total_credited_paisa: int
    total_payments_received_paisa: int
    total_refunded_paisa: int
    total_allocated_paisa: int
    advance_balance_paisa: int
    total_outstanding_paisa: int
    net_receivable_paisa: int
    overdue_balance_paisa: int
    pending_invoices_count: int
    overdue_invoices_count: int


class PaginatedCustomerArOut(BaseModel):
    items: list[CustomerArSummaryRow]
    total: int
    page: int
    page_size: int
    total_pages: int
    summary_total_invoiced_paisa: int
    summary_total_received_paisa: int
    summary_total_outstanding_paisa: int
    summary_total_overdue_paisa: int
    summary_total_advance_paisa: int


class AgeingInvoiceRow(BaseModel):
    invoice_id: int
    invoice_number: str
    customer_id: int
    customer_name: str
    invoice_date: date
    due_date: date
    days_past_due: int
    is_overdue: bool
    ageing_bucket: str
    original_paisa: int
    credited_paisa: int
    paid_paisa: int
    outstanding_paisa: int
    payment_status: str


class AgeingCustomerRow(BaseModel):
    customer_id: int
    customer_code: str
    customer_name: str
    not_due_paisa: int
    overdue_1_30_paisa: int
    bucket_0_30_paisa: int
    bucket_31_60_paisa: int
    bucket_61_90_paisa: int
    bucket_90_plus_paisa: int
    total_outstanding_paisa: int
    overdue_total_paisa: int


class AgeingReportOut(BaseModel):
    as_of_date: date
    not_due_paisa: int
    overdue_1_30_paisa: int
    bucket_0_30_paisa: int
    bucket_31_60_paisa: int
    bucket_61_90_paisa: int
    bucket_90_plus_paisa: int
    total_outstanding_paisa: int
    overdue_total_paisa: int
    customers: list[AgeingCustomerRow]
    invoices: list[AgeingInvoiceRow]
    total_invoices: int
    page: int
    page_size: int
    total_pages: int


class CustomerStatementEntry(BaseModel):
    entry_date: date
    occurred_at: datetime
    entry_type: str
    reference_number: str
    description: str
    debit_paisa: int
    credit_paisa: int
    running_balance_paisa: int
    linked_invoice_id: int | None = None
    linked_payment_id: int | None = None


class CustomerStatementOut(BaseModel):
    customer_id: int
    customer_code: str
    customer_name: str
    gstin: str | None = None
    state_name: str
    credit_days: int
    total_invoiced_paisa: int
    total_credited_paisa: int
    total_payments_received_paisa: int
    total_refunded_paisa: int
    advance_balance_paisa: int
    total_outstanding_paisa: int
    net_balance_paisa: int
    open_invoices: list[OpenInvoiceForAllocationOut]
    entries: list[CustomerStatementEntry]


class ProductProfitabilityRow(BaseModel):
    pack_size_id: int
    sku_code: str
    display_name: str
    hsn_code: str
    invoiced_qty_pkts: int
    returned_qty_pkts: int
    net_sold_qty_pkts: int
    gross_revenue_paisa: int
    credited_revenue_paisa: int
    net_revenue_paisa: int
    gst_collected_paisa: int
    dispatched_cogs_paisa: int
    pending_dispatch_estimated_cogs_paisa: int
    total_cogs_paisa: int
    gross_profit_paisa: int
    gross_margin_pct: Decimal


class CustomerProfitabilityRow(BaseModel):
    customer_id: int
    customer_code: str
    customer_name: str
    customer_type: str
    invoice_count: int
    net_revenue_paisa: int
    gst_collected_paisa: int
    total_cogs_paisa: int
    gross_profit_paisa: int
    gross_margin_pct: Decimal
    cash_received_paisa: int
    outstanding_receivables_paisa: int


class OrderProfitabilityRow(BaseModel):
    sales_order_id: int
    order_number: str
    order_date: date
    invoice_id: int
    invoice_number: str
    invoice_date: date
    customer_name: str
    doc_status: str
    net_revenue_paisa: int
    gst_collected_paisa: int
    total_cogs_paisa: int
    gross_profit_paisa: int
    gross_margin_pct: Decimal
    cash_received_paisa: int
    outstanding_paisa: int


class DateProfitabilityRow(BaseModel):
    period_date: date
    invoice_count: int
    net_revenue_paisa: int
    gst_collected_paisa: int
    total_cogs_paisa: int
    gross_profit_paisa: int
    gross_margin_pct: Decimal
    cash_collected_on_date_paisa: int


class ProfitabilityReportOut(BaseModel):
    gross_revenue_paisa: int
    credited_revenue_paisa: int
    net_revenue_paisa: int
    gst_collected_paisa: int
    dispatched_cogs_paisa: int
    pending_dispatch_estimated_cogs_paisa: int
    total_cogs_paisa: int
    gross_profit_paisa: int
    gross_margin_pct: Decimal
    cash_received_paisa: int
    outstanding_receivables_paisa: int
    disclaimer: str
    by_product: list[ProductProfitabilityRow]
    by_customer: list[CustomerProfitabilityRow]
    by_order: list[OrderProfitabilityRow]
    by_date: list[DateProfitabilityRow]


class PaymentTrendRow(BaseModel):
    payment_date: date
    payment_count: int
    total_received_paisa: int


class CostingSummaryCardRow(BaseModel):
    production_run_id: int
    run_number: str
    sku_code: str
    display_name: str
    cost_status: str
    good_packets: int
    total_cost_paisa: int
    cost_per_packet_paisa: int | None = None
    gross_margin_per_pkt_paisa: int | None = None
    gross_margin_pct: Decimal | None = None


class FinanceDashboardOut(BaseModel):
    total_invoiced_taxable_paisa: int
    total_gst_collected_paisa: int
    total_invoiced_gross_paisa: int
    total_credited_paisa: int
    net_invoiced_sales_paisa: int
    payments_received_paisa: int
    total_refunded_paisa: int
    net_cash_collected_paisa: int
    customer_advances_paisa: int
    outstanding_receivables_paisa: int
    overdue_receivables_paisa: int
    total_cogs_paisa: int
    gross_profit_paisa: int
    gross_margin_pct: Decimal
    profitability_disclaimer: str
    recent_payments: list[PaymentOut]
    recent_outstanding_invoices: list[AgeingInvoiceRow]
    payment_trends: list[PaymentTrendRow]
    product_profitability: list[ProductProfitabilityRow]
    costing_summary: list[CostingSummaryCardRow]


class SalesmanCustomerArOut(BaseModel):
    customer_id: int
    customer_code: str
    customer_name: str
    total_invoiced_paisa: int
    total_paid_paisa: int
    advance_balance_paisa: int
    total_outstanding_paisa: int
    open_invoices: list[OpenInvoiceForAllocationOut]
