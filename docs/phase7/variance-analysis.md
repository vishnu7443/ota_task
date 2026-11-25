# Variance Analysis & Tolerance Alerting (`docs/phase7/variance-analysis.md`)

## Explicit Formulas (`_compute_and_store_variances`)
All variances are persisted to `production.production_variances` with explicit `planned_qty_base`, `actual_qty_base`, `variance_qty_base`, `variance_pct`, `tolerance_pct`, `is_flagged`, and human-readable `formula_explanation`:

1. **Yield Variance (`variance_scope = "YIELD"`):**
   - Formula: `(actual_good_output_pkts - expected_output_pkts) / expected_output_pkts × 100`
   - Flagged when `|variance_pct| > tolerance_pct` (`alert_type = "YIELD_LOSS"` if `< 0`, else `"YIELD_EXCESS"`).

2. **Raw Material Consumption Variance (`variance_scope = "RAW_CONSUMPTION"`):**
   - Formula: `(actual_consumed_qty_base - planned_qty_base) / planned_qty_base × 100`
   - Flagged when `|variance_pct| > tolerance_pct` (`alert_type = "MATERIAL_OVERUSE"` if `> 0`, else `"MATERIAL_UNDERUSE"`).

3. **Dual Packaging Variance (`BR-VAR-03` Separation):**
   - **Batch BOM Comparison (`PACKAGING_BATCH_BOM`):** Compares total actual consumed vs batch BOM `planned_qty_base`; stored for audit transparency (`is_flagged = False`) so carton under-use due to lower yield does not emit false alerts.
   - **Output-Scaled Packaging Variance (`PACKAGING_OUTPUT_SCALED`):**
     - **Pouches:** `scaled_std = actual_good_output_pkts`. Formula compares `(good + damaged) - actual_good_output_pkts` so damaged pouches (`e.g., 6 torn out of 194 used for 188 packets`) trigger an accurate `+3.19%` variance & `PACKAGING_WASTAGE` alert (`|3.19%| > 2.00%`).
     - **Cartons (`MAT-CTN*` or `"carton"` in name):** `scaled_std = floor(actual_good_output_pkts / packets_per_carton)` with un-cartoned loose packet count noted in `formula_explanation`. E.g. `188` packets @ `20 pkts/carton` = `9` cartons needed (`8` loose packets); `9` consumed yields `0.00%` output-scaled variance.

## Variance Alerts & Acknowledgements
- Exceeding `company.variance_tolerance_pct` creates `OPEN` rows in `audit.variance_alerts`.
- Authorised roles (`FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR`, `OWNER`) acknowledge alerts via `POST /api/v1/production/alerts/{alert_id}/acknowledge` (recording `acknowledged_by`, `acknowledged_at`, `acknowledgement_note`, and `VARIANCE_ALERT_ACKNOWLEDGED` audit entry).
- Aggregated reporting across posted/in-flight runs is served by `GET /api/v1/production/reports/variances`.
