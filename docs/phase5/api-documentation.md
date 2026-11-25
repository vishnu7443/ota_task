# API Documentation (Phase 5 Endpoints)

All endpoints sit under `/api/v1` and return `{"error": {"code", "message", "details"}}` on failure.

---

## 1. Catalog Filter Extension (`sales`)

- **`GET /api/v1/sales/salesmen`** *(Roles: `FACTORY_ADMIN`, `OWNER`, `ACCOUNTANT_AUDITOR`)*
  - **200 OK:** `[{"user_id", "full_name", "employee_code", "territory"}]` — powers Admin queue salesman filters dynamically.

---

## 2. Admin Order Management & Verification (`admin/orders`)

- **`GET /api/v1/admin/orders/summary`** *(Roles: `FACTORY_ADMIN`, `OWNER`, `ACCOUNTANT_AUDITOR`)*
  - **200 OK:** Aggregate counts (`total_count`, `submitted_count`, `under_review_count`, `correction_requested_count`, `pending_verification_count`, `approved_count`, `rejected_count`, `cancelled_count`, `shortage_count`, `pending_value_paisa`, `approved_value_paisa`).
- **`GET /api/v1/admin/orders`** *(Roles: `FACTORY_ADMIN`, `OWNER`, `ACCOUNTANT_AUDITOR`)*
  - **Query Params:** `status` (comma-separated supported), `pending_verification=true`, `customer_id`, `salesman_id`, `date_from` (`YYYY-MM-DD`), `date_to` (`YYYY-MM-DD`), `has_shortage`, `search`, `page`, `page_size`.
- **`GET /api/v1/admin/orders/{order_id}`** *(Roles: `FACTORY_ADMIN`, `OWNER`, `ACCOUNTANT_AUDITOR`)*
  - Returns full `OrderDetailResponse` including `original_unit_price_paisa`, `effective_qty_pkts`, `is_qty_modified`, `is_price_modified`, `reservations`, `status_history`, `approvals`, and `audit_trail`.
- **`PATCH /api/v1/admin/orders/{order_id}`** *(Role: `FACTORY_ADMIN` only)*
  - **Request:** `{"items": [{"id", "approved_qty_pkts", "unit_price_paisa"}], "admin_remarks", "reason", "expected_version"}`
  - Validates order is in `SUBMITTED` or `UNDER_REVIEW` (`409 ORDER_LOCKED` otherwise), enforces `reason >= 5 chars` when modifying qty/price (`422`), recalculates taxable & GST totals server-side, updates `has_shortage`, transitions `SUBMITTED -> UNDER_REVIEW` if needed, logs audit diffs.
- **`POST /api/v1/admin/orders/{order_id}/review`** *(Role: `FACTORY_ADMIN` only)*
  - Transitions `SUBMITTED -> UNDER_REVIEW` (or refreshes snapshot if already `UNDER_REVIEW` without duplicate history) and saves optional `admin_remarks`.
- **`POST /api/v1/admin/orders/{order_id}/request-correction`** *(Role: `FACTORY_ADMIN` only)*
  - **Request:** `{"reason": "...(min 5 chars)", "admin_remarks", "expected_version"}` -> sets status `CORRECTION_REQUESTED`.
- **`POST /api/v1/admin/orders/{order_id}/approve`** *(Role: `FACTORY_ADMIN` only)*
  - **Request:** `{"admin_remarks", "reason", "expected_version"}`
  - Locks `SalesOrder` & `InventoryBalance` rows (`FOR UPDATE`), verifies `available >= effective_qty` across all lines (`409 INSUFFICIENT_STOCK` on shortage), reserves stock in `inventory_balances` + `inventory.stock_reservations`, transitions to `APPROVED`, logs `ORDER_APPROVED` + `STOCK_RESERVED`.
- **`POST /api/v1/admin/orders/{order_id}/reject`** *(Role: `FACTORY_ADMIN` only)*
  - **Request:** `{"reason": "...(min 5 chars)", "admin_remarks", "expected_version"}` -> terminal `REJECTED`.
- **`POST /api/v1/admin/orders/{order_id}/cancel`** *(Role: `FACTORY_ADMIN` only)*
  - **Request:** `{"reason": "...(min 5 chars)", "admin_remarks", "expected_version"}` -> terminal `CANCELLED`; releases active `StockReservation` rows if cancelling an `APPROVED` order.

---

## 3. Salesman Tracking, Correction & Withdrawal (`orders`)

- **`GET /api/v1/orders/my`** *(Role: `SALESMAN` only)*: Supports comma-separated `status` and `search`.
- **`GET /api/v1/orders/{order_id}`** *(Own `SALESMAN` or Admin/Owner/Auditor)*: Returns live status, remarks, revised quantities, and status timeline (`reservations` and `audit_trail` stripped `[]` for `SALESMAN`).
- **`PUT /api/v1/orders/{order_id}`** *(Owning `SALESMAN` only, `status == 'CORRECTION_REQUESTED'`)*
  - **Request:** `{"notes", "items": [{"pack_size_id", "ordered_qty_pkts"}]}` — ignores client price, recalculates authoritative server pricing, and resubmits (`SUBMITTED`).
- **`POST /api/v1/orders/{order_id}/cancel`** *(Owning `SALESMAN` only, `status in {'SUBMITTED', 'CORRECTION_REQUESTED'}`)*
  - **Request:** `{"reason": "...(min 5 chars)"}` -> `CANCELLED`.
