# Phase 6 Automated Testing & Verification Report (`docs/phase6/testing-report.md`)

## Test Environment & Isolation Guarantee
- **Database Isolation:** All tests run via `tests/conftest.py` strictly against `TEST_DATABASE_URL` (`ota_test` on PostgreSQL 16.11), running `alembic downgrade base -> upgrade head` once per session and truncating/reseeding every test function so `ota_dev` stays completely clean.
- **Linter & Static Checks:**
  - Backend: `uv run ruff check app tests` -> `All checks passed!`
  - Frontend: `npx tsc --noEmit` + `npm run build` (`vite v6.4.6`) -> `✓ 1679 modules transformed. ✓ built in 16.05s`

## Pytest Execution Summary (`uv run pytest -v`)
- **Result:** **`33 passed, 1 warning in 101.12s (0:01:41)`** (24 preserved Phase 4–5 regression tests + 9 comprehensive Phase 6 test suites).
- **Phase 6 Suites Executed (`backend/tests/test_phase6_purchasing_and_inventory.py`):**
  1. `test_supplier_crud_validation_and_purchase_history` — Supplier create/list/edit, duplicate code `409`, GSTIN prefix mismatch `422`, active filtering, and PO/GRN purchase history.
  2. `test_po_lifecycle_totals_and_po_alone_does_not_increase_stock` — Multi-line Raw + Packaging PO creation, exact GST calculation, `DRAFT -> SUBMITTED -> APPROVED`/`REJECTED`, duplicate-approval/reject conflict guards, and confirmation that POs never mutate stock.
  3. `test_benchmark_final_acceptance_scenario_60kg_flour_and_exact_balances` — Exact Section 5 seeded balances + PO (`60 kg Flour @ ₹45/kg`) + `client_receipt_id` replay idempotency + `DRAFT -> SUBMITTED -> VERIFIED -> POSTED` + duplicate-post `409` block + `Closing Flour = 160 kg (160,000 g)` + FIFO `CostLot` layers (`4.200000` & `4.500000` paise/g) + supplier totals.
  4. `test_partial_receipt_damaged_rejection_and_excess_guard` — 100 kg PO split across 50 kg received / 5 kg damaged (stock increases +45 kg only, `PARTIALLY_RECEIVED`) -> excess receipt `409 EXCESS_RECEIPT_QUANTITY` -> second receipt in grams (`55000 g`) -> `RECEIVED`.
  5. `test_unit_conversion_and_incompatible_unit_rejected` — Cross-dimension `L` on `MASS` Flour rejected (`422`), valid metric conversion (`-500 ml` Oil adjustment -> `29.5 L`).
  6. `test_stock_adjustments_approval_workflow_low_stock_and_reservation_safety` — Supervisor `post_immediately=True` blocked (`403`), Supervisor `PENDING_APPROVAL` -> Admin `POSTED` (`SUPPLIER_RETURN` updates `adjusted_qty_base`), Low-Stock threshold trigger, negative stock block (`409 INSUFFICIENT_STOCK`), Sales Order 30-pkt reservation safety (`409 INSUFFICIENT_AVAILABLE_STOCK`), Admin `REJECT` check, and `audit.audit_logs` check.
  7. `test_ledger_immutability_and_db_negative_stock_constraints` — Direct SQL `UPDATE`/`DELETE` on `inventory.inventory_movements` rejected by PostgreSQL triggers; direct negative `on_hand_qty_base` rejected by PostgreSQL check constraints.
  8. `test_rbac_boundaries_and_stock_reports_summary` — `SALESMAN` (`403` on `/purchasing/*`, `/inventory/*`), `PRODUCTION_SUPERVISOR` (`403` on Sales Orders & Supplier CRUD), `ACCOUNTANT_AUDITOR` & `OWNER` (full read `/inventory/reports/summary`, `403` on all writes).
  9. `test_concurrent_receipt_post_and_concurrent_adjustments_prevent_corruption` — `ThreadPoolExecutor` simultaneous double-post on `VERIFIED` Goods Receipt -> `[200, 409]` (exactly 1 `PURCHASE_IN` ledger entry); competing `-70 kg` adjustments against `100 kg` Flour -> `[200, 409]` (physical remains `30 kg`).
