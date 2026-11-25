# Phase 8 — Partial Dispatch Rules & Multi-Trip Accounting

## Supported Behavior

A single ISSUED GST Tax Invoice supports splitting physical fulfillment across multiple sequential `Dispatch` documents (`DSP/YYYY-YY/NNNN`) while maintaining exact remaining quantities, accurate stock reservations, and strict anti-over-dispatch guarantees.

---

## Mechanics

1. **Cumulative Allocation Tracking (`sum_dispatched_qty_by_invoice_item_ids`):**
   - Aggregates all committed `DispatchItem.dispatched_qty_pkts` across existing dispatches for each `invoice_item_id`.
   - Remaining dispatchable quantity on any item = `invoice_item.qty_pkts - committed_qty`.
2. **Proportional Reservation Fulfillment (`post_dispatch`):**
   - When Dispatch #1 posts `100` out of `150` invoiced packets (with `238` physical on hand and `150` reserved):
     - `DISPATCH_OUT` reduces physical stock: `238 - 100 = 138` packets.
     - `StockReservation.fulfilled_qty_pkts` increments `0 -> 100` (status remains `ACTIVE`), releasing `100` packets from `InventoryBalance.reserved_qty_base` (`150 -> 50`).
     - Net free `available_qty_base` remains `138 - 50 = 88` packets—protecting the remaining `50` packets for Dispatch #2!
   - When Dispatch #2 posts the remaining `50` packets:
     - `DISPATCH_OUT` reduces physical stock: `138 - 50 = 88` packets.
     - `StockReservation.fulfilled_qty_pkts` reaches `150` (`status = 'FULFILLED'`), `reserved_qty_base` becomes `0`, and `available_qty_base` remains `88` packets.
3. **Invoice & Sales Order Sync:**
   - `posted_qty < total_inv_qty`: Invoice `dispatch_status = 'PARTIAL'`, Sales Order `status = 'PARTIALLY_DISPATCHED'`.
   - `posted_qty >= total_inv_qty`: Invoice `dispatch_status = 'DISPATCHED'`, Sales Order `status = 'DISPATCHED'`.
4. **Over-Dispatch Block:**
   - Attempting `51` packets when only `50` remain returns `409 DISPATCH_EXCEEDS_ORDER` (backed independently by PostgreSQL trigger `trg_guard_over_dispatch`).
