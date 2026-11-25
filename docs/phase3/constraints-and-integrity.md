# Database Integrity, Concurrency & Transaction Controls

---

## 1. Foreign Key Deletion Restrictions

| Policy | Applied Tables | Business Justification |
| --- | --- | --- |
| **`ON DELETE RESTRICT`** | **All 51 operational, master, ledger, billing, payment, and audit tables** | Prevents destructive cascading wipes. A `Customer` with orders, a `Product` with invoices, a `BomVersion` with production runs, an `Invoice` with payments, or any source doc referenced by `InventoryMovement` **cannot be deleted**. |
| **Soft Deactivation (`is_active = FALSE`)** | Masters (`users`, `customers`, `suppliers`, `products`, `pack_sizes`, `materials`) | Retires obsolete items safely while keeping historical invoices, BOMs, and stock ledgers 100% intact. |
| **Append-Only Trigger (`BEFORE UPDATE OR DELETE`)** | `inventory.inventory_movements`, `audit.audit_logs`, `sales.sales_order_status_history` | Unconditionally executes `RAISE EXCEPTION` on SQL `UPDATE` or `DELETE`, blocking accidental mutations even from admin SQL scripts. |
| **Posted Document Immutability Trigger** | `billing.invoices`, `billing.invoice_items`, `billing.credit_notes`, `production.bom_versions` (when `status <> 'DRAFT'`) | Blocks `DELETE` and blocks updates to financial/recipe columns (`grand_total_paisa`, `invoice_number`, `expected_yield_pkts`); only `payment_status`, `dispatch_status`, and `doc_status -> CANCELLED_BY_CN` can change via controlled workflows. |

---

## 2. Critical `CHECK` & `UNIQUE` Constraints Summary

1. **Idempotency Constraints:**
   - `sales.sales_orders`: `UNIQUE (salesman_id, client_order_id)`
   - `finance.payments`: `UNIQUE (idempotency_key)`
2. **Stock & Reservation Integrity:**
   - `inventory.inventory_balances`: `CHECK (on_hand_qty_base >= 0)`, `CHECK (reserved_qty_base >= 0)`, `CHECK (reserved_qty_base <= on_hand_qty_base)`
   - `inventory.cost_lots`: `CHECK (remaining_qty_base >= 0 AND remaining_qty_base <= original_qty_base)`
3. **Source Traceability Enforcement:**
   - `inventory.inventory_movements`: `CHECK (num_nonnulls(opening_balance_id, purchase_receipt_item_id, production_run_id, dispatch_item_id, credit_note_item_id, stock_adjustment_id) = 1)`
4. **GST & Financial Correctness:**
   - `billing.invoices`: `CHECK ((supply_type='INTRA_STATE' AND igst_total_paisa=0 AND cgst_total_paisa=sgst_total_paisa) OR (supply_type='INTER_STATE' AND cgst_total_paisa=0 AND sgst_total_paisa=0))`
   - `finance.customer_receivables`: `CHECK (credited_paisa + paid_paisa <= original_paisa)`
   - `billing.fiscal_sequences`: `UNIQUE (doc_type, financial_year)`
5. **Dispatch Over-Fulfillment Guard (`BEFORE INSERT` Trigger on `billing.dispatch_items`):**
   - Sums existing `dispatch_items.dispatched_qty_pkts` + `NEW.dispatched_qty_pkts` for `invoice_item_id` and raises an exception if total exceeds `invoice_items.qty_pkts`.

---

## 3. Isolation Levels & Concurrency Controls

### 3.1 Chosen Strategy: `READ COMMITTED` + Deterministic Pessimistic Locking (`SELECT ... FOR UPDATE`)
- **Why not rely solely on `READ COMMITTED` without locks?** Two transactions reading `available_qty = 88` simultaneously would both pass application validation before either commits (`lost reservation`).
- **Why pessimistic `SELECT ... FOR UPDATE` beats `SERIALIZABLE` retry storms here:** Under `SERIALIZABLE`, concurrent transactions cause unpredictable `40001 serialization_failure` aborts requiring full client retry loops across multi-step workflows. Explicit pessimistic row locks on exact target rows (`inventory_balances`, `cost_lots`, `fiscal_sequences`, `customer_receivables`) provide **zero-retry deterministic serialization** per SKU or sequence while keeping unrelated SKUs/customers completely unblocked!

### 3.2 Deadlock Prevention Rule
Whenever a transaction locks multiple `inventory.inventory_balances` rows (e.g., an order with 3 SKUs or a production run issuing Flour + Oil + Spice):
```sql
SELECT id, on_hand_qty_base, reserved_qty_base, available_qty_base
FROM inventory.inventory_balances
WHERE id IN (...)
ORDER BY id ASC
FOR UPDATE;
```
Deterministic ascending `id` lock ordering guarantees circular waits (`A waits for B` while `B waits for A`) are **mathematically impossible**.

---

## 4. Concurrency Walkthrough: How Two Salesmen Cannot Oversell Limited Stock

**Scenario (`EC-03`):** `Murukku 200 g` has `on_hand_qty_base = 100`, `reserved_qty_base = 0` (`available_qty_base = 100`).
- **T1 (10:00:01):** `Salesman A` submits `ORD-101` (`80 pkts`, `client_order_id = UUID-A`). Allowed! Both mobile submissions succeed (`SUBMITTED`).
- **T2 (10:00:02):** `Salesman B` submits `ORD-102` (`70 pkts`, `client_order_id = UUID-B`). Allowed! (`150` total demand queued).
- **T3 (10:01:00 — Simultaneous Admin Approvals in 2 browser tabs):**
  - **Admin Tab 1 (`ORD-101`, `80` pkts)** enters `TX-02` and executes `SELECT ... FROM inventory.inventory_balances WHERE pack_size_id = 1 FOR UPDATE`. Acquires exclusive row lock (`available = 100 >= 80`). Updates `reserved_qty_base = 80` (`available_qty_base` computed column becomes `20`). Commits!
  - **Admin Tab 2 (`ORD-102`, `70` pkts)** executed `SELECT ... FOR UPDATE` 5ms later — PostgreSQL **blocks Tab 2** until Tab 1 commits, then returns the fresh committed row (`available_qty_base = 20`)!
  - Tab 2 checks `20 >= 70` -> **FAILS**! Even if application logic had a bug and ran `UPDATE inventory_balances SET reserved_qty_base = reserved_qty_base + 70`, PostgreSQL's `CHECK (reserved_qty_base <= on_hand_qty_base)` (`150 <= 100` FALSE!) **aborts Tab 2 at the storage engine!**
  - Tab 2 rolls back cleanly, sets `ORD-102.has_shortage = TRUE` (`Shortage: 50 pkts`), and logs `HELD_SHORTAGE` in `sales_order_approvals`.
