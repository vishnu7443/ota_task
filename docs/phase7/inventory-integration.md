# Inventory Ledger Integration (`docs/phase7/inventory-integration.md`)

## Single-Ledger Architecture (Zero Duplicate Stock Tables)
Phase 7 reuses Phase 6 `inventory.inventory_movements`, `inventory.inventory_balances`, and `inventory.cost_lots` directly:

- **Schema Extensions (`0004_phase7_bom_and_production.py`):**
  - Added `production_run_id BIGINT NULL` FK (`ON DELETE RESTRICT`) on `inventory.inventory_movements` with index `idx_inv_mov_production_run`.
  - Updated `chk_inventory_movements_mov_source_required` so `PRODUCTION_RUN` rows require non-null `production_run_id`.
  - Created `inventory.cost_lot_consumptions` (`CostLotConsumption`) linking `inventory_movement_id`, `cost_lot_id`, `qty_consumed_base`, `unit_cost_paisa_per_base`, and `total_cost_paisa` for exact FIFO audit traceability.

- **Ledger Movement Types Emitted by Production:**
  - `PROD_ISSUE_OUT` (negative `signed_qty_base`): Raw/packaging consumed from `CostLot` FIFO layers (`consume_fifo_lots`).
  - `PACKAGING_DAMAGE_OUT` (negative `signed_qty_base`): Damaged pouches/cartons segregated in the ledger from clean production issue.
  - `PROD_RETURN_IN` (positive `signed_qty_base`): Unused issued materials returned to store during posting or abort of an `IN_PROGRESS` run; recreates a `RET-<run_number>` `CostLot` and nets cleanly against the `issued` bucket on `GET /api/v1/inventory/overview` so `Opening + Received - Net Issued + Adjusted = Physical`.
  - `PROD_OUTPUT_IN` (positive `signed_qty_base`): Adds saleable `good_qty_pkts` (`rejected_qty_pkts` excluded) to `FINISHED_GOOD` balance + FIFO `CostLot` (`batch_code`, `expiry_date`, material-absorbed `unit_cost_paisa_per_base`).

- **Traceability Across UI:**
  - `GET /api/v1/inventory/ledger` filters by `production_run_id` and serializes `production_run_id` + `reference_code`.
  - [AdminInventoryLedgerPage.tsx](file:///d:/mac/ota/frontend/src/pages/admin/AdminInventoryLedgerPage.tsx) links every `PRODUCTION_RUN` row directly to `/admin/production/runs/:runId`.
  - [AdminInventoryDashboardPage.tsx](file:///d:/mac/ota/frontend/src/pages/admin/AdminInventoryDashboardPage.tsx) exposes the net `Issued` column alongside `Opening`, `Received`, `Adjusted`, `Physical`, `Reserved`, and `Available`.
