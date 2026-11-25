# Production & BOM API Reference (`docs/phase7/api-documentation.md`)

Base prefix: `/api/v1/production` (registered in [main.py](file:///d:/mac/ota/backend/app/main.py); routes defined in [router.py](file:///d:/mac/ota/backend/app/modules/production/router.py)).

## Role Permissions
- **Viewers (`_ProdViewer`):** `FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR`, `ACCOUNTANT_AUDITOR`, `OWNER`.
- **Operators (`_ProdOperator`):** `FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR` (all mutations reject `SALESMAN`, `ACCOUNTANT_AUDITOR`, and `OWNER` with `403`).
- **Alert Acknowledge (`_AlertAckActor`):** `FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR`, `OWNER`.

## Endpoints

| Method | Path | Role | Summary |
|---|---|---|---|
| `GET` | `/catalog` | Viewer | Products, pack sizes (`has_active_bom`, `active_bom_version_no`), recipe templates |
| `POST` | `/catalog/pack-sizes` | Operator | Create SKU (`201`, e.g., `MRK-500G` under shared product) |
| `POST` | `/catalog/materials` | Operator | Create raw/packaging material (`201`) + zero balance row |
| `GET` | `/bom` | Viewer | List all BOM headers with active & historical versions |
| `GET` | `/bom/{pack_size_id}` | Viewer | Get BOM header & version history for a pack size |
| `POST` | `/bom/versions` | Operator | Create `DRAFT` (or immediately `ACTIVE`) BOM version (`201`) |
| `PUT` | `/bom/versions/{version_id}` | Operator | Edit `DRAFT` BOM version (`409 IMMUTABLE_BOM_VERSION` if active/superseded) |
| `POST` | `/bom/versions/{version_id}/activate` | Operator | Activate `DRAFT`, atomically superseding prior `ACTIVE` version |
| `DELETE` | `/bom/versions/{version_id}` | Operator | Delete `DRAFT` version (`409` if non-draft) |
| `POST` | `/bom/calculate` | Viewer | Scale BOM by `batch_multiplier` or `target_output_pkts`, with stock comparison & carton rounding |
| `GET` | `/bom/{pack_size_id}/calculate` | Viewer | Query-param variant of BOM calculator |
| `GET` | `/dashboard` | Viewer | KPIs, open shortages, open alerts, and filterable run list (`status`, `pack_size_id`) |
| `GET` | `/runs/{run_id}` | Viewer | Full run detail (`material_issues`, `outputs`, `wastages`, `variances`, `alerts`) |
| `POST` | `/runs` | Operator | Create run (`DRAFT` or `PLANNED`), pinning current active `BomVersion` |
| `POST` | `/runs/{run_id}/plan` | Operator | `DRAFT -> PLANNED` transition |
| `POST` | `/runs/{run_id}/issue-materials` | Operator | `PLANNED -> IN_PROGRESS`; FIFO issue (`PROD_ISSUE_OUT`), `409 DOUBLE_MATERIAL_ISSUE` / `INSUFFICIENT_STOCK` |
| `POST` | `/runs/{run_id}/complete` | Operator | `IN_PROGRESS -> COMPLETED`; records good/rejected packets & consumption/damage split |
| `POST` | `/runs/{run_id}/post` | Operator | `COMPLETED -> POSTED`; atomic reconciliation, FG lot, variances, alerts (`409 DUPLICATE_POST`) |
| `POST` | `/runs/{run_id}/cancel` | Operator | Cancel `DRAFT`/`PLANNED` or abort `IN_PROGRESS` (returning unspoiled material via `PROD_RETURN_IN`) |
| `GET` | `/alerts` | Viewer | List variance alerts (`?status=OPEN\|ACKNOWLEDGED`) |
| `POST` | `/alerts/{alert_id}/acknowledge` | AckActor | Acknowledge alert (`409 ALREADY_ACKNOWLEDGED` on replay) |
| `GET` | `/reports/variances` | Viewer | Tabular variance & yield report across runs |
