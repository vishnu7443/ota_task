# Production Execution Workbench (`docs/phase7/production-execution.md`)

## Workbench Capabilities (`AdminProductionRunDetailPage.tsx`)
Each Production Run view (`/admin/production/runs/:runId`) displays and tracks:
- **Run Identity & Pinned Recipe:** `run_number`, finished `sku_code`, `display_name`, `version_no` & `bom_status` lock indicator (`v1` preserved forever), and lifecycle stepper (`DRAFT -> PLANNED -> IN_PROGRESS -> COMPLETED -> POSTED`).
- **Timestamps & Actors:** `run_date`, `planned_at`, `started_at`, `completed_at`, `posted_at`, `supervisor_name`, `posted_by_name`, `notes`, and `quality_remarks`.
- **Plan vs Issued vs Actual Consumption Table:** Live comparison across all five material quantity columns plus absorbed FIFO cost.
- **Linked Inventory Ledger Movements:** Real-time query of `inventory.inventory_movements` filtered strictly to `production_run_id`.

## Abort / Cancellation (`EC-06`)
- Pre-issue runs (`DRAFT` / `PLANNED`) cancel cleanly (`CANCELLED`) with audit reason.
- Aborting an `IN_PROGRESS` run accepts optional `returned_items`: salvaged raw/packaging inputs post `PROD_RETURN_IN` back to store (creating a return `CostLot`), while unreturned issued quantities are written explicitly to `production.production_wastages` (`BURNT_BATCH`), preserving full mass balance and audit trail (`INV-STK-03`).
