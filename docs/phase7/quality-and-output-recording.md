# Quality & Output Recording (`docs/phase7/quality-and-output-recording.md`)

## Separation of Finished Output vs Damaged Packaging (`IN_PROGRESS -> COMPLETED`)
Implemented in `complete_production_run` (`POST /api/v1/production/runs/{run_id}/complete`):
- **Finished Goods Output (`production.production_outputs`):** Captures `good_qty_pkts` (`188`), `rejected_qty_pkts` (`0` default), `batch_code`, optional `expiry_date`, and `quality_remarks`. Total output `good + rejected` must be `> 0`.
- **Packaging Quantities Captured Independently (`production_material_issues` + `production_wastages`):**
  - Captures `actual_good_used_qty` (e.g., `188` pouches, `9` cartons) separately from `damaged_packaging_qty` (e.g., `6` pouches torn during sealing).
  - Never conflates `6` damaged pouches with `6` rejected finished snack packets: rejected packets and damaged empty pouches are recorded independently and never pollute each other.
- **Internal Consistency Validation:**
  - Packaging consumed equals `actual_good_used_qty + damaged_packaging_qty`.
  - When materials were pre-issued (`issued_qty_base > 0`) and unused units remain (`returned_unused_qty > 0`), enforces `actual_consumed_qty_base + returned_unused_qty_base == issued_qty_base`.
  - `wasted_qty_base` cannot exceed `actual_consumed_qty_base`; cross-dimension units are rejected (`422`).
- **Audit Events Recorded:** `PRODUCTION_RUN_COMPLETED` written to `audit.audit_logs` before transitioning `IN_PROGRESS -> COMPLETED`.
