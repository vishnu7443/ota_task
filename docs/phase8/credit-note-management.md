# Phase 8 — Credit Note & Cancellation Management

## Overview

Issued GST Invoices cannot be edited or deleted (`trg_invoice_immutability`). Corrections, order cancellations after invoicing, and post-dispatch returns must flow exclusively through **Credit Notes** (`billing.credit_notes`, `billing.credit_note_items`).

---

## Supported Credit Note Types

1. **`INVOICE_CANCELLATION`:**
   - Reverses full remaining taxable value, tax components, and invoice round-off (`cancel_original_invoice = True`).
   - Transitions Invoice `doc_status` -> `'CANCELLED_BY_CN'` and `payment_status` -> `'CREDITED'`.
   - If the linked `SalesOrder` is still un-dispatched (`status == 'INVOICED'`), releases active FG `StockReservation` rows back to `available_qty_base` and transitions the Sales Order to `'CANCELLED'` with history & audit logging.
2. **`SALES_RETURN`:**
   - Supports per-line quantities up to invoiced quantity, explicitly validating that physical returns (`RESTOCK_SELLABLE` / `SCRAP_DAMAGED`) do not exceed physically dispatched quantity (`409 RETURN_EXCEEDS_DISPATCHED`).
   - **`RESTOCK_SELLABLE`:** Writes `CREDIT_RETURN_IN` into `inventory.inventory_movements` (`credit_note_item_id`) and adds an open `FINISHED_GOOD` `CostLot` layer (increasing `on_hand_qty_base` and `available_qty_base`).
   - **`SCRAP_DAMAGED`:** Financial & GST reversal is recorded on the Credit Note without adding spoiled/damaged packets back into sellable FG inventory.
   - **`NONE_NOT_DISPATCHED`:** Financial reversal only when goods never left the plant.
3. **`VALUE_ADJUSTMENT`:**
   - Supports tax/value reversal (`taxable_override_paisa`) preserving the exact original invoice supply split (`CGST+SGST` or `IGST`).

---

## Guards & Immutability

- Allocations (`CN/YYYY-YY/NNNN`) occur strictly upon Issuance (`DRAFT -> ISSUED`).
- Cumulative reversals cannot exceed invoice `grand_total_paisa - credited_paisa` (`409 EXCESS_CREDIT_NOTE`).
- PostgreSQL trigger `trg_credit_note_immutability` blocks any `UPDATE` or `DELETE` once `status <> 'DRAFT'`.
- Duplicate cancellation attempts on an already-cancelled invoice fail with `409 INVALID_STATE_TRANSITION`.
