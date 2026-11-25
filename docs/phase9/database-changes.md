# Phase 9 — Additive Database Migration (`0006_phase9_payments_costing`)

## Overview

Migration file: [`0006_phase9_payments_and_costing`](file:///d:/mac/ota/backend/alembic/versions/0006_phase9_payments_ar_and_costing.py)
- **Revision ID:** `0006_phase9_payments_costing`
- **Revises:** `0005_phase8_gst_billing_dispatch`
- Preserves all Phases 1–8 tables, data, valuation layers, and triggers with zero breaking edits. Supports clean forward `upgrade` and clean `downgrade`.

---

## Additive Updates to Existing Schema (`billing`)

1. **`billing.fiscal_sequences` Check Constraint Extension:**
   - `chk_fiscal_sequences_fs_doc_type_enum` extended from `('INVOICE', 'CREDIT_NOTE', 'DISPATCH')` to `('INVOICE', 'CREDIT_NOTE', 'DISPATCH', 'PAYMENT', 'REFUND')`.
2. **`billing.invoices` Financial Bound Constraint:**
   - Added `chk_invoices_inv_paid_credited_cap`: guarantees `paid_paisa + credited_paisa <= taxable_total_paisa + cgst_total_paisa + sgst_total_paisa + igst_total_paisa + round_off_paisa`.

---

## New Schema: `finance`

| Table | Purpose & Key Columns | Constraints & Indexes |
| --- | --- | --- |
| `finance.payments` | Customer payment receipts (`payment_number`, `financial_year`, `customer_id`, `payment_date`, `amount_paisa`, `allocated_paisa`, `refunded_paisa`, persisted generated `unallocated_paisa`, `payment_mode`, `reference_no`, `is_advance`, `idempotency_key`, `status`, `reversed_by`, `reversal_reason`, `version`) | `uq_payments_payment_number`, `uq_payments_idempotency_key`, partial unique `uq_payments_customer_dup_ref` (where `status <> 'REVERSED' AND reference_no IS NOT NULL`), `chk_payments_pmt_cap_bounds`, `chk_payments_pmt_mode_enum`, `chk_payments_pmt_status_enum` |
| `finance.payment_allocations` | Links payments to `billing.invoices` (`payment_id`, `invoice_id`, `allocated_paisa`, `status`, `allocated_by`, `reversed_by`, `reversal_reason`) | `chk_payment_allocations_pa_amount_pos`, `chk_payment_allocations_pa_status_enum` (`ACTIVE`, `REVERSED`), `idx_pa_payment_status`, `idx_pa_invoice_status` |
| `finance.payment_refunds` | Immutable refund records from unallocated advance (`refund_number`, `payment_id`, `customer_id`, `refund_date`, `amount_paisa`, `refund_mode`, `reason`) | `uq_payment_refunds_refund_number`, `chk_payment_refunds_rfd_amount_pos`, `chk_payment_refunds_rfd_reason_len` |
| `finance.customer_receivables` | Per-invoice AR balance projection (`customer_id`, `invoice_id`, `invoice_date`, `due_date`, `original_paisa`, `credited_paisa`, `paid_paisa`, persisted generated `outstanding_paisa`) | `uq_customer_receivables_invoice_id`, `chk_customer_receivables_ar_non_negative`, `idx_ar_customer_due`. Upgrade backfills any pre-existing non-DRAFT invoices idempotently. |

---

## New Schema: `costing`

| Table | Purpose & Key Columns | Constraints & Indexes |
| --- | --- | --- |
| `costing.production_overheads` | Direct batch or monthly factory pool overhead lines (`production_run_id`, `period_month`, `overhead_type`, `allocation_scope`, `amount_paisa`, `is_voided`, `void_reason`, `voided_by`) | `chk_production_overheads_po_scope_run_match` (ensures `DIRECT_RUN` has run ID & `MONTHLY_POOL` has NULL run ID), `chk_production_overheads_po_type_enum`, `idx_cost_overheads_run`, `idx_cost_overheads_period` |
| `costing.production_cost_summaries` | Immutable versioned FIFO batch cost snapshots (`production_run_id`, `snapshot_version`, `is_current`, `cost_status`, `valuation_method`, `planned_*`, `raw_material_cost_paisa`, `damaged_packaging_cost_paisa`, `raw_wastage_cost_paisa`, `rejected_output_cost_impact_paisa`, `direct_overhead_paisa`, `allocated_overhead_paisa`, `total_cost_paisa`, `cost_per_packet_paisa`, `exact_cost_per_packet_paisa`, `gross_margin_*`, JSONB `cost_breakdown_snapshot`) | `uq_pcs_run_version`, partial unique `uq_pcs_current_run` (where `is_current IS TRUE`), `chk_pcs_status_enum` (`PRELIMINARY`, `FINALIZED`), `chk_pcs_val_method_enum` |

---

## Database Triggers Enforcing Financial & Costing Integrity

- `trg_payment_immutability` (`finance.fn_protect_posted_payment_immutability`): Blocks `DELETE`; blocks updates to `payment_number`, `customer_id`, `amount_paisa`, `payment_date`, `payment_mode`, `idempotency_key`, `recorded_by`, and any mutation once `REVERSED`.
- `trg_payment_allocation_integrity` (`finance.fn_protect_allocation_immutability`): Blocks `DELETE`; blocks altering amounts/IDs or un-reversing reversed rows; on `INSERT`, verifies against DB totals that the allocation fits inside BOTH payment unallocated capacity and invoice remaining balance.
- `trg_payment_refunds_append_only` (`audit.fn_prevent_mutation`): Makes `finance.payment_refunds` strictly append-only (`BEFORE UPDATE OR DELETE`).
- `trg_customer_receivable_no_delete` (`finance.fn_protect_receivable_delete`): Blocks `DELETE` on `finance.customer_receivables`.
- `trg_cost_summary_immutability` (`costing.fn_protect_cost_summary_immutability`): Blocks `DELETE` and monetary/quantity edits; permits only superseding `is_current = TRUE -> FALSE` when a newer version is appended.
- `trg_overhead_immutability` (`costing.fn_protect_overhead_immutability`): Blocks `DELETE` and monetary/scope edits; permits only active-to-voided transition (`is_voided = FALSE -> TRUE`) with reason/actor.
