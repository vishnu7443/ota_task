# Security & Authorization Testing Report — Phase 11

This report summarizes implemented security controls and observed negative-test results verified across [`test_auth.py`](file:///d:/mac/ota/backend/tests/test_auth.py), [`test_orders_vertical_slice.py`](file:///d:/mac/ota/backend/tests/test_orders_vertical_slice.py), [`test_phase10_audit_reconciliation.py`](file:///d:/mac/ota/backend/tests/test_phase10_audit_reconciliation.py), and [`test_phase11_integration_benchmark_security.py`](file:///d:/mac/ota/backend/tests/test_phase11_integration_benchmark_security.py).

---

## 1. Authentication, Credential & Session Security

| Control Area | Implementation | Negative Test Executed | Observed Status |
| --- | --- | --- | --- |
| Password Hashing | Argon2id via `pwdlib` ([`security.py`](file:///d:/mac/ota/backend/app/core/security.py)) | Invalid password login attempts (`Wrong!Password`, `SuperSecretWrongPassword!99`) | **HTTP `401`** + `LOGIN_FAILED` logged |
| Stateless JWT Integrity | HS256 requiring `sub`, `role`, `exp` claims | Missing Bearer header & tampered `invalid.jwt.token` across protected endpoints | **HTTP `401 Unauthorized`** |
| Account Deactivation Lock | `User.is_active` checked during login & token resolution | Owner deactivates `temp_p11` via `PATCH /iam/users/{id}`; immediate login retry | **HTTP `401`** (`USER_STATUS_CHANGED` audited) |
| Production Config Safety | `validate_production_safety()` in [`config.py`](file:///d:/mac/ota/backend/app/core/config.py) | Fails fast if `ENVIRONMENT=production` sets `ENABLE_DEV_SEED=true` or weak/`dev_only` `JWT_SECRET_KEY` (< 32 chars) | Enforced cleanly at settings load |
| Secret Redaction in Audit Logs | `_SENSITIVE_KEYS` strips `password`, `password_hash`, `token`, `access_token`, `secret`, `authorization`, `jwt` | Verified serialized audit events (`test_phase10` & `test_phase11`) contain zero raw passwords | **`0` leaked credentials** |

---

## 2. Five-Role RBAC & Segregation-of-Duties Matrix (Tested via Negative Assertions)

| Endpoint / Operation | `SALESMAN` | `PRODUCTION_SUPERVISOR` | `FACTORY_ADMIN` | `ACCOUNTANT_AUDITOR` | `OWNER` |
| --- | --- | --- | --- | --- | --- |
| Mobile Order Entry & Own Orders (`/orders/my`, `/orders`) | Allow (`201`) | Denied (`403`) | Read (`200`) | Read (`200`) | Read (`200`) |
| Order Approvals & Price Overrides (`/admin/orders/{id}/*`) | Denied (`403`) | Denied (`403`) | **Allow (`200`)** | Denied (`403`) | Denied (`403`) |
| Customer Create & SKU Price Update (`POST /sales/customers`, `PATCH /sales/products/{id}/price`) | Denied (`403`) | Denied (`403`) | **Allow (`201`/`200`)** | Denied (`403`) | Denied (`403`) |
| Customer Master Isolation (`GET /sales/customers`) | Own assigned (`200`) | Allowed catalog (`200`) | All (`200`) | All (`200`) | All (`200`) |
| PO / GRN Creation & Production Execution (`/production/*`) | Denied (`403`) | **Allow** | Allow / Approve PO & GRN | Read only | Read only |
| GST Invoices, Dispatches, Credit Notes (`/billing/*` writes) | PDF download only (`200`) | Denied (`403`) | **Allow** | Read only (`403` write) | Read only (`403` write) |
| Customer Payments, Refunds, Reversals (`/finance/*` writes) | Own AR read only | Denied (`403`) | **Allow** | Read only (`403` write) | Read only (`403` write) |
| Audit Explorer & Reconciliation Reports (`/audit/*`, `/reconciliation/*`) | Denied (`403`) | Denied on Audit/Sales (`403`); `INVENTORY` recon allowed | Allow + `STOCK_ADJUSTMENT` resolution | **Read & Export Only (`403` mutations)** | Read + Approve corrections (`403` adjustment post) |
| Management Intelligence (`/intelligence/dashboard`, CSV export) | Denied (`403`) | Denied (`403`) | Allow (`200`) | Allow (`200`) | **Allow (`200`, Landing Page)** |

*(Every denied attempt records an `ACCESS_DENIED` event in `audit.audit_logs` tied to `REQ-` correlation IDs.)*

---

## 3. Injection, Input Tampering, Idempotency & DB Trigger Protections

- **SQL Injection Immunity:** Parameterized SQLAlchemy ORM queries across all modules tested in `test_phase11` (`test_3`) using payloads `"' OR '1'='1"`, `"x'; DROP TABLE sales.customers;--"`, and `"%' UNION SELECT password_hash FROM iam.users--"` inside `/api/v1/sales/customers?search=` and `/api/v1/audit/logs?search=`; returned clean empty `200` responses with zero DB errors or unauthorized row exposure.
- **Client Price & Tax Tampering Ignored (`test_orders_vertical_slice`):** Server always computes unit prices, GST split (`INTRA_STATE` vs `INTER_STATE`), line totals, and invoice grand totals from PostgreSQL masters, ignoring tampered client values.
- **Idempotency & Anti-Double-Posting:** Duplicate `client_order_id`, `client_receipt_id`, `client_payment_id`, double material issue (`DOUBLE_MATERIAL_ISSUE`), double production post (`DUPLICATE_POST`), duplicate active invoice (`DUPLICATE_INVOICE`), and duplicate dispatch post (`DUPLICATE_DISPATCH_POST`) cleanly return replay or `409 Conflict`.
- **PostgreSQL Trigger Tamper Resistance:** Direct SQL `DELETE`/`UPDATE` attempts on `audit.audit_logs`, `inventory.inventory_movements`, `sales.sales_order_status_history`, and closed `audit.reconciliation_runs` abort with `DBAPIError` raised by `fn_prevent_mutation()`.
- **HTTP Headers (`frontend/nginx.conf`):** Production container adds `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, and `Referrer-Policy: strict-origin-when-cross-origin`; CORS restricts origins, methods, and headers explicitly via [`main.py`](file:///d:/mac/ota/backend/app/main.py).
