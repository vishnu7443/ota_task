# Phase 8 — Dispatch Management & Lifecycle

## Overview

Physical goods movement and finished-goods inventory deduction happen strictly through Dispatch records (`billing.dispatches`, `billing.dispatch_items`, `billing.dispatch_status_history`), separated cleanly from financial invoicing.

---

## Dispatch State Machine

```text
  [Invoice ISSUED]
         │
         ▼
     (CREATED)             ── Dispatched qty allocated (DSP/YYYY-YY/NNNN); FG not deducted yet
         │
         │  [POST /dispatches/{id}/ready]
         ▼
 (READY_FOR_DISPATCH)      ── Packing verified; transporter/vehicle/LR recorded
         │
         │  [POST /dispatches/{id}/post]  (Or immediately via post_immediately=True)
         ▼
    (DISPATCHED)           ── ATOMIC: FG CostLot FEFO depletion + DISPATCH_OUT ledger +
         │                    Reservation fulfilled + Invoice dispatch_status + Order status sync
         │
         ├──[POST /delivery -> IN_TRANSIT]──► (IN_TRANSIT)
         │                                         │
         ├──[POST /delivery -> DELIVERED]──────────┼──► (DELIVERED)
         │                                         │
         └──[POST /delivery -> DELIVERY_EXCEPTION]─┴──► (DELIVERY_EXCEPTION) ──► Can resolve to DELIVERED / IN_TRANSIT
```

---

## Key Controls & Guards

1. **Issued Invoice Requirement:**
   - Dispatches can only be created for invoices with `doc_status = 'ISSUED'`. Draft or CN-cancelled invoices fail with `409 INVOICE_NOT_ISSUED`.
2. **Pre-Validation & Database Over-Dispatch Trigger (`trg_guard_over_dispatch`):**
   - `create_dispatch` locks the parent `Invoice` (`FOR UPDATE`) and verifies `req.dispatched_qty_pkts <= orig.qty_pkts - already_committed` (`409 DISPATCH_EXCEEDS_ORDER`).
   - PostgreSQL trigger `trg_guard_over_dispatch` independently enforces `SUM(dispatched_qty_pkts) <= invoice_item.qty_pkts` at DB level (`ERRCODE = '23514'`).
3. **Atomic Posting (`_perform_post_dispatch`):**
   - Rejects duplicate post attempts (`status not in {'CREATED', 'READY_FOR_DISPATCH'}` -> `409 DUPLICATE_DISPATCH_POST`).
   - Locks `inventory.inventory_balances` and `inventory.stock_reservations` (`FOR UPDATE`).
   - Pre-validates physical stock `on_hand_qty_base >= dispatched_qty_pkts` **before** writing any ledger/lot changes; insufficient FG rolls back cleanly with `409 INSUFFICIENT_STOCK`.
   - Depletes open FG `CostLot` records in FEFO order (`list_open_fg_lots_fefo_for_update`), populates `batch_code_ref`, creates `DISPATCH_OUT` movement + `CostLotConsumption` records, reduces `reserved_qty_base` & increments `fulfilled_qty_pkts`, and updates Invoice (`PARTIAL` vs `DISPATCHED`) and Sales Order (`PARTIALLY_DISPATCHED` vs `DISPATCHED`).
4. **Append-Only Progression Log:**
   - `billing.dispatch_status_history` is protected by `trg_dispatch_status_history_append_only` (`fn_prevent_mutation()`), preserving every status transition timestamp, user, and reason.
