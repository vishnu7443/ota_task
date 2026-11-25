# Phase 6 API Documentation (`docs/phase6/api-documentation.md`)

All endpoints sit under `/api/v1` and require JWT Bearer authentication (`Authorization: Bearer <token>`). Errors follow `{ "error": { "code", "message", "details" } }`.

## Purchasing Endpoints (`/api/v1/purchasing`)

| Method | Path | Allowed Roles | Description |
|---|---|---|---|
| `GET` | `/suppliers` | Admin, Supervisor, Auditor, Owner | List suppliers (`active_only`, `search`) with PO/receipt aggregates. |
| `GET` | `/suppliers/{supplier_id}` | Admin, Supervisor, Auditor, Owner | Supplier profile plus nested `purchase_orders` & `purchase_receipts`. |
| `POST` | `/suppliers` | Factory Admin | Create supplier (validates GSTIN & 2-digit state prefix). |
| `PUT` | `/suppliers/{supplier_id}` | Factory Admin | Update supplier contact/GSTIN/address/active status. |
| `GET` | `/orders` | Admin, Supervisor, Auditor, Owner | List POs (`supplier_id`, `status`, `search`). |
| `GET` | `/orders/{po_id}` | Admin, Supervisor, Auditor, Owner | Full PO lines (ordered, accepted, rejected, remaining) + linked receipts. |
| `POST` | `/orders` | Admin, Supervisor | Create PO (`submit_immediately` optional); converts qty to base units cleanly. |
| `POST` | `/orders/{po_id}/submit` | Admin, Supervisor | Transition `DRAFT -> SUBMITTED`. |
| `POST` | `/orders/{po_id}/approve` | Factory Admin | Transition `SUBMITTED -> APPROVED`. Never touches stock. |
| `POST` | `/orders/{po_id}/reject` | Factory Admin | Transition `SUBMITTED -> REJECTED` (mandatory `reason`). |
| `POST` | `/orders/{po_id}/cancel` | Factory Admin | Cancel PO cleanly when zero accepted receipts exist. |
| `GET` | `/receipts` | Admin, Supervisor, Auditor, Owner | List Goods Receipts (`supplier_id`, `purchase_order_id`, `status`, `date_from`, `date_to`, `search`). |
| `GET` | `/receipts/{receipt_id}` | Admin, Supervisor, Auditor, Owner | Full GRN details and line breakdown. |
| `POST` | `/receipts` | Admin, Supervisor | Create GRN idempotently via `client_receipt_id` (`201 Created`, or `200 OK` replay). |
| `POST` | `/receipts/{receipt_id}/submit` | Admin, Supervisor | Transition `DRAFT -> SUBMITTED`. |
| `POST` | `/receipts/{receipt_id}/verify` | Admin, Supervisor | Transition `SUBMITTED -> VERIFIED`. |
| `POST` | `/receipts/{receipt_id}/post` | Admin, Supervisor | Transition `VERIFIED -> POSTED`, writing `PURCHASE_IN` movements & `CostLot` layers. |

## Inventory & Ledger Endpoints (`/api/v1/inventory`)

| Method | Path | Allowed Roles | Description |
|---|---|---|---|
| `GET` | `/materials` | Admin, Supervisor, Auditor, Owner | List active Raw Materials & Packaging Materials (`category`, `search`). |
| `GET` | `/overview` | Admin, Supervisor, Auditor, Owner | Dashboard KPIs + item balances (`Opening`, `Received`, `Issued`, `Dispatched`, `Adjusted`, `Physical`, `Reserved`, `Available`, `is_low_stock`, `open_lot_value_paisa`). |
| `GET` | `/ledger` | Admin, Supervisor, Auditor, Owner | Append-only movement ledger (`item_category`, `material_id`, `pack_size_id`, `movement_type`, `date_from`, `date_to`, `limit`). |
| `GET` | `/adjustments` | Admin, Supervisor, Auditor, Owner | List stock adjustment requests & approval history (`status`, `item_category`). |
| `POST` | `/adjustments` | Admin, Supervisor | Request adjustment (`PENDING_APPROVAL`; only Admin may pass `post_immediately: true`). |
| `POST` | `/adjustments/{adjustment_id}/approve` | Factory Admin | Atomically approve & post adjustment to ledger (`INSUFFICIENT_STOCK` / `INSUFFICIENT_AVAILABLE_STOCK` guards). |
| `POST` | `/adjustments/{adjustment_id}/reject` | Factory Admin | Reject pending adjustment with mandatory `reason`. |
| `GET` | `/reports/summary` | Admin, Supervisor, Auditor, Owner | Consolidated report (`current_stock`, `low_stock_items`, `purchase_receipts`, `adjustments`). |
