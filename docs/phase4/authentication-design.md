# Authentication & Authorization Design

## 1. Password Storage & Token Lifecycle
- **Password Hashing:** `pwdlib` with **Argon2id** (`PasswordHash.recommended()`). Plaintext passwords are never stored, logged, or returned in API payloads.
- **Token Minting:** Signed `HS256` JWTs (`PyJWT`) carrying `sub` (user ID), `role` (`SALESMAN`, `FACTORY_ADMIN`, etc.), `username`, `iat`, and `exp` (`480` minutes dev default).
- **Production Safety Guard:** `Settings.validate_production_safety` refuses startup if `ENVIRONMENT=production` with default `JWT_SECRET_KEY` or `ENABLE_DEV_SEED=true`.

## 2. Server-Side Authorization Enforcement
1. **Endpoint Role Guards (`iam_service.require_roles(...)`):** Every protected endpoint declares allowed roles on the server. Unauthorized calls write an `ACCESS_DENIED` entry to `audit.audit_logs` and return `403 Forbidden`.
2. **Ownership Scoping (`Salesman` Isolation):**
   - `GET /sales/customers` and `POST /orders` verify `customer.assigned_salesman_id == actor.user_id` (or `NULL` shared).
   - `GET /orders/my` filters `SalesOrder.salesman_id == actor.user_id`.
   - `GET /orders/{order_id}` rejects a salesman requesting another salesman's order with `403 Forbidden`.
3. **PostgreSQL Session Context Hook:** `get_current_actor` executes `SELECT set_config('app.current_user_id', ...), set_config('app.current_role', ...)` inside the request transaction (`SET LOCAL` equivalent), preparing the database layer for Phase 5+ PostgreSQL RLS policies.
4. **Frontend Routing:** `RequireRole` redirects users cleanly for UX ergonomics only; security rests 100% on backend API validation.

## 3. Development Seed Accounts (Dev-Only)

| Role | Username | Password (Dev Seed Only) |
| --- | --- | --- |
| Salesman A (`SM-001`) | `salesman_a` | `SalesA@2026!` |
| Salesman B (`SM-002`) | `salesman_b` | `SalesB@2026!` |
| Factory Admin | `admin` | `Admin@2026!` |
| Production Supervisor | `supervisor` | `Prod@2026!` |
| Accountant / Auditor | `auditor` | `Audit@2026!` |
| Owner | `owner` | `Owner@2026!` |
