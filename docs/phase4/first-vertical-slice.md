# First Working Vertical Slice — Sales Order Submission & Admin Visibility

## 1. End-to-End Flow Trace

1. **Mobile Salesman Login (`/login` -> `POST /api/v1/auth/login`):**
   - `Salesman A` logs in; backend verifies Argon2id hash, records `LOGIN_SUCCESS`, mints JWT (`role=SALESMAN`), and routes to `/salesman`.
2. **Customer & Product Retrieval (`/salesman/new-order`):**
   - `GET /api/v1/sales/customers` returns active assigned/shared customers (`Retailer A`, Tamil Nadu `33`, GSTIN `33AAACR9999K1Z2`).
   - `GET /api/v1/sales/products?customer_id=...` returns active SKUs (`Murukku 200 g`, `MRK-200G`, `₹50.00` = `5000` paise, `20 pkts/carton`, read-only `available_stock_pkts = 50`).
3. **Quantity Entry, Cart Review & Idempotent Submission (`POST /api/v1/orders`):**
   - Salesman enters `150 packets` (directly or via `7 cartons + 10 pkts`), reviews `₹7,500.00` taxable + `₹375.00` est. GST (`CGST+SGST` intra-state TN -> TN) = `₹7,875.00`, and submits with client-generated `client_order_id` UUID persisted in `localStorage`.
   - Backend enforces `(salesman_id, client_order_id)` idempotency, ignores client prices, resolves `5000 paise` server-side, checks `50` available vs `150` ordered (`has_shortage = True`, `shortage = 100` recorded in `sales_order_approvals` without mutating `inventory_balances`), creates `SalesOrder (SUBMITTED)`, `SalesOrderItem`, `SalesOrderStatusHistory`, and `AuditLog` in a single atomic transaction.
4. **Desktop Admin Order Visibility (`/admin/orders` -> `GET /api/v1/admin/orders` & `/admin/orders/:id`):**
   - `Factory Admin` logs in; Incoming Orders queue polls PostgreSQL every 10 seconds (`TanStack Query`), displaying `ORD-2026-0001` (`Retailer A`, `Salesman A`, `150 pkts`, `₹7,875.00`, `SUBMITTED`, `Shortage`) with zero manual re-entry.
   - Admin opens Review screen inspecting customer GST/place-of-supply details, line items, live stock coverage (`On-Hand 50`, `Available 50`, `Short 100`), estimated CGST+SGST split (`₹187.50 + ₹187.50`), status timeline, and stock verification snapshot.
