# Controlled Material Issue Workflow (`docs/phase7/material-issue-workflow.md`)

## State Transition (`PLANNED -> IN_PROGRESS`)
Executed atomically via `issue_materials_and_start_run` (`POST /api/v1/production/runs/{run_id}/issue-materials`):
1. Acquires row lock `FOR UPDATE` on `production.production_runs`.
2. **Double-Issue Guard:** Rejects with `409 DOUBLE_MATERIAL_ISSUE` if `status IN ('IN_PROGRESS','COMPLETED','POSTED')` or `started_at IS NOT NULL`, and `409 INVALID_STATE_TRANSITION` if `status == 'DRAFT'` or `'CANCELLED'`.
3. Validates all entered units via `convert_to_base_qty` (preventing cross-dimension mistakes such as entering litres for flour).
4. **Deadlock-Safe Balance Locking:** Acquires `SELECT ... FOR UPDATE ORDER BY id ASC` across all BOM materials in `inventory.inventory_balances`. Validates `on_hand - reserved >= required_check` before writing any movement (`409 INSUFFICIENT_STOCK` aborts the entire transaction).
5. Depletes open FIFO `CostLot` records (`received_at ASC, id ASC FOR UPDATE`), inserts `inventory.inventory_movements` (`movement_type = 'PROD_ISSUE_OUT'`, `source_doc_type = 'PRODUCTION_RUN'`, **`production_run_id = run.id`**), and creates `inventory.cost_lot_consumptions`.
6. Updates `ProductionMaterialIssue.issued_qty_base`, `cost_absorbed_paisa`, `issued_by`, `issued_at`.

## Distinguishing the Five Consumption Quantities
On every `ProductionMaterialIssue` line:
- `planned_qty_base`: standard BOM × batch scale
- `issued_qty_base`: physical stock drawn at production start
- `actual_consumed_qty_base`: net material consumed (`issued - returned_unused`)
- `returned_unused_qty_base`: unspoiled excess returned to store (`PROD_RETURN_IN`)
- `damaged_qty_base` / `wasted_qty_base`: damaged packaging or raw process wastage
