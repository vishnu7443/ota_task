# Phase 7 Automated Testing & Verification Report (`docs/phase7/testing-report.md`)

## Verification Commands & Observed Results
1. **Database Migration (`ota` dev & `ota_test` clean reset):**
   - `uv run alembic upgrade head` succeeded (`0003_phase6_purchasing_inv -> 0004_phase7_bom_production`).
   - Session fixture executed `alembic downgrade base -> upgrade head` on `ota_test` (PostgreSQL 16.11) with zero errors.
2. **Backend Linter:**
   - `uv run ruff check app tests` -> `All checks passed!`
3. **Full Backend Test Suite (`uv run pytest -v`):**
   - **Observed Result:** **`41 passed, 1 warning in 471.07s (0:07:51)`** (33 preserved Phase 4–6 tests + 8 comprehensive Phase 7 tests in [test_phase7_bom_and_production.py](file:///d:/mac/ota/backend/tests/test_phase7_bom_and_production.py)).
4. **Frontend TypeScript & Production Bundle:**
   - `npm run build` (`tsc -b && vite build` in `frontend/`) exited with code `0`: `✓ 1683 modules transformed.`, `✓ built in 14.62s`.

## Phase 7 Test Coverage Summary (`tests/test_phase7_bom_and_production.py`)
1. `test_1_bom_creation_pack_size_extensibility_and_version_immutability` — Creates `MRK-500G` + `MAT-PCH-500` sharing `PROD-MRK`, edits `DRAFT` BOM, activates v1, verifies `409 IMMUTABLE_BOM_VERSION` on `PUT`/`DELETE`, and confirms PostgreSQL trigger blocks direct `UPDATE` on active versions.
2. `test_2_bom_calculator_scaling_unit_conversions_and_rounding` — Scales `MRK-200G` to `150` pkts (`0.7500` multiplier): `30000 g` Flour, `7500 ml` Oil, `900 g` Spice, `150` pouches, `7.5 -> 8` rounded-up indivisible cartons (`was_rounded_up=True`); `4.0x` batch exposes shortages (`60 kg` Flour, `10 L` Oil); rejects cross-dimension `L` on `MASS` Flour (`422`).
3. `test_3_benchmark_end_to_end_purchase_production_posting_variance_and_ledger` — Full benchmark run: `60 kg` Flour GRN (`160 kg`), `DRAFT -> PLANNED -> IN_PROGRESS` (mixing `1200 g == 1.2 kg` Spice + blocking `409 DOUBLE_MATERIAL_ISSUE`), `COMPLETED` (`188` good, `0` rejected, `188 + 6` pouches, `9` cartons), atomic `POSTED` (`409 DUPLICATE_POST`), exact closing balances, FIFO lot valuation (`522000 paisa`), exact variances/3 open alerts, alert acknowledgement, and `SUM(movements) == InventoryBalance` zero-drift check.
4. `test_4_unused_material_returns_and_rejected_output_excluded_from_fg_stock` — Issues packaging at start, returns unused pouches/cartons via `PROD_RETURN_IN` + `RET-*` lot, records `10` rejected FG packets excluded from saleable FG stock (`50 + 185 = 235`), and tests conflicting return/consumption validation (`422`).
5. `test_5_historical_bom_preservation_when_v2_activated` — Activates BOM `v2` (`11 kg` Oil, `v1 -> SUPERSEDED`), verifies in-flight `v1` run finishes and posts strictly against `v1` quantities while new runs use `v2`.
6. `test_6_concurrent_material_issues_and_transaction_rollback` — `ThreadPoolExecutor` competing `issue-materials` calls -> `[200, 409]` (exactly 1 `PROD_ISSUE_OUT` set); insufficient stock at start rolls back cleanly with zero partial state or ledger entries.
7. `test_7_rbac_isolation_across_all_roles` — Enforces `403` for `SALESMAN` on all production endpoints and `403` for `ACCOUNTANT_AUDITOR`/`OWNER` on mutations (`create_pack_size`, `create_bom_version`, `create_run`, `issue`, `post`) while permitting reads & `OWNER` alert acknowledgement.
8. `test_8_insufficient_material_blocks_start_and_abort_handles_returns_and_scrap` — Blocks start on missing `60 kg` Flour (`409 INSUFFICIENT_STOCK`, run stays `PLANNED`); verifies aborting an `IN_PROGRESS` run credits unspoiled `PROD_RETURN_IN` back to `100 kg` and logs `COOKING_SCRAP` for unreturned `3 L` Oil.
