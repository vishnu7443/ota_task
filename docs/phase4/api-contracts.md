# API Contracts (v1 — Phase 4 Vertical Slice)

**Base URL:** `/api/v1`  
**Error Envelope:** All errors return `{"error": {"code": "<CODE>", "message": "<Human message>", "details": ...}}`.

---

## 1. System & Health

- **`GET /api/v1/health`** *(Public)*
  - **200 OK:** `{"status": "ok", "database": "connected", "environment": "development"}`

---

## 2. Authentication (`iam`)

- **`POST /api/v1/auth/login`** *(Public)*
  - **Request:** `{"username": "salesman_a", "password": "..."}`
  - **200 OK:** `{"access_token": "<jwt>", "token_type": "bearer", "user": {"id", "username", "full_name", "role_code", "role_name", "is_active", "last_login_at"}}`
  - **401:** `AUTHENTICATION_FAILED`
- **`GET /api/v1/auth/me`** *(Bearer JWT required)*
  - **200 OK:** `UserPublic`

---

## 3. Sales Catalog (`sales`)

- **`GET /api/v1/sales/customers?search=...`** *(Roles: `SALESMAN`, `FACTORY_ADMIN`, `OWNER`, `ACCOUNTANT_AUDITOR`)*
  - `SALESMAN` receives only active customers where `assigned_salesman_id == user_id` or `NULL`.
  - **200 OK:** List of `CustomerSummary` (including `primary_state_code`, `gstin`, `default_shipping_address`).
- **`GET /api/v1/sales/products?customer_id=...`** *(Roles: `SALESMAN`, `FACTORY_ADMIN`, `OWNER`, `ACCOUNTANT_AUDITOR`)*
  - Returns active finished SKU pack sizes (`Murukku 200 g`, `MRK-200G`) with authoritative `selling_price_paisa` (`5000`), `packets_per_carton` (`20`), `gst_rate_bps` (`500`), and read-only `available_stock_pkts` (`50`).

---

## 4. Salesman Orders (`orders`)

- **`POST /api/v1/orders`** *(Role: `SALESMAN` only)*
  - **Request:** `{"customer_id": 1, "client_order_id": "<uuid>", "notes": "...", "items": [{"pack_size_id": 1, "ordered_qty_pkts": 150}]}`
  - Client prices/totals are neither required nor accepted (ignored if sent).
  - **201 Created** (first submission) or **200 OK** (`is_duplicate_replay: true` when `(salesman_id, client_order_id)` matches): returns full `OrderDetailResponse` with server-computed `taxable_total_paisa` (`750000`), GST estimate (`18750 + 18750 = 37500` paise), `grand_total_paisa` (`787500`), and read-only shortage check (`has_shortage: true` when `150 > 50`).
  - **403:** Customer assigned to another salesman or non-salesman caller. **404:** Missing customer. **422:** Invalid qty `<= 0`, duplicate SKUs, or unknown SKU.
- **`GET /api/v1/orders/my?status=...&page=1&page_size=20`** *(Role: `SALESMAN` only)*
  - Returns paginated orders owned by authenticated salesman.
- **`GET /api/v1/orders/{order_id}`** *(Roles: `SALESMAN` [own only -> `403` otherwise], `FACTORY_ADMIN`, `OWNER`, `ACCOUNTANT_AUDITOR`)*

---

## 5. Admin Order Visibility (`admin/orders`)

- **`GET /api/v1/admin/orders?status=...&has_shortage=...&search=...&page=1&page_size=20`** *(Roles: `FACTORY_ADMIN`, `OWNER`, `ACCOUNTANT_AUDITOR`)*
  - Returns paginated `OrderSummaryResponse` items directly from PostgreSQL `sales.sales_orders`.
- **`GET /api/v1/admin/orders/{order_id}`** *(Roles: `FACTORY_ADMIN`, `OWNER`, `ACCOUNTANT_AUDITOR`)*
  - Returns full `OrderDetailResponse` with customer GSTIN/address, salesman profile, live `on_hand`/`reserved`/`available`/`shortage` per line, GST breakdown, status history, and verification snapshot.
