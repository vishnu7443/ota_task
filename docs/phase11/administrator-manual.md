# Administrator Manual — Order-to-Audit ERP (`Kaveri Traditional Snacks Pvt. Ltd.`)

Intended for system administrators, internal auditors (`ACCOUNTANT_AUDITOR`), and business owners (`OWNER`) overseeing governance, reconciliation, security, backups, and compliance.

---

## 1. User Governance & Role Matrix (`/admin/users`)

- **Provisioning Users (`FACTORY_ADMIN` / `OWNER`):** Create user accounts assigning one of 5 system roles (`SALESMAN`, `PRODUCTION_SUPERVISOR`, `FACTORY_ADMIN`, `ACCOUNTANT_AUDITOR`, `OWNER`). If creating a `SALESMAN`, include `employee_code` and `territory`. Passwords are hashed using Argon2id (`pwdlib`).
- **Role & Activation Changes (`OWNER` / `FACTORY_ADMIN` governance controls):** Deactivating a user (`is_active = false`) requires a documented reason, records `USER_STATUS_CHANGED` / `USER_ROLE_CHANGED` in `audit.audit_logs`, and blocks login immediately (`401`).
- **Segregation of Duties Enforced:**
  - `ACCOUNTANT_AUDITOR` & `OWNER` are strictly blocked (`403`) from mutating sales orders, GRNs, stock adjustments, invoices, dispatches, payments, or refunds.
  - Self-approval separation in Reconciliation: the actor who proposes a discrepancy correction cannot approve their own proposal (`APPROVED` requires distinct oversight role).

---

## 2. Centralized Audit Explorer (`/admin/audit`)

- Every significant business and security event (`LOGIN_SUCCESS`, `LOGIN_FAILED`, `ACCESS_DENIED`, order approvals/rejections, PO/GRN posts, inventory adjustments, BOM activations, production posts, GST invoice issuance, credit notes, dispatches, payments/reversals/refunds, customer/price edits, user/role updates) appends an immutable row to `audit.audit_logs`.
- **Correlation Tracking:** Request middleware injects `X-Request-ID: REQ-xxxxxxxx` across HTTP responses and audit log records so multi-step actions share traceable correlation references.
- **Secret Redaction:** `_SENSITIVE_KEYS` (`password`, `password_hash`, `token`, `access_token`, `refresh_token`, `secret`, `authorization`, `jwt`) are automatically redacted before persistence.
- **Immutability Guarantee:** PostgreSQL triggers (`fn_prevent_mutation()`) block any `UPDATE` or `DELETE` SQL statement against `audit.audit_logs`, `inventory.inventory_movements`, `sales.sales_order_status_history`, and `billing.dispatch_status_history`.
- **CSV Export:** Filter by actor, action, entity table, date range, or correlation ref (`search`) and export verified audit trails directly via **Export CSV**.

---

## 3. Cross-Module Reconciliation & Period Close (`/admin/reconciliation`)

Run automated reconciliation sweeps (`REC/YYYY-YY/NNNN`) across modules (`INVENTORY`, `SALES`, `FINANCE`, `PRODUCTION`, or `FULL_SYSTEM`):

1. **Inventory Ledger Parity:** Recomputes `Opening + Purchase/Prod/Return Inward - Production/Dispatch/Damage/Return Outward` against `inventory.inventory_balances` AND open FIFO/FEFO `inventory.cost_lots`. Any divergence raises `INV_BAL_MISMATCH` / `COST_LOT_MISMATCH`.
2. **Sales-to-Billing Parity:** Detects `APPROVED` orders awaiting invoice (`APPROVED_ORDER_UNINVOICED`), duplicate active invoices, or quantity mismatches.
3. **GST Invoice, Credit Note & AR Parity:** Verifies persisted invoice line sums, CGST/SGST vs IGST tax rules, active payment allocations vs `payments.allocated_paisa`, and `customer_receivables` projections (`INV_AR_OUTSTANDING_MISMATCH`).
4. **Dispatch-to-Ledger Parity:** Reconciles `DISPATCHED` invoices against `DISPATCH_OUT` stock ledger rows.
5. **Production & Variance Sweep:** Checks `PROD_OUTPUT_IN` and material issue movements vs run records, costing sums, and flags tolerance-exceeding BOM variances (`BOM_CONSUMPTION_VARIANCE`, severity `LOW`) for supervisor acknowledgement.
6. **Controlled Discrepancy Resolution:** Workflow states progress `OPEN -> INVESTIGATING -> CORRECTION_PROPOSED -> APPROVED -> RESOLVED` (posting legitimate `StockAdjustment` rows or dismissing justified low-severity variances with documented notes), followed by **Re-Run** auto-verification and **Close Run** (locking the run immutably).

---

## 4. Management Intelligence Oversight (`/admin/intelligence`)

- Accessible strictly to `OWNER`, `FACTORY_ADMIN`, and `ACCOUNTANT_AUDITOR`.
- **Single-Source Metrics:** Reads directly from live Phase 6–9 services (GST Billing, Payments/AR, FIFO Batch Costing & Profitability, Inventory Overview, Production Runs, Overdue Ageing) without duplicating ledger tables.
- **Accounting Scope Clarification:** Reported **Gross Profit** reflects `Net Revenue (excl. GST) - Production COGS (FIFO)`. Non-production administrative expenses and Net Profit are explicitly excluded and noted by the API disclaimer.

---

## 5. Production Security, Backup & Log Checklist

1. Set `ENVIRONMENT=production`, `ENABLE_DEV_SEED=false`, strong random 32+ char `JWT_SECRET_KEY`, and restricted `CORS_ORIGINS` (see [`docs/phase11/deployment-guide.md`](file:///d:/mac/ota/docs/phase11/deployment-guide.md)).
2. Schedule automated `pg_dump` backups of PostgreSQL (`ota_prod` / `ota_dev`), testing restoration onto an isolated staging database before upgrades.
3. Rotate logs carefully (`JSON` structured HTTP request logs with `X-Request-ID` in `app/core/logging.py`) and ensure `.env` secrets are never tracked in Git.
4. Apply Alembic schema migrations (`uv run alembic upgrade head`) inside maintenance windows prior to rolling backend container restarts.
