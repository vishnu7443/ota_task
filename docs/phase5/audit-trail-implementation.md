# Audit Trail & Immutability Implementation

Implemented across [audit/service.py](file:///d:/mac/ota/backend/app/modules/audit/service.py), [audit/models.py](file:///d:/mac/ota/backend/app/modules/audit/models.py), and [orders/service.py](file:///d:/mac/ota/backend/app/modules/orders/service.py).

---

## 1. Audited Order & Inventory Reservation Events (`PART 9`)

Every mutation commits its `audit.audit_logs` entry inside the **exact same database transaction** as the domain change:

| Action Code | Trigger Event | Entity Recorded | Captured State (`before_state` / `after_state` / `reason`) |
| --- | --- | --- | --- |
| `ORDER_SUBMITTED` | Salesman creates order | `sales.sales_orders` | Customer ID, order number, total packets, initial shortage flag |
| `ORDER_QTY_MODIFIED` | Admin changes line qty | `sales.sales_orders` | Item IDs, SKU codes, `ordered_qty_pkts`, before & after qtys, shortage flag, mandatory reason |
| `ORDER_PRICE_MODIFIED` | Admin overrides unit price | `sales.sales_orders` | Item IDs, SKU codes, `original_unit_price_paisa`, before & after unit price, mandatory reason |
| `ORDER_REMARK_UPDATED` | Admin saves remarks | `sales.sales_orders` | Previous vs new `admin_remarks`, reason |
| `ORDER_MARKED_UNDER_REVIEW` | Admin marks Under Review / logs check | `sales.sales_orders` | Previous & target status, shortage packets, remarks |
| `ORDER_CORRECTION_REQ` | Admin returns order for correction | `sales.sales_orders` | Previous status, `CORRECTION_REQUESTED`, mandatory reason |
| `ORDER_RESUBMITTED` | Salesman edits & resubmits | `sales.sales_orders` | Full before/after line snapshots and new shortage flag |
| `ORDER_APPROVED` | Admin approves verified order | `sales.sales_orders` | Previous status, `APPROVED`, approved packet count, remarks |
| `STOCK_RESERVED` | Atomic reservation created on approval | `inventory.inventory_balances` | `sales_order_id`, order number, per-SKU `reservation_id` & `reserved_qty_pkts` |
| `ORDER_REJECTED` | Admin rejects order | `sales.sales_orders` | Previous status, `REJECTED`, mandatory `rejection_reason` |
| `ORDER_CANCELLED` | Admin or Salesman cancels pre-invoice | `sales.sales_orders` | Previous status, `CANCELLED`, count of released reservations, reason |
| `STOCK_RESERVATION_RELEASED` | Pre-invoice cancel of `APPROVED` order | `inventory.inventory_balances` | `sales_order_id`, `reservation_id`, `released_qty_pkts`, resulting `reserved_qty_base`, reason |
| `ACCESS_DENIED` | RBAC permission violation | `iam.users` | Required roles, actor role, denied reason |

---

## 2. Tamper-Proof Enforcement & Visibility

- **PostgreSQL Trigger Protection:** `trg_audit_logs_append_only` (`BEFORE UPDATE OR DELETE ... FOR EACH ROW EXECUTE FUNCTION audit.fn_prevent_mutation()`) raises `SQLSTATE 42501` if any `UPDATE` or `DELETE` touches `audit.audit_logs` or `sales.sales_order_status_history`.
- **Role-Controlled Audit Query:** `list_order_audit_logs(db, order_id)` merges order-table logs and stock-reservation balance logs chronologically and is exposed **exclusively** to `FACTORY_ADMIN`, `OWNER`, and `ACCOUNTANT_AUDITOR` (stripped to `[]` for `SALESMAN`).
