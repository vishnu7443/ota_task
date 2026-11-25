# Phase 10 Database Changes (`0007_phase10_audit_recon`)

Alembic Migration: `backend/alembic/versions/0007_phase10_audit_reconciliation.py` (`Revision: 0007_phase10_audit_recon`, `Revises: 0006_phase9_payments_costing`).

---

## 1. Fiscal Sequence Extension (`billing.fiscal_sequences`)
- Updated `chk_fiscal_sequences_fs_doc_type_enum` CHECK constraint to include `'RECONCILIATION'` alongside `'INVOICE'`, `'CREDIT_NOTE'`, `'DISPATCH'`, `'PAYMENT'`, and `'REFUND'`, enabling gap-free concurrency-safe `REC/YYYY-YY/NNNN` run numbers locked `FOR UPDATE`.

---

## 2. Additive Enhancements on `audit.audit_logs`
- Widened `action` from `VARCHAR(32)` to `VARCHAR(48)`.
- Added nullable `correlation_ref VARCHAR(64)` column for HTTP `REQ-...` and document correlation lookups.
- Added nullable `metadata_json JSONB` column for sanitized contextual telemetry.
- Added indexes:
  - `idx_audit_action_time` (`action`, `occurred_at DESC`)
  - `idx_audit_correlation_ref` (`correlation_ref`, partial `WHERE correlation_ref IS NOT NULL`)
- Existing append-only trigger `trg_audit_logs_append_only` continues blocking all `UPDATE` and `DELETE` statements.

---

## 3. New Tables in `audit` Schema

### `audit.reconciliation_runs`
- Stores formal periodic/on-demand reconciliation runs across `INVENTORY`, `SALES`, `INVOICE`, `PAYMENT`, `DISPATCH`, `PRODUCTION`, and `FULL_SYSTEM`.
- Key constraints: `rr_fy_format`, `rr_domain_enum`, `rr_status_enum` (`NOT_STARTED`, `IN_PROGRESS`, `RECONCILED`, `DISCREPANCY_FOUND`, `UNDER_REVIEW`, `RESOLVED`, `CLOSED`), `rr_period_order`, `rr_counts_non_neg`, `rr_version_pos`.
- Partial unique index `uq_recon_active_fingerprint` prevents concurrent/duplicate active runs over identical `(domain, period_start, period_end, scope_filter)`.
- Trigger `trg_reconciliation_run_immutability` (`BEFORE UPDATE OR DELETE`) blocks deletion of any run, blocks modifying metadata/scope/period/starter fields, and blocks any mutation once `OLD.status = 'CLOSED'`.

### `audit.reconciliation_discrepancies`
- Persists individual detected mismatches with JSONB snapshots (`expected_value`, `actual_value`), severity (`INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), investigation notes, proposed action (`STOCK_ADJUSTMENT`, `ISSUE_INVOICE`, `AR_RECALC_NOTE`, `MANUAL_JOURNAL_NOTE`, `DISPATCH_FOLLOWUP`, `NO_OP_EXPLAINED`), approval actor/timestamp, resolution reference (`resolution_ref_table`, `resolution_ref_id`), and optimistic `version` counter.
- Indexed via `idx_rd_run_status` and `idx_rd_domain_status`.

### `audit.reconciliation_events`
- Immutable append-only audit trail recording `RUN_STARTED`, `SCAN_COMPLETED`, `DISCREPANCY_INVESTIGATED`, `CORRECTION_PROPOSED`, `CORRECTION_APPROVED`, `DISCREPANCY_RESOLVED`, `DISCREPANCY_DISMISSED`, `AUTO_VERIFIED_RESOLVED`, `RUN_RERUN`, and `RUN_CLOSED`.
- Protected by trigger `trg_reconciliation_events_append_only` executing `audit.fn_prevent_mutation()`.
