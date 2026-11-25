"""Pydantic schemas for Management Intelligence Dashboard & Executive Reporting."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class IntelOrderPipelineOut(BaseModel):
    total_orders: int
    pending_verification: int
    approved: int
    invoiced: int
    dispatched_or_partial: int
    rejected_or_cancelled: int
    shortage_orders: int


class IntelProductSalesRow(BaseModel):
    pack_size_id: int
    sku_code: str
    display_name: str
    hsn_code: str
    invoiced_qty_pkts: int
    net_sold_qty_pkts: int
    net_revenue_paisa: int
    total_cogs_paisa: int
    gross_profit_paisa: int
    gross_margin_pct: Decimal


class IntelCustomerSalesRow(BaseModel):
    customer_id: int
    customer_code: str
    customer_name: str
    customer_type: str
    invoice_count: int
    net_revenue_paisa: int
    gross_profit_paisa: int
    gross_margin_pct: Decimal
    cash_received_paisa: int
    outstanding_receivables_paisa: int


class IntelDailyTrendRow(BaseModel):
    period_date: date
    invoice_count: int
    net_revenue_paisa: int
    total_cogs_paisa: int
    gross_profit_paisa: int
    cash_collected_paisa: int


class IntelSalesSummaryOut(BaseModel):
    gross_taxable_paisa: int
    gst_collected_paisa: int
    credited_taxable_paisa: int
    net_sales_excl_gst_paisa: int
    gross_invoiced_total_paisa: int
    invoice_count: int
    credit_note_count: int
    order_pipeline: IntelOrderPipelineOut
    top_products: list[IntelProductSalesRow]
    top_customers: list[IntelCustomerSalesRow]
    daily_trend: list[IntelDailyTrendRow]


class IntelLowStockRow(BaseModel):
    item_type: str
    item_id: int
    code: str
    name: str
    item_category: str
    display_uom: str
    base_uom: str
    display_factor: Decimal
    physical_qty_base: Decimal
    reserved_qty_base: Decimal
    available_qty_base: Decimal
    reorder_level_base: Decimal
    open_lot_value_paisa: int


class IntelMovementSummaryRow(BaseModel):
    movement_type: str
    movement_count: int
    total_abs_qty_base: Decimal
    total_cost_paisa: int


class IntelInventorySummaryOut(BaseModel):
    total_items: int
    raw_material_count: int
    packaging_material_count: int
    finished_good_count: int
    total_stock_valuation_paisa: int
    low_stock_count: int
    pending_adjustments_count: int
    low_stock_alerts: list[IntelLowStockRow]
    period_movements: list[IntelMovementSummaryRow]


class IntelProductionSkuRow(BaseModel):
    pack_size_id: int
    sku_code: str
    display_name: str
    runs_count: int
    expected_output_pkts: int
    actual_good_pkts: int
    rejected_pkts: int
    yield_efficiency_pct: Decimal
    total_cost_paisa: int
    avg_cost_per_pkt_paisa: int | None = None


class IntelProductionSummaryOut(BaseModel):
    total_runs: int
    posted_runs: int
    in_progress_runs: int
    planned_runs: int
    expected_output_pkts: int
    actual_good_output_pkts: int
    rejected_output_pkts: int
    yield_efficiency_pct: Decimal
    total_batch_cost_paisa: int
    weighted_avg_unit_cost_paisa: int | None = None
    total_wastage_damage_cost_paisa: int
    flagged_variances_count: int
    open_variance_alerts_count: int
    by_sku: list[IntelProductionSkuRow]


class IntelFinanceSummaryOut(BaseModel):
    payments_received_paisa: int
    refunds_paisa: int
    net_cash_collected_paisa: int
    customer_advances_paisa: int
    total_outstanding_receivables_paisa: int
    overdue_receivables_paisa: int
    not_due_receivables_paisa: int
    bucket_0_30_paisa: int
    bucket_31_60_paisa: int
    bucket_61_90_paisa: int
    bucket_90_plus_paisa: int
    total_cogs_paisa: int
    gross_profit_paisa: int
    gross_margin_pct: Decimal
    profitability_disclaimer: str


class IntelOperationsSummaryOut(BaseModel):
    pending_approval_orders: int
    shortage_orders: int
    pending_purchase_orders: int
    pending_goods_receipts: int
    pending_stock_adjustments: int
    pending_dispatches: int
    delivery_exceptions: int
    open_reconciliation_discrepancies: int
    critical_high_discrepancies: int
    security_events_in_period: int


class IntelWatchlistItemOut(BaseModel):
    severity: str  # CRITICAL | HIGH | MEDIUM | INFO
    category: str
    title: str
    detail: str
    link_path: str


class ManagementIntelligenceDashboardOut(BaseModel):
    period_start: date
    period_end: date
    as_of_date: date
    financial_year: str
    sales: IntelSalesSummaryOut
    inventory: IntelInventorySummaryOut
    production: IntelProductionSummaryOut
    finance: IntelFinanceSummaryOut
    operations: IntelOperationsSummaryOut
    watchlist: list[IntelWatchlistItemOut]
