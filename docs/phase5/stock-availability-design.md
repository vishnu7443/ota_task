# Stock Availability & Atomic Reservation Design

---

## 1. Schema Assessment & Additive Change (`0002_phase5_order_lifecycle`)

### Assessment of Phase 4 Schema
Migration `0001_phase4_foundation` already defined `inventory.inventory_balances` with:
- `on_hand_qty_base NUMERIC(18,3)` (physical stock derived strictly via `AFTER INSERT` trigger on `inventory.inventory_movements`)
- `reserved_qty_base NUMERIC(18,3)` (committed stock awaiting dispatch)
- `available_qty_base NUMERIC(18,3) GENERATED ALWAYS AS (on_hand_qty_base - reserved_qty_base) STORED`
- `CHECK (reserved_qty_base <= on_hand_qty_base)` (`chk_inventory_balances_bal_reserved_cap`)

### Additive Table Introduced (`inventory.stock_reservations`)
While `inventory_balances.reserved_qty_base` enforced SKU-level aggregate reservation caps, Phase 5 requires per-order reservation traceability (`PART 9` + pre-invoice cancellation release + double-reservation protection). Migration `0002_phase5_order_lifecycle` adds **`inventory.stock_reservations`**:
- Columns: `id`, `sales_order_id`, `sales_order_item_id`, `pack_size_id`, `reserved_qty_pkts`, `status ('ACTIVE','RELEASED','FULFILLED')`, `reserved_by`, `reserved_at`, `released_by`, `released_at`, `release_reason`.
- Partial unique index `uq_stock_res_active_item ON (sales_order_item_id) WHERE status = 'ACTIVE'` makes duplicate active reservations for any order item impossible at the database level.

---

## 2. Stock Policy Consistency

Consistent with approved Phase 1–3 architecture (`ADR-03`, `BR-AVL-01`, `BR-AVL-02`, `TX-02`):
- **Order Submission:** Non-blocking read-only check (`has_shortage` flagged, `reserved_qty_base` unchanged).
- **Order Approval (`POST /approve`):** Soft-reserves finished goods (`reserved_qty_base += effective_qty_pkts` and creates `ACTIVE` `stock_reservations`), reducing `available_qty_base` immediately so competing orders cannot double-allocate the same packets, while keeping physical `on_hand_qty_base` untouched until Dispatch (Phase 6).
- **Pre-Invoice Cancellation (`POST /cancel` on `APPROVED`):** Atomically marks `stock_reservations.status = 'RELEASED'` and decrements `reserved_qty_base`.

---

## 3. Concurrency Safety & Insufficient Stock Behavior

1. **Deterministic Pessimistic Locking:** `lock_balances_by_pack_size_ids()` in [inventory/repository.py](file:///d:/mac/ota/backend/app/modules/inventory/repository.py) sorts `pack_size_id` values and executes `SELECT ... FROM inventory.inventory_balances ... ORDER BY id ASC FOR UPDATE`, eliminating deadlocks across multi-SKU approvals.
2. **Serialized Competing Approvals:** If `Murukku 200 g` has `on_hand = 100` (`reserved = 0`, `available = 100`) and two Admin sessions simultaneously approve `Order 1 (80 pkts)` and `Order 2 (70 pkts)`, PostgreSQL serializes execution on the `FOR UPDATE` row lock: `Order 1` commits (`reserved = 80`, `available = 20`), and `Order 2` sees `available = 20 < 70` and rolls back cleanly with `409 INSUFFICIENT_STOCK`.
3. **Insufficient Stock Guard:** When `available_pkts < requested_qty_pkts`:
   - Physical `on_hand` is never driven negative (`chk_inventory_balances_bal_on_hand_non_negative`).
   - `reserved_qty_base` is never allowed to exceed `on_hand` (`chk_inventory_balances_bal_reserved_cap`).
   - API returns `409 INSUFFICIENT_STOCK` listing per-SKU `requested_qty_pkts`, `on_hand_qty_pkts`, `reserved_qty_pkts`, `available_qty_pkts`, `shortage_pkts`, and policy explanation; Admin UI surfaces `"Match Max Available Qty"`, `"Mark Under Review"`, `"Request Correction"`, and `"Reject Order"`.
