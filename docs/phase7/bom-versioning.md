# BOM Versioning & Historical Immutability (`docs/phase7/bom-versioning.md`)

## Version Lifecycle (`DRAFT -> ACTIVE -> SUPERSEDED`)
1. Every `BomVersion` stores `version_no` (`UNIQUE(bom_header_id, version_no)`), `expected_yield_pkts`, `effective_date`, `created_by`, `activated_by`, `activated_at`, `notes`, and immutable `BomComponent` rows.
2. Partial unique index `uq_bv_active_header` on `(bom_header_id) WHERE status = 'ACTIVE'` ensures at most one active BOM exists per `pack_size_id` at any time.
3. Creating a new recipe (`POST /api/v1/production/bom/versions`) generates `version_no + 1` in `DRAFT` (or atomically supersedes the prior `ACTIVE` version when `activate = true`).

## Dual-Layer Immutability Enforcement
- **Application Layer (`production/service.py`):** `update_draft_bom_version` (`PUT /bom/versions/{id}`) and `delete_bom_version` (`DELETE /bom/versions/{id}`) permit mutations **only** while `status == 'DRAFT'`, rejecting `ACTIVE` or `SUPERSEDED` edits/deletes with `409 IMMUTABLE_BOM_VERSION`.
- **PostgreSQL Trigger Layer (`0004`):** `trg_bom_version_immutability` (`fn_protect_bom_version_immutability()`) and `trg_bom_component_immutability` (`fn_protect_bom_component_immutability()`) block `UPDATE` / `DELETE` of historical fields (`expected_yield_pkts`, `version_no`, `effective_date`, `bom_components`) directly inside the database even if invoked outside the API.

## Historical Run Preservation Proof
`production.production_runs.bom_version_id` references `production.bom_versions(id) ON DELETE RESTRICT`. Creating & activating BOM `v2` (e.g., changing flour to `45 kg` / `225` packets) never alters prior runs: reopening an earlier run created under `v1` displays `version_no = 1`, `40 kg` flour, and `200` expected packets identically.
