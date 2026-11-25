# Phase 9 — API Reference (`/api/v1/finance/*` & `/api/v1/costing/*`)

All endpoints enforce JWT Bearer authentication, strict Pydantic v2 validation, integer-paisa payloads, and server-side RBAC.

---

## 1. Finance, Payments, Receivables & Profitability (`/api/v1/finance`)

| Method & Path | Allowed Roles | Description |
| --- | --- | --- |
| `GET /api/v1/finance/dashboard` | `FACTORY_ADMIN`, `ACCOUNTANT_AUDITOR`, `OWNER` | Aggregated taxable sales, GST collected, cash received, advances, open/overdue AR, COGS, gross margin %, trends, and top profitability/costing cards (`date_from`, `date_to`). |
| `GET /api/v1/finance/payments` | `FACTORY_ADMIN`, `ACCOUNTANT_AUDITOR`, `OWNER` | Paginated payment list filtered by `customer_id`, `status`, `payment_mode`, `date_from`, `date_to`, `search`. |
| `POST /api/v1/finance/payments` | `FACTORY_ADMIN` | Records a customer payment (`201`) with optional initial allocations, `client_payment_id` idempotency replay, and FY numbering (`PMT/...`). |
| `GET /api/v1/finance/payments/{payment_id}` | `FACTORY_ADMIN`, `ACCOUNTANT_AUDITOR`, `OWNER` | Payment detail including line allocations and refund history. |
| `POST /api/v1/finance/payments/{payment_id}/allocate` | `FACTORY_ADMIN` | Allocates remaining `unallocated_paisa` (e.g., Customer Advance) to one or more open customer invoices (`expected_version` optimistic lock supported). |
| `POST /api/v1/finance/allocations/{allocation_id}/reverse` | `FACTORY_ADMIN` | Reverses an individual `ACTIVE` allocation with `reason`, recalculating invoice balance/status back to `PARTIALLY_PAID`/`UNPAID` and restoring `unallocated_paisa`. |
| `POST /api/v1/finance/payments/{payment_id}/reverse` | `FACTORY_ADMIN` | Reverses entire posted payment (`reason`), unwinding all active allocations and resetting AR & invoice balances (`REVERSED`). |
| `POST /api/v1/finance/payments/{payment_id}/refund` | `FACTORY_ADMIN` | Refunds all or part of remaining `unallocated_paisa` as `RFN/YYYY-YY/NNNN`. |
| `GET /api/v1/finance/payments/{payment_id}/receipt-pdf` | `FACTORY_ADMIN`, `ACCOUNTANT_AUDITOR`, `OWNER` | Downloads statutory `%PDF-1.4` customer payment receipt (`application/pdf`). |
| `GET /api/v1/finance/receivables` | `FACTORY_ADMIN`, `ACCOUNTANT_AUDITOR`, `OWNER` | Paginated customer AR summary with totals, advances, overdue balances, and `only_outstanding` filter. |
| `GET /api/v1/finance/receivables/ageing` | `FACTORY_ADMIN`, `ACCOUNTANT_AUDITOR`, `OWNER` | Invoice & customer ageing across `NOT_DUE`, `0_30`, `31_60`, `61_90`, `90_PLUS` strictly from `due_date` vs `as_of_date`. |
| `GET /api/v1/finance/receivables/customers/{customer_id}/statement` | `FACTORY_ADMIN`, `ACCOUNTANT_AUDITOR`, `OWNER` | Chronological customer debit/credit statement with running balance and open invoice list. |
| `GET /api/v1/finance/receivables/open-invoices/{customer_id}` | `FACTORY_ADMIN`, `ACCOUNTANT_AUDITOR`, `OWNER` | Open `ISSUED` invoices with `outstanding_paisa > 0` for quick allocation UI. |
| `GET /api/v1/finance/my-customers/receivables` | `SALESMAN` only | Salesman-scoped read-only AR summary & open invoices limited to `assigned_salesman_id == actor.user_id`. |
| `GET /api/v1/finance/profitability` | `FACTORY_ADMIN`, `ACCOUNTANT_AUDITOR`, `OWNER` | Product, customer, order, and date profitability breakdowns with GST/Cash isolation and Net Profit disclaimer. |

---

## 2. Production Costing & Overheads (`/api/v1/costing`)

| Method & Path | Allowed Roles | Description |
| --- | --- | --- |
| `GET /api/v1/costing/dashboard` | `FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR`, `ACCOUNTANT_AUDITOR`, `OWNER` | Costed runs, finalized count, batch cost totals, wastage/damage totals, SKU cost aggregates, and active monthly overhead pools. |
| `GET /api/v1/costing/runs/{run_id}` | `FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR`, `ACCOUNTANT_AUDITOR`, `OWNER` | Detailed run costing: current snapshot, historical snapshot versions (`PRELIMINARY` -> `FINALIZED`), material-level FIFO variances, and overhead lines. |
| `POST /api/v1/costing/runs/{run_id}/overheads` | `FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR` | Appends a `DIRECT_RUN` overhead line and generates an immutable updated cost snapshot (`snapshot_version + 1`). |
| `POST /api/v1/costing/runs/{run_id}/finalize` | `FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR` | Optionally records additional direct overheads in batch and appends a `FINALIZED` cost snapshot. |
| `POST /api/v1/costing/overheads/{overhead_id}/void` | `FACTORY_ADMIN` only | Voids a posted overhead with audit `reason` (`is_voided = true`) and recalculates affected run/pool snapshots cleanly (`v + 1`). |
| `POST /api/v1/costing/monthly-pools` | `FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR` | Records a `MONTHLY_POOL` factory expense (`YYYY-MM`, e.g., `FACTORY_RENT`, `MACHINE_DEPRECIATION`). |
| `POST /api/v1/costing/monthly-pools/{period_month}/reallocate` | `FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR` | Reallocates active monthly pool totals proportionally across all completed/posted runs in `period_month` by `actual_good_output_pkts` (largest-remainder integer-paisa split). |
