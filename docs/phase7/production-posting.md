# Atomic Production Posting (`docs/phase7/production-posting.md`)

## Single Atomic Commit (`COMPLETED -> POSTED`)
Implemented in `post_production_run` (`POST /api/v1/production/runs/{run_id}/post`) in [service.py](file:///d:/mac/ota/backend/app/modules/production/service.py):

1. **Row-Level Concurrency & Idempotency Guards:**
   - Acquires `SELECT ... FOR UPDATE` on `production.production_runs` plus deterministic lock ordering on all `inventory.inventory_balances` rows (`lock_balances_by_material_ids` + `lock_balances_by_pack_size_ids`).
   - Rejects already-posted runs with `409 Conflict` (`error_code = "DUPLICATE_POST"`).
   - Rejects non-`COMPLETED` runs with `409 Conflict` (`error_code = "INVALID_STATE_TRANSITION"`).

2. **Reconciliation of Pre-Issued vs Completion-Recorded Quantities:**
   - Computes net previously posted movement outflow per material (`SUM(-signed_qty_base)` for rows linked by `production_run_id`).
   - **Never Pre-Issued (`already_out == 0` and `desired_consumed > 0`, e.g., packaging issued at packing):**
     - Verifies `available_qty_base >= desired_consumed` (`409 INSUFFICIENT_STOCK`).
     - Posts `PROD_ISSUE_OUT` for `actual_good_used_base` and `PACKAGING_DAMAGE_OUT` for `damaged_qty_base` using FIFO `CostLot` depletion (`consume_fifo_lots`), recording `inventory.cost_lot_consumptions` (`CostLotConsumption`).
   - **Over-Issued (`already_out > desired_consumed`):**
     - Returns excess to store via `PROD_RETURN_IN` (`+return_qty`) and creates a fresh return `CostLot` (`batch_code = "RET-<run_number>"`), crediting back `mi.cost_absorbed_paisa`.
   - **Under-Issued (`desired_consumed > already_out`):**
     - Posts additional `PROD_ISSUE_OUT` from FIFO `CostLot` layers and adds incremental `cost_absorbed_paisa`.

3. **Finished Goods Ledger & Batch Traceability:**
   - Sums absorbed material cost across all `production_material_issues` (`total_mat_cost`) and derives `fg_unit_cost` over `actual_good_output_pkts`.
   - Inserts `PROD_OUTPUT_IN` into `inventory.inventory_movements` and a fresh `FINISHED_GOOD` `CostLot` (`batch_code`, `expiry_date`) **only for `good_qty_pkts`** (`rejected_qty_pkts` is excluded from saleable FG stock).

4. **Variance Persistence, Alerts & Audit Trail:**
   - Invokes `_compute_and_store_variances` using `company.variance_tolerance_pct`.
   - Transitions run to `POSTED` (`posted_by`, `posted_at`, `version += 1`) and writes `PRODUCTION_RUN_POSTED` to `audit.audit_logs` inside the same database transaction (`db.rollback()` on any failure).
