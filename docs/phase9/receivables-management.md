# Phase 9 — Accounts Receivable, Due-Date Ageing & Customer Statements

## Customer Receivables Model (`finance.customer_receivables`)

- Maintains one authoritative projection per non-draft invoice (`uq_customer_receivables_invoice_id`), created atomically inside `billing/service.py::_perform_issue_invoice`.
- Persisted generated column:
  - `outstanding_paisa = original_paisa - credited_paisa - paid_paisa`
- Check constraint `chk_customer_receivables_ar_non_negative` guarantees `credited_paisa + paid_paisa <= original_paisa`.
- Direct SQL `DELETE` is blocked by PostgreSQL trigger `trg_customer_receivable_no_delete`.

## Ageing Buckets (`GET /api/v1/finance/receivables/ageing`)

Ageing is calculated **strictly from `due_date` compared against the reporting `as_of_date`** (defaulting to current server date), **never** from `invoice_date`:
- `days_past_due = (as_of_date - due_date).days`
- Bucket assignment for all `ISSUED` invoices where `outstanding_paisa > 0`:
  - `days_past_due <= 0` -> `NOT_DUE` (`not_due_paisa`, `is_overdue = false`)
  - `1 <= days_past_due <= 30` -> `0_30` (`overdue_1_30_paisa` / `bucket_0_30_paisa`, `is_overdue = true`)
  - `31 <= days_past_due <= 60` -> `31_60` (`bucket_31_60_paisa`, `is_overdue = true`)
  - `61 <= days_past_due <= 90` -> `61_90` (`bucket_61_90_paisa`, `is_overdue = true`)
  - `days_past_due > 90` -> `90_PLUS` (`bucket_90_plus_paisa`, `is_overdue = true`)

## Customer Financial Statement (`GET /api/v1/finance/receivables/customers/{customer_id}/statement`)

Produces a chronological double-entry style customer ledger (`CustomerStatementOut`) ordered by `(entry_date, occurred_at)`:
- **Debits (`+`):** Issued GST Invoices (`original_paisa`), Posted Refunds (`amount_paisa`).
- **Credits (`-`):** Issued Credit Notes (`total_reversed_paisa`), Posted Customer Payments (`amount_paisa`).
- **Reversed Payments:** Shown transparently or excluded/offset cleanly alongside net customer `advance_balance_paisa`, `total_outstanding_paisa`, and `net_balance_paisa = total_outstanding_paisa - advance_balance_paisa`.
- Supports `date_from` and `date_to` filtering and calculates accurate `running_balance_paisa` on every row.

## Salesman Own-Customer AR Visibility (`GET /api/v1/finance/my-customers/receivables`)

- Restricted strictly to `SALESMAN` role via `customer.assigned_salesman_id == actor.user_id`.
- Returns customer total invoiced, total paid, unallocated advance, total outstanding, and open invoice list (`OpenInvoiceForAllocationOut`).
- Zero exposure to product costing, overheads, batch margins, or other salesmen's accounts (`403`).
