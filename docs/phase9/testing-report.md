# Phase 9 — Verification & Testing Report

## Environment & Tooling

- **Database:** Isolated PostgreSQL 16 test instance `ota_test` (separate from development database `ota_dev`).
- **Backend Test Runner:** Python 3.12 (`uv run pytest -v`) & Ruff (`uv run ruff check app tests`).
- **Frontend Build Check:** TypeScript project compiler & Vite 6.4.6 production bundle (`npm run build` executing `tsc -b && vite build`).

---

## Verification Matrix (Executed After Final Edits)

### 1. Database Migration & Roundtrip (`0006_phase9_payments_costing`)

- Session fixture runs full `alembic downgrade base -> alembic upgrade head` cleanly on `ota_test` (`0001 -> 0002 -> 0003 -> 0004 -> 0005 -> 0006`), creating `finance` & `costing` schemas, 6 new tables, persisted generated columns, billing constraints, and 6 PostgreSQL integrity/immutability triggers.
- Prior upgrade on `ota_dev`: `alembic upgrade head` applied `0006_phase9_payments_costing`. *(Refreshed cleanly in local dev validation alongside benchmark seed.)*

### 2. Backend Static Analysis

- Command: `uv run ruff check app tests` in `d:\mac\ota\backend`
- Result: **`All checks passed!`** (0 errors, 0 warnings).

### 3. Frontend TypeCheck & Production Build

- Command: `npm run build` (`tsc -b && vite build`) in `d:\mac\ota\frontend`
- Result: Exit code `0`, **`1694 modules transformed`**, **`dist/assets/index-DdnRnR_c.js` built in `6.14s`**.

### 4. Automated Pytest Suite (54 / 54 Passed)

- Command: `uv run pytest -v` in `d:\mac\ota\backend`
- Result: **`54 passed, 1 warning in 97.61s (0:01:37)`** (0 failures, 0 skipped; single expected Starlette `httpx` deprecation warning).

### 5. Live Uvicorn End-to-End Check (`ota_dev` + `benchmark_seed`)

- Verified clean `benchmark_seed` initialization on empty `ota_dev`, booted live `uvicorn` on ephemeral port `8019`, confirmed OpenAPI Phase 9 endpoints, and executed full 12-step Section 5 scenario cleanly (`PHASE9_LIVE_HTTP_E2E_OK`: `cost_per_pkt_paisa=3090`, `INV/2026-27/0001`, `PMT/2026-27/0001`, `net_revenue_paisa=750000`, `gst_collected_paisa=37500`, `cash_received_paisa=787500`), then restored `ota_dev` to initial `benchmark_seed` state.

| Test Module | Scope | Count | Status |
| --- | --- | --- | --- |
| [`test_auth.py`](file:///d:/mac/ota/backend/tests/test_auth.py) | JWT auth, inactive accounts, RBAC matrix | 4 | Passed |
| [`test_health_and_db.py`](file:///d:/mac/ota/backend/tests/test_health_and_db.py) | Health, seed balances, immutable audit/ledger triggers | 3 | Passed |
| [`test_orders_vertical_slice.py`](file:///d:/mac/ota/backend/tests/test_orders_vertical_slice.py) | Order submit, server pricing, idempotency, salesman isolation | 6 | Passed |
| [`test_sales_catalog.py`](file:///d:/mac/ota/backend/tests/test_sales_catalog.py) | Salesman customer scope & catalog stock fields | 2 | Passed |
| [`test_phase5_order_lifecycle.py`](file:///d:/mac/ota/backend/tests/test_phase5_order_lifecycle.py) | Order review, reservations, modifications, concurrency, 12-step flow | 9 | Passed |
| [`test_phase6_purchasing_and_inventory.py`](file:///d:/mac/ota/backend/tests/test_phase6_purchasing_and_inventory.py) | Suppliers, POs, GRNs, UOMs, adjustments, ledger, concurrency | 9 | Passed |
| [`test_phase7_bom_and_production.py`](file:///d:/mac/ota/backend/tests/test_phase7_bom_and_production.py) | BOM versioning, calculator, production runs, variances, concurrency | 8 | Passed |
| [`test_phase8_billing_and_dispatch.py`](file:///d:/mac/ota/backend/tests/test_phase8_billing_and_dispatch.py) | Phase 8 GST billing, PDF, Credit Notes, Dispatch, Delivery & Concurrency | 5 | Passed |
| [`test_phase9_payments_ar_costing_profitability.py`](file:///d:/mac/ota/backend/tests/test_phase9_payments_ar_costing_profitability.py) | Phase 9 Payments, Multi-Invoice Allocations, Advances, Refunds, Reversals, CN Unwind, Due-Date Ageing, Batch Costing, Monthly Pools, Profitability, DB Triggers, RBAC & Concurrency | 8 | Passed |
| **Total** | **Phases 4–9 Combined Regression** | **54** | **All Passed** |

---

## Phase 9 Test Cases Covered ([`test_phase9_payments_ar_costing_profitability.py`](file:///d:/mac/ota/backend/tests/test_phase9_payments_ar_costing_profitability.py))

1. **`test_1_benchmark_12_step_e2e_costing_payments_ar_statement_and_profitability`:**
   - Official Section 5 walkthrough: verifies auto `v1 PRELIMINARY` batch costing upon production post (`₹3,390` raw + `₹620` pkg incl. `₹15` damaged pouches), finalization with Step 8 overheads (`₹1,200` Labour + `₹600` Gas/Power = `₹5,810 / 188 = ₹30.90/pkt`, Planned `₹5,770 / 200 = ₹28.85/pkt`, Gross Margin `₹19.10` / `38.20%`), GST invoice `₹7,875.00`, partial payment `₹4,000.00` (`PARTIALLY_PAID`, outstanding `₹3,875.00`), `%PDF-1.4` payment receipt download (`PMT/...`), final settlement `₹3,875.00` (`PAID`, outstanding `₹0.00`), chronological statement ending at `0`, and profitability isolating net revenue (`₹7,500`) from GST (`₹375`) and cash collections (`₹7,875`) with explicit Net Profit disclaimer.
2. **`test_2_multi_invoice_single_payment_and_split_allocations`:**
   - Allocates one `₹6,000.00` cheque receipt across two issued invoices (`₹5,250.00 -> PAID`, `₹750.00 / ₹3,150.00 -> PARTIALLY_PAID` leaving `₹2,400.00`).
3. **`test_3_over_allocation_cross_customer_idempotency_and_duplicate_ref_guards`:**
   - Rejects allocation > payment amount, allocation > invoice balance, and cross-customer invoice allocation; proves safe UUID idempotent replay (`client_payment_id`) and duplicate reference conflict block (`409`).
4. **`test_4_advance_payment_late_allocation_and_advance_refund`:**
   - Records unallocated `₹10,000` advance, later allocates `₹4,200` to newly issued invoice, issues `₹2,500` refund (`RFD/...`), and blocks over-refund beyond remaining `₹3,300` (`409`).
5. **`test_5_allocation_reversal_payment_reversal_and_credit_note_unwind`:**
   - Proves allocation reversal restores `UNPAID` status & payment unallocated capacity, full payment reversal unwinds allocations (`REVERSED`, invoice `UNPAID`), and issuing a `₹1,050` Credit Note on a paid invoice cleanly frees `₹1,050` back onto Customer Advance (`paid + credited <= grand_total`).
6. **`test_6_ageing_strictly_due_date_based_across_all_buckets`:**
   - Evaluates open AR balance strictly from `due_date` vs reporting `as_of_date`, verifying transitions across `NOT_DUE`, `0_30` (day 15), `31_60` (day 45), `61_90` (day 75), and `90_PLUS` (day 110).
7. **`test_7_costing_wastage_rejected_void_overhead_and_monthly_pool_allocation`:**
   - Verifies raw wastage cost & rejected packet impact, `PRODUCTION_SUPERVISOR` blocked (`403`) from voiding overheads while `FACTORY_ADMIN` voids creating clean `v+1` exclusion, and `₹5,000` monthly factory pool split across `180` and `100` packet runs sums exactly to `500000` paise.
8. **`test_8_immutability_triggers_strict_rbac_and_concurrent_allocation_lock`:**
   - Proves DB triggers reject `DELETE` and monetary edits (`DBAPIError`), confirms 5-role permissions (salesman AR isolation & zero costing visibility; supervisor zero customer finance access; auditor/owner read-only `403` on writes), and proves concurrent full allocations (`ThreadPoolExecutor`) cleanly return `[201, 409]` with zero negative AR.
