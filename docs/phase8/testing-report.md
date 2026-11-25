# Phase 8 — Verification & Testing Report

## Environment & Tooling

- **Database:** Isolated PostgreSQL 16 test instance `ota_test` (separate from development database `ota_dev`).
- **Backend Test Runner:** Python 3.12 (`uv run pytest -v`) & Ruff (`uv run ruff check app tests`).
- **Frontend Build Check:** TypeScript project build & Vite 6.4.6 production bundle (`npm run build` running `tsc -b && vite build`).

---

## Verification Matrix (Executed After Final Edits)

### 1. Database Migration & Roundtrip (`0005_phase8_gst_billing_and_dispatch`)

- `alembic upgrade head` on `ota_dev`: Passed cleanly, creating schema `billing`, 9 tables, constraints, triggers, and Phase 8 columns on `inventory.inventory_movements` and `inventory.stock_reservations`.
- `alembic downgrade base && alembic upgrade head` on `ota_test`: Verified **`ALEMBIC_ROUNDTRIP_OK`**.

### 2. Backend Static Analysis

- Command: `uv run ruff check app tests`
- Result: **`All checks passed!`** (0 errors, 0 warnings).

### 3. Frontend TypeCheck & Production Build

- Command: `npm run build` (`tsc -b && vite build`) in `d:\mac\ota\frontend`
- Result: Exit code `0`, **`1689 modules transformed`**, **`dist/assets/index-B-35gJJT.js` built in `15.84s`**.

### 4. Automated Pytest Suite (46 / 46 Passed)

- Command: `uv run pytest -v` in `d:\mac\ota\backend`
- Result: **`46 passed, 1 warning in 154.68s (0:02:34)`** (0 failures, 0 skipped; single expected Starlette deprecation warning on `httpx`).

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
| **Total** | **Phases 4–8 Combined Regression** | **46** | **All Passed** |

---

## Phase 8 Test Scenarios Covered ([`test_phase8_billing_and_dispatch.py`](file:///d:/mac/ota/backend/tests/test_phase8_billing_and_dispatch.py))

1. **`test_1_final_acceptance_benchmark_retailer_a_and_distributor_b`:**
   - Official Section 5 walkthrough: produces 188 pkts (`50 + 188 = 238` FG), processes `Retailer A` (`150` pkts, `INTRA_STATE`, `INV/2026-27/0001`), verifies draft -> verify -> issue lifecycle, confirms stock isolation prior to dispatch, downloads PDF checking exact statutory bytes, posts dispatch `DSP/2026-27/0001` reducing FG `238 -> 88`, advances delivery `IN_TRANSIT -> DELIVERED`, verifies `Distributor B` (`120` pkts) shortage block (`32` pkts) & modified `88`-pkt `INTER_STATE` IGST invoice `INV/2026-27/0002`, and reconciles Billing Reports.
2. **`test_2_fy_rollover_decimal_rounding_pos_validation_and_historical_snapshot`:**
   - Proves April 1 Indian FY rollover (`2027-03-31` -> `INV/2026-27/0001`, `2027-04-01` -> `INV/2027-28/0001`), commercial `ROUND_HALF_UP` whole-rupee round-off (`₹52.50 -> ₹53.00`), symmetric CGST+SGST (`₹51.00 @ 5% -> 128 + 128 = 256 paise`), GSTIN prefix mismatch rejection (`DomainValidationError`), and historical invoice/PDF immutability after SQL `Product.gst_rate_bps` change (`5% -> 12%`).
3. **`test_3_partial_dispatch_over_dispatch_guards_and_stock_shortage_rollback`:**
   - Enforces draft dispatch block (`409 INVOICE_NOT_ISSUED`), partial dispatch `100` (`CREATED -> READY_FOR_DISPATCH -> DISPATCHED`, FG `238 -> 138`, Reserved `150 -> 50`), over-dispatch guard (`51` vs `50` -> `409 DISPATCH_EXCEEDS_ORDER`), final dispatch `50` (FG `88`, Reserved `0`), delivery discrepancy (`48/50 -> DELIVERY_EXCEPTION` discrepancy `2`), and ledger zero-drift + FEFO `CostLotConsumption` audit.
4. **`test_4_credit_note_immutability_cancellation_and_stock_returns`:**
   - Verifies DB trigger `trg_invoice_immutability` raises `DBAPIError` on direct SQL `UPDATE billing.invoices`, pre-dispatch `INVOICE_CANCELLATION` (`CN/2026-27/0001`) sets invoice `CANCELLED_BY_CN`, cancels order, releases `100` reserved packets back to `available_qty_base = 238`, blocks duplicate cancellation (`409`), and verifies post-dispatch `SALES_RETURN` (`30 RESTOCK_SELLABLE` adds stock `188 -> 218` while `10 SCRAP_DAMAGED` records financial reversal only).
5. **`test_5_concurrency_insufficient_fg_rollback_and_rbac_isolation`:**
   - Verifies `PRODUCTION_SUPERVISOR` blocked (`403`), non-admin writes blocked (`403`), cross-salesman isolation (`403` for `salesman_b` reading `salesman_a` invoice/PDF), `ThreadPoolExecutor` simultaneous invoice creation `[201, 409]`, and simultaneous dispatch posting `[200, 409]` deducting stock strictly once (`238 -> 88`).
