# Production Planning Workflow (`docs/phase7/production-planning.md`)

## Planning Steps (`DRAFT -> PLANNED`)
1. Authorized operators (`FACTORY_ADMIN` or `PRODUCTION_SUPERVISOR`) select an active `pack_size_id` (`Murukku 200 g`) and specify either `batch_multiplier` or `target_output_pkts` and `run_date`.
2. `create_production_run` (`POST /api/v1/production/runs`) resolves and pins the active `BomVersion`, assigns sequential run number (`PRD-YYYY-NNNN`), creates `ProductionRun` (`DRAFT` by default, or `PLANNED` if `plan_immediately = true`), and populates `ProductionMaterialIssue` lines with deterministic BOM planned quantities (`planned_qty_base`).
3. `plan_production_run` (`POST /api/v1/production/runs/{id}/plan`) transitions `DRAFT -> PLANNED`, records `planned_at`, increments optimistic version, and appends `PRODUCTION_RUN_PLANNED` to `audit.audit_logs`.
4. **No Premature Stock Mutation:** Planning never deducts inventory balances; stock impact occurs solely at controlled material issue (`IN_PROGRESS`) and atomic production posting (`POSTED`).

## Material Shortage Guardrail Before Starting
Planned runs expose missing requirements across the Production Dashboard (`upcoming_shortages`). Starting production (`PLANNED -> IN_PROGRESS`) is **strictly blocked (`409 INSUFFICIENT_STOCK`)** whenever required/issued materials are unavailable (`available < required`).
