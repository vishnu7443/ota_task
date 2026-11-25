"""Pydantic schemas for Cross-Module Reconciliation, Discrepancy Investigation & Workflow."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator


class InventoryReconciliationRowOut(BaseModel):
    item_type: str  # MATERIAL | PACK_SIZE
    item_id: int
    code: str
    name: str
    item_category: str
    base_uom: str
    display_uom: str
    display_factor: Decimal
    opening_qty_base: Decimal
    inward_purchase_qty_base: Decimal
    inward_production_qty_base: Decimal
    inward_returns_qty_base: Decimal
    inward_adjustment_qty_base: Decimal
    total_inward_qty_base: Decimal
    outward_production_issue_qty_base: Decimal
    outward_dispatch_qty_base: Decimal
    outward_damage_wastage_qty_base: Decimal
    outward_supplier_return_qty_base: Decimal
    outward_adjustment_qty_base: Decimal
    total_outward_qty_base: Decimal
    expected_closing_qty_base: Decimal
    persisted_closing_qty_base: Decimal
    difference_qty_base: Decimal
    cost_lot_remaining_qty_base: Decimal
    cost_lot_difference_qty_base: Decimal
    status: str  # MATCHED | MISMATCH


class InventoryReconciliationReportOut(BaseModel):
    period_start: date
    period_end: date
    cutoff_at: datetime
    total_items: int
    matched_count: int
    mismatch_count: int
    items: list[InventoryReconciliationRowOut]


class SalesReconciliationRowOut(BaseModel):
    sales_order_id: int
    order_number: str
    order_date: date
    order_status: str
    customer_name: str
    ordered_qty_pkts: int
    invoiced_qty_pkts: int
    active_invoice_count: int
    invoice_numbers: list[str]
    status: str  # MATCHED | DISCREPANCY
    issue_code: str | None = None
    issue_detail: str | None = None


class InvoiceReconciliationRowOut(BaseModel):
    invoice_id: int
    invoice_number: str
    invoice_date: date
    doc_status: str
    supply_type: str
    persisted_taxable_paisa: int
    computed_taxable_paisa: int
    persisted_tax_paisa: int
    computed_tax_paisa: int
    persisted_grand_total_paisa: int
    computed_grand_total_paisa: int
    persisted_credited_paisa: int
    computed_credited_paisa: int
    status: str
    issue_code: str | None = None
    issue_detail: str | None = None


class PaymentReconciliationRowOut(BaseModel):
    payment_id: int
    payment_number: str
    payment_date: date
    customer_name: str
    amount_paisa: int
    persisted_allocated_paisa: int
    computed_allocated_paisa: int
    persisted_refunded_paisa: int
    computed_refunded_paisa: int
    unallocated_paisa: int
    status: str
    issue_code: str | None = None
    issue_detail: str | None = None


class DispatchReconciliationRowOut(BaseModel):
    invoice_id: int
    invoice_number: str
    invoice_date: date
    dispatch_status: str
    invoiced_qty_pkts: int
    dispatched_qty_pkts: int
    ledger_dispatch_qty_pkts: int
    pending_qty_pkts: int
    status: str
    issue_code: str | None = None
    issue_detail: str | None = None


class ProductionReconciliationRowOut(BaseModel):
    production_run_id: int
    run_number: str
    run_date: date
    sku_code: str
    run_status: str
    expected_output_pkts: int
    actual_good_pkts: int
    rejected_pkts: int
    ledger_output_pkts: int
    bom_variance_flags_count: int
    cost_summary_paisa: int | None = None
    lot_consumption_cost_with_overheads_paisa: int | None = None
    status: str
    issue_code: str | None = None
    issue_detail: str | None = None


class ReconciliationRunCreateRequest(BaseModel):
    domain: str = Field(
        pattern=r"^(INVENTORY|SALES|INVOICE|PAYMENT|DISPATCH|PRODUCTION|FULL_SYSTEM)$"
    )
    period_start: date | None = None
    period_end: date | None = None
    cutoff_at: datetime | None = None
    item_category: str | None = Field(
        default=None, pattern=r"^(RAW_MATERIAL|PACKAGING_MATERIAL|FINISHED_GOOD)$"
    )
    material_id: int | None = Field(default=None, gt=0)
    pack_size_id: int | None = Field(default=None, gt=0)
    allow_duplicate: bool = False


class ReconciliationDiscrepancyOut(BaseModel):
    id: int
    reconciliation_run_id: int
    domain: str
    discrepancy_code: str
    severity: str
    entity_schema: str
    entity_table: str
    entity_id: int
    entity_ref: str
    expected_value: dict[str, Any]
    actual_value: dict[str, Any]
    difference_summary: str
    status: str
    assigned_to: int | None = None
    assigned_to_name: str | None = None
    investigation_notes: str | None = None
    proposed_action: str | None = None
    corrective_action_type: str | None = None
    approved_by: int | None = None
    approved_by_name: str | None = None
    approved_at: datetime | None = None
    resolution_notes: str | None = None
    resolution_ref_table: str | None = None
    resolution_ref_id: int | None = None
    resolved_by: int | None = None
    resolved_by_name: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    version: int


class ReconciliationEventOut(BaseModel):
    id: int
    reconciliation_run_id: int
    discrepancy_id: int | None = None
    actor_user_id: int
    actor_name: str
    actor_role: str
    event_type: str
    from_status: str | None = None
    to_status: str
    notes: str | None = None
    payload: dict[str, Any] | None = None
    occurred_at: datetime


class ReconciliationRunSummaryOut(BaseModel):
    id: int
    run_number: str
    financial_year: str
    domain: str
    status: str
    period_start: date
    period_end: date
    cutoff_at: datetime
    scope_filter: dict[str, Any]
    summary_snapshot: dict[str, Any]
    discrepancy_count: int
    resolved_count: int
    started_by: int
    started_by_name: str
    started_at: datetime
    last_rerun_at: datetime | None = None
    closed_by: int | None = None
    closed_by_name: str | None = None
    closed_at: datetime | None = None
    closure_notes: str | None = None
    version: int


class ReconciliationRunDetailOut(ReconciliationRunSummaryOut):
    discrepancies: list[ReconciliationDiscrepancyOut]
    events: list[ReconciliationEventOut]


class InvestigateDiscrepancyRequest(BaseModel):
    assigned_to: int | None = Field(default=None, gt=0)
    investigation_notes: str = Field(min_length=5, max_length=1000)

    @field_validator("investigation_notes")
    @classmethod
    def check_notes(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 5:
            raise ValueError("Investigation notes must be at least 5 characters.")
        return s


class ProposeCorrectionRequest(BaseModel):
    corrective_action_type: str = Field(
        pattern=r"^(STOCK_ADJUSTMENT|ISSUE_INVOICE|AR_RECALC_NOTE|MANUAL_JOURNAL_NOTE|DISPATCH_FOLLOWUP|NO_OP_EXPLAINED)$"
    )
    proposed_action: str = Field(min_length=5, max_length=1000)
    investigation_notes: str | None = Field(default=None, max_length=1000)


class ApproveCorrectionRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=500)


class ApplyCorrectionRequest(BaseModel):
    resolution_notes: str = Field(min_length=5, max_length=1000)
    adjustment_type: str | None = Field(
        default="COUNT_CORRECTION",
        pattern=r"^(DAMAGED|EXPIRED|MISSING|COUNT_CORRECTION|SUPPLIER_RETURN|OTHER)$",
    )
    entered_qty: Decimal | None = None
    entered_uom: str | None = Field(default=None, max_length=16)
    unit_cost_paisa_per_base: int | None = Field(default=None, ge=0)
    dismiss: bool = False

    @field_validator("resolution_notes")
    @classmethod
    def check_res_notes(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 5:
            raise ValueError("Resolution notes must be at least 5 characters.")
        return s


class CloseReconciliationRunRequest(BaseModel):
    closure_notes: str = Field(min_length=5, max_length=1000)
