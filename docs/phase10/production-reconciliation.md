# Production & Costing Reconciliation

## 1. Scope

Implemented in `backend/app/modules/reconciliation/engine.py` (`evaluate_production_reconciliation`), this domain cross-checks every `COMPLETED` and `POSTED` batch in `production.production_runs` against:
- `production.production_outputs`
- `production.production_material_issues`
- `inventory.inventory_movements` (`PROD_OUTPUT_IN`, `PROD_ISSUE_OUT`, `PROD_RETURN_IN`, `PACKAGING_DAMAGE_OUT`)
- `production.production_variances`
- `costing.production_cost_summaries` (`is_current = TRUE`)

---

## 2. Deterministic Checks Enforced

1. **Good Output vs Ledger Output Parity (`PROD_OUTPUT_VS_LEDGER_MISMATCH`, Severity `HIGH`):**
   - For every `POSTED` run, verifies `run.actual_good_output_pkts == sum(outputs.good_qty_pkts) == sum(PROD_OUTPUT_IN signed_qty_base)` using strict deduplication on `InventoryMovement.id`.
   - Rejected finished goods (`rejected_output_pkts`) are deliberately excluded from `PROD_OUTPUT_IN` saleable FG stock and tracked separately for costing absorption impact.
2. **Material Consumption vs Net Ledger Movements (`PROD_ISSUE_VS_MOVEMENT_MISMATCH`, Severity `HIGH`):**
   - For each raw/packaging material issued to a `POSTED` run, verifies `ProductionMaterialIssue.actual_consumed_qty_base` equals net ledger outward flow (`PROD_ISSUE_OUT` + `PACKAGING_DAMAGE_OUT` minus `PROD_RETURN_IN`) within `0.0005` base unit tolerance.
3. **Batch Costing Integrity (`PROD_COST_SUMMARY_MISMATCH`, Severity `HIGH`):**
   - Recomputes $\sum \text{mi.cost\_absorbed\_paisa} + \text{direct\_overhead\_paisa} + \text{allocated\_overhead\_paisa}$ and compares against `ProductionCostSummary.total_cost_paisa`.
4. **BOM Consumption & Yield Variance Visibility (`BOM_CONSUMPTION_VARIANCE`, Severity `LOW`):**
   - Surfaces runs with tolerance-exceeding variance flags (`production_variances.is_flagged = TRUE`) into the reconciliation run for formal supervisor/management sign-off or `NO_OP_EXPLAINED` / `DISMISSED` closure with documented remarks.

---

## 3. Role Scoped Access

Per `docs/phase1/roles-and-permissions.md`, `PRODUCTION_SUPERVISOR` is permitted to inspect Inventory and Production reconciliation reports, initiate `INVENTORY` / `PRODUCTION` runs, and log `investigate` / `propose` findings, while remaining blocked (`403 Forbidden`) from Sales, Invoice, Payment, Dispatch, and Financial Cost Margin approvals.
