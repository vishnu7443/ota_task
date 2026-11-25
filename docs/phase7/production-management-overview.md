# Phase 7 Production Management Overview (`docs/phase7/production-management-overview.md`)

## Scope & Architecture
Phase 7 delivers an end-to-end **Bill of Materials (BOM) and Production Management** module connecting raw/packaging procurement (Phase 6) directly to finished-goods inventory availability for sales orders (Phases 4–5).

- **Backend Module:** `backend/app/modules/production/` (`models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py`), registered at `/api/v1/production`.
- **Database Migration:** `backend/alembic/versions/0004_phase7_bom_and_production.py` (`0004_phase7_bom_production`).
- **Frontend Workspace:** `AdminBomPage.tsx`, `AdminProductionDashboardPage.tsx`, `AdminProductionRunDetailPage.tsx`, and `AdminProductionVarianceReportPage.tsx`.
- **Single-Ledger Architecture:** Zero duplicate stock tracking. Every raw material issue, packaging issue, damaged packaging deduction, unused return, and good finished-goods output writes an immutable `inventory.inventory_movements` row linked directly via `production_run_id`.

## Phase 2 State Machine Reconciliation & Scope Boundary
- **Reconciled Run Lifecycle:** `DRAFT -> PLANNED -> IN_PROGRESS -> COMPLETED -> POSTED` (plus `CANCELLED` pre-completion with unspoiled material return & scrap handling for aborted `IN_PROGRESS` batches per `EC-06`).
- **Separation from Step 8 Final Costing:** Direct overheads (`Labour`, `Gas/Power`) and final Cost-per-Packet / Margin accounting (`costing` schema) along with GST Invoicing, Dispatch, and Customer Payments remain strictly deferred beyond Phase 7. However, exact FIFO `CostLot` depletion & `CostLotConsumption` tracking continues natively at the inventory ledger layer so material valuation stays exact.
