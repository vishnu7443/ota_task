# Supplier Management (`docs/phase6/supplier-management.md`)

## Overview
Phase 6 introduces the `purchasing.suppliers` master for raw material and packaging vendors serving **Kaveri Traditional Snacks Pvt. Ltd.**, independently engineered against the Phase 3 PostgreSQL schema.

## Schema & Constraints (`purchasing.suppliers`)
- **Primary Key:** `id` (`BIGSERIAL`).
- **Natural Unique Key:** `code` (`VARCHAR(32)`, uppercased server-side, unique).
- **GST Validation:**
  - `state_code` must be a 2-digit GST state code (`^[0-9]{2}$`).
  - Optional `gstin` (`VARCHAR(15)`) must match the 15-character Indian GST format (`^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$`) and its first two digits must equal `state_code` (`gstin_matches_state`).
- **Status Control:** `is_active` (`BOOLEAN`, default `true`) allows deactivating obsolete suppliers cleanly without deleting historical purchase orders or receipts (`ON DELETE RESTRICT`).

## Capabilities & Roles
- **View & History (`FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR`, `ACCOUNTANT_AUDITOR`, `OWNER`):**
  - Search by code, name, or GSTIN (`GET /api/v1/purchasing/suppliers`).
  - View supplier statistics (`po_count`, `receipt_count`, `total_purchased_paisa`) and full linked PO + Goods Receipt history (`GET /api/v1/purchasing/suppliers/{supplier_id}`).
- **Create / Edit (`FACTORY_ADMIN` only):**
  - `POST /api/v1/purchasing/suppliers` and `PUT /api/v1/purchasing/suppliers/{supplier_id}` enforce backend Pydantic + DB validation and write `SUPPLIER_CREATED` / `SUPPLIER_UPDATED` records to `audit.audit_logs`.
- **`SALESMAN`:** Denied access (`403 Forbidden`).

## Seeded Benchmark Master
- `SUP-001` — **Cauvery Agro Mills** (Tamil Nadu `33`, GSTIN `33AAACS7777P1Z1`, Tiruchirappalli).
