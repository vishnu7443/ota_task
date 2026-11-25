# Database Security & Defense-in-Depth Design

**Principle:** Frontend hiding and API middleware checks are necessary but **not sufficient** against privilege escalation, buggy SQL queries, or direct DB console access. Security is enforced in depth at the PostgreSQL role, trigger, and Row-Level Security (RLS) layer.

---

## 1. PostgreSQL Role Hierarchy & Principle of Least Privilege

| PostgreSQL Role | Assigned Purpose | Schema & Table Privileges | Explicitly Blocked Operations |
| --- | --- | --- | --- |
| **`ota_schema_owner`** | Used **strictly** during schema migrations (`V001`–`V012`); disabled from runtime app connections. | `CREATE`, `ALTER`, ownership of tables/views/triggers. | Never used by backend web worker pool. |
| **`ota_app_rw`** | Primary runtime connection role for application services. | `USAGE` on operational schemas; `SELECT, INSERT, UPDATE` on mutable business tables; `SELECT, INSERT` **only** on append-only tables (`inventory.inventory_movements`, `audit.audit_logs`, `sales.sales_order_status_history`). | **No `DDL` (`CREATE/DROP/ALTER/TRUNCATE`)**; **`REVOKE UPDATE, DELETE` on `inventory_movements`, `audit_logs`, `sales_order_status_history`**; **`REVOKE DELETE` on `invoices`, `credit_notes`, `payments`, `production_runs`, `purchase_receipts`**. |
| **`ota_auditor_ro`** | Dedicated read-only connection role (or session-switched role) for Accountant/Auditor reporting exports & BI tools. | `SELECT` only on `reporting.*` views and posted operational tables (`sales`, `billing`, `purchasing`, `inventory`, `production`, `costing`, `finance`, `audit`). | Zero `INSERT`, `UPDATE`, `DELETE`, `EXECUTE` on mutating functions; zero access to `iam.users.password_hash`! |

### Column-Level Protection on Credentials
- `REVOKE SELECT ON iam.users FROM ota_auditor_ro;` and grant `SELECT (id, role_id, username, full_name, is_active, created_at)` — preventing `password_hash` exposure even in read-only audit queries.

---

## 2. Row-Level Security (`RLS`) Strategy

Because the application connects using a shared pool (`ota_app_rw`), each authenticated request executes inside a database transaction setting session-local context variables:
```sql
SET LOCAL app.current_user_id = '42';
SET LOCAL app.current_role    = 'SALESMAN';
```

### Key RLS Policies
1. **Salesman Order Isolation (`sales.sales_orders` & `sales.sales_order_items`):**
   - When `current_setting('app.current_role', true) = 'SALESMAN'`:
     - `SELECT / INSERT / UPDATE` allowed **only** when `salesman_id = current_setting('app.current_user_id')::BIGINT`.
     - `UPDATE` restricted further via `WITH CHECK (status IN ('DRAFT','CORRECTION_REQUESTED'))` — preventing a rogue SQL query under a Salesman session from changing `status = 'APPROVED'`.
   - `FACTORY_ADMIN`, `OWNER`, `ACCOUNTANT_AUDITOR` bypass the salesman filter for full read visibility; `PRODUCTION_SUPERVISOR` is denied (`FALSE`) from querying `sales.sales_orders` directly.
2. **Customer Scope (`sales.customers`, if `DEC-05` restricts territories):**
   - If territory isolation is enabled, Salesmen see only `assigned_salesman_id = current_user_id` (plus unassigned shared accounts if policy allows).
3. **Cost & Purchase Confidentiality (`costing.*`, `purchasing.*`, `inventory.cost_lots`):**
   - `SALESMAN` session receives **zero rows (`USING (FALSE)`)** on `costing.production_cost_summaries`, `costing.production_overheads`, `purchasing.purchase_receipt_items`, and `inventory.cost_lots`, guaranteeing factory margins and ingredient rates can never leak to field mobile sessions!
4. **Read-Only Auditor Enforcement (`ACCOUNTANT_AUDITOR`):**
   - When `app.current_role = 'ACCOUNTANT_AUDITOR'`, RLS `FOR INSERT / UPDATE / DELETE` policies across all operational tables evaluate `USING (FALSE)` as a second lock behind API RBAC middleware (`INV-SEC-01`).

---

## 3. Sensitive Data & Immutability Controls

1. **Authentication Secrets:** `iam.users.password_hash` stores strong salted password hashes (`Argon2id` / `bcrypt`) — never plaintext or reversible encryption.
2. **Customer & Tax PII:** `gstin`, `phone`, and `customer_addresses` are accessible only to authorized internal roles (`Admin`, `Auditor`, `Owner`, and owning `Salesman`). Database connections mandate TLS (`sslmode=require` in hosted environments).
3. **Database-Enforced Append-Only Triggers (`audit.audit_logs` & `inventory.inventory_movements`):**
   - Even if an operator logs in via `psql` as `ota_app_rw`, `BEFORE UPDATE OR DELETE` triggers raise `SQLSTATE '42501' (insufficient_privilege)` so posted financial/ledger history and audit trails cannot be silently altered or purged.
4. **Security Event Auditing:** Failed authorization (`403`) attempts and role/user status modifications (`iam.users`) write immutable rows to `audit.audit_logs`.
