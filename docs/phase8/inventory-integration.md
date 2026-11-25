# Phase 8 — Single-Ledger Inventory Integration & Cost Lot Depletion

## Single-Ledger Architecture Preserved

Phase 8 creates **zero separate inventory tables**. Finished-goods deductions on Dispatch and sellable returns on Credit Notes write directly to the existing Phase 6/7 `inventory.inventory_movements` ledger (`0005` adds nullable foreign keys `dispatch_item_id` and `credit_note_item_id`, plus `fulfilled_qty_pkts` on `inventory.stock_reservations`).

---

## End-to-End Stock Lifecycle Through Phase 8

| Stage | Physical (`on_hand`) | Reserved (`reserved`) | Available (`available = on_hand - reserved`) | Ledger / CostLot Mutation |
| --- | --- | --- | --- | --- |
| Order `APPROVED` (Phase 5) | Unchanged | `+order_qty` | `-order_qty` | `StockReservation(ACTIVE)` created |
| Invoice `DRAFT` / `ISSUED` (Phase 8) | Unchanged | Unchanged | Unchanged | None (tax document only) |
| Dispatch `CREATED` / `READY_FOR_DISPATCH` | Unchanged | Unchanged | Unchanged | None (`DSP/YYYY-YY/NNNN` allocated) |
| Dispatch `DISPATCHED` (`_perform_post_dispatch`) | `-dispatched_qty` | `-release_amt` | Unchanged (stays protected for remainder) | `DISPATCH_OUT` movement + FEFO `CostLot` & `CostLotConsumption` rows |
| Pre-dispatch Full Cancellation Credit Note | Unchanged | `-remaining_res` (`RELEASED`) | `+remaining_res` | Order moves `INVOICED -> CANCELLED` |
| Post-dispatch `SALES_RETURN` (`RESTOCK_SELLABLE`) | `+returned_qty` | Unchanged | `+returned_qty` | `CREDIT_RETURN_IN` movement + new `CostLot(CREDIT_NOTE)` |
| Post-dispatch `SALES_RETURN` (`SCRAP_DAMAGED`) | Unchanged | Unchanged | Unchanged | Financial reversal only; damaged stock excluded from FG |

---

## Atomicity & Zero-Drift Guarantees

- Before writing any movement, `_perform_post_dispatch` locks `InventoryBalance` and `StockReservation` rows `FOR UPDATE` and validates `on_hand_qty_base >= dispatched_qty_pkts`; shortfall aborts with `409 INSUFFICIENT_STOCK` and full rollback.
- Database trigger `fn_sync_balance_from_movement()` remains the sole mutator of `InventoryBalance.on_hand_qty_base`.
- Inventory ledger API (`inventory/service.py`) enriches `DISPATCH` and `CREDIT_NOTE` rows with `source_reference_id` so UI links navigate directly from ledger rows to `/admin/dispatch/:id` or `/admin/billing/invoices/:id`.
