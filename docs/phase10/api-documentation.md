# Phase 10 API Documentation

All routes are served under `/api/v1` with Bearer JWT authentication and backend-enforced RBAC.

---

## 1. Centralized Audit & Activity (`/api/v1/audit`)
*Allowed Roles: `FACTORY_ADMIN`, `ACCOUNTANT_AUDITOR`, `OWNER`*

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/audit/logs` | Paginated audit trail query with `actor_user_id`, `actor_role`, `action`, `entity_schema`, `entity_table`, `entity_id`, `correlation_ref`, `date_from`, `date_to`, `search`, `page`, `page_size`. |
| `GET` | `/audit/logs/export/csv` | Stream filtered audit events as CSV (`audit_logs_export.csv`). |
| `GET` | `/audit/logs/{audit_id}` | Fetch detailed audit event with sanitized `before_state`, `after_state`, and `metadata_json`. |
| `GET` | `/audit/summary` | Aggregate counts for total events, security events, failed logins, denied accesses, and breakdown by schema/action. |
| `GET` | `/audit/user-activity` | Per-user activity summary (`login_success_count`, `login_failed_count`, `access_denied_count`, `business_events_count`, `last_login_at`). |

---

## 2. IAM User & Role Governance (`/api/v1/iam`)
*Viewers (`GET`): `FACTORY_ADMIN`, `OWNER`, `ACCOUNTANT_AUDITOR` · Mutators (`POST`/`PATCH`): `FACTORY_ADMIN`, `OWNER`*

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/iam/roles` | List system RBAC roles. |
| `GET` | `/iam/users` | List all system users with active flag and last login timestamp. |
| `POST` | `/iam/users` | Provision new user (auto-creates `SalesmanProfile` for `SALESMAN`) with bcrypt password & `USER_CREATED` audit event. |
| `PATCH` | `/iam/users/{user_id}` | Update `role_code`, `is_active`, or `full_name` with mandatory audit `reason` (`USER_ROLE_CHANGED` / `USER_STATUS_CHANGED`). Blocks self-deactivation. |

---

## 3. Cross-Module Reconciliation (`/api/v1/reconciliation`)
*Allowed: `FACTORY_ADMIN`, `OWNER`, `ACCOUNTANT_AUDITOR` (read-only), and `PRODUCTION_SUPERVISOR` (strictly scoped to `INVENTORY` & `PRODUCTION`)*

### Live Diagnostic Reports & CSV Export
| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/reconciliation/reports/inventory` | Opening + Inward - Outward vs persisted balance & open `CostLot` parity. |
| `GET` | `/reconciliation/reports/inventory/export/csv` | Export Inventory reconciliation table as UTF-8 CSV. |
| `GET` | `/reconciliation/reports/sales` | Approved/Invoiced Orders vs Issued Invoices parity. |
| `GET` | `/reconciliation/reports/invoices` | Invoice line sums, GST CGST/SGST/IGST split & Credit Note parity. |
| `GET` | `/reconciliation/reports/payments` | Payment allocations, refunds & `CustomerReceivable` parity. |
| `GET` | `/reconciliation/reports/dispatch` | Issued Invoices vs Posted Dispatches vs `DISPATCH_OUT` ledger parity. |
| `GET` | `/reconciliation/reports/production` | Production output, material consumption ledger, costing totals & flagged variances. |

### Formal Reconciliation Workflow & Resolution
| Method | Path | Roles Permitted | Purpose |
| --- | --- | --- | --- |
| `GET` | `/reconciliation/runs` | Viewers (Supervisor ops-scoped) | List formal reconciliation runs. |
| `POST` | `/reconciliation/runs` | `FACTORY_ADMIN`, `OWNER`, `PRODUCTION_SUPERVISOR` (ops) | Start deterministic scan (`REC/YYYY-YY/NNNN`) & persist discrepancies. |
| `GET` | `/reconciliation/runs/{run_id}` | Viewers (Supervisor ops-scoped) | Fetch full run details, discrepancies & immutable events. |
| `POST` | `/reconciliation/runs/{run_id}/rerun` | Operators (`AUDITOR` blocked) | Re-verify domain scan; auto-resolves cleared discrepancies. |
| `POST` | `/reconciliation/runs/{run_id}/close` | `FACTORY_ADMIN`, `OWNER` | Close run after all discrepancies are `RESOLVED` or `DISMISSED`. |
| `GET` | `/reconciliation/discrepancies` | Viewers (Supervisor ops-scoped) | List discrepancies across runs. |
| `POST` | `/reconciliation/discrepancies/{id}/investigate` | Operators (`AUDITOR` blocked) | Transition to `UNDER_REVIEW` and assign/log notes. |
| `POST` | `/reconciliation/discrepancies/{id}/propose` | Operators (`AUDITOR` blocked) | Propose corrective action category (`ACTION_PROPOSED`). |
| `POST` | `/reconciliation/discrepancies/{id}/approve` | `FACTORY_ADMIN`, `OWNER` | Approve proposed corrective action (`APPROVED`). |
| `POST` | `/reconciliation/discrepancies/{id}/resolve` | `FACTORY_ADMIN` ONLY | Post authorized `STOCK_ADJUSTMENT` or document dismissal (`RESOLVED` / `DISMISSED`). |

---

## 4. Management Intelligence (`/api/v1/intelligence`)
*Allowed Roles: `FACTORY_ADMIN`, `OWNER`, `ACCOUNTANT_AUDITOR`*

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/intelligence/dashboard` | Unified executive metrics (Sales, GST, COGS, Gross Margin, Collections, Ageing, Stock Valuation, Production Yield, Watchlist). |
| `GET` | `/intelligence/reports/export/csv` | Export executive intelligence summary & breakdowns to CSV. |
