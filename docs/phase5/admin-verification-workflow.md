# Admin Verification Workflow

Implemented across [AdminDashboardPage.tsx](file:///d:/mac/ota/frontend/src/pages/admin/AdminDashboardPage.tsx), [AdminIncomingOrdersPage.tsx](file:///d:/mac/ota/frontend/src/pages/admin/AdminIncomingOrdersPage.tsx), [AdminOrderDetailPage.tsx](file:///d:/mac/ota/frontend/src/pages/admin/AdminOrderDetailPage.tsx), and [orders/router.py](file:///d:/mac/ota/backend/app/modules/orders/router.py).

---

## 1. Queue Organization & Filtering (`GET /api/v1/admin/orders`)

- **Queue Summary KPIs (`GET /api/v1/admin/orders/summary`):** Server-computed counts across all persisted orders (`pending_verification_count`, `submitted_count`, `under_review_count`, `correction_requested_count`, `shortage_count`, `approved_count`, `rejected_count`, plus pending and approved INR values).
- **Lifecycle Tabs:** `Pending Verification`, `Incoming`, `Approved`, `Rejected`, and `All Orders`.
- **Filters & Pagination:**
  - Search by order number (`ORD-...`), customer name/code, or salesman name
  - Filter by Customer (`customer_id`) sourced dynamically from `GET /api/v1/sales/customers`
  - Filter by Salesman (`salesman_id`) sourced dynamically from `GET /api/v1/sales/salesmen`
  - Date range (`date_from` and `date_to` against `order_date`)
  - Status (`status` / `pending_verification=true`) & Stock Coverage (`has_shortage`)
  - Paginated (`page`, `page_size`) with 10-second live polling

---

## 2. Detailed Order Review Capabilities (`FACTORY_ADMIN`)

When opening `/admin/orders/:orderId`, Factory Admin sees:
- **Customer & Tax Jurisdiction:** Customer code, type (`RETAILER` / `DISTRIBUTOR`), GSTIN, Place of Supply state code, and tax mode (`CGST+SGST` vs `IGST`).
- **Salesman Info:** Salesman name, employee code, territory, and mobile delivery notes.
- **Line Items & Price Override Editor (`PATCH /api/v1/admin/orders/{id}`):**
  - Displays `ordered_qty_pkts` alongside editable `approved_qty_pkts`.
  - Displays immutable `original_unit_price_paisa` alongside editable `unit_price_paisa`.
  - Any modification of quantity or price enforces a mandatory reason (`>= 5` characters), auto-transitions `SUBMITTED -> UNDER_REVIEW` on first edit, recalculates line taxable (`GENERATED ALWAYS AS`) & GST estimates server-side, and logs `ORDER_QTY_MODIFIED` / `ORDER_PRICE_MODIFIED` to `audit.audit_logs`.
- **Decision Controls:**
  - **Mark Under Review / Log Stock Check (`POST /review`):** Places `SUBMITTED -> UNDER_REVIEW` and captures a fresh `sales_order_approvals` stock snapshot.
  - **Request Correction (`POST /request-correction`):** Moves order to `CORRECTION_REQUESTED` with mandatory remarks visible on the salesman's phone.
  - **Approve & Reserve Stock (`POST /approve`):** Verifies `available >= effective_qty` under `FOR UPDATE` locks, reserves stock atomically, and transitions to `APPROVED`.
  - **Reject Order (`POST /reject`):** Permanently transitions to `REJECTED` with mandatory `rejection_reason`.
  - **Cancel Approved / Pre-Invoice Order (`POST /cancel`):** Transitions to `CANCELLED` with mandatory reason and atomically releases any active reservations.

**Role Segregation Safeguard:** `OWNER` and `ACCOUNTANT_AUDITOR` see full order details, stock snapshots, reservations, and audit logs in strictly read-only mode; any mutation API call by non-`FACTORY_ADMIN` roles fails server-side with `403 Forbidden` and logs `ACCESS_DENIED`.
