# Goods Receipt Workflow (`docs/phase6/goods-receipt-workflow.md`)

## Workflow Stages
Goods Receipts (`purchasing.purchase_receipts`) record actual supplier deliveries against Approved/Partially Received POs (or standalone emergency purchases):

```
DRAFT ──submit──► SUBMITTED ──verify──► VERIFIED ──post──► POSTED
```

## Key Operational & Accounting Rules
1. **Usable vs Rejected/Damaged Stock:**
   - Each line item accepts `received_qty_entered` and `rejected_qty_entered` (`0 <= rejected <= received`).
   - When `rejected_qty_entered > 0`, a descriptive `rejection_reason` is mandatory.
   - Accepted quantity (`accepted = received - rejected`) is converted to canonical base units (`accepted_qty_base`).
   - Monetary value (`line_subtotal_paisa`, `line_tax_paisa`, `line_total_paisa`) and FIFO inventory cost (`unit_cost_paisa_per_base` at `NUMERIC(18,6)`) are calculated strictly on **accepted** quantities.
2. **Excess Quantity Guard:**
   - When receiving against a PO line, if `already_accepted_base + new_accepted_base > ordered_qty_base`, the backend raises `409 EXCESS_RECEIPT_QUANTITY` unless the operator explicitly opts in with `allow_excess: true`.
3. **Only Posted Accepted Quantities Enter Inventory:**
   - Receipts in `DRAFT`, `SUBMITTED`, or `VERIFIED` leave physical stock untouched.
   - `POST /api/v1/purchasing/receipts/{id}/post` locks the receipt row `FOR UPDATE` (blocking concurrent duplicate posts with `409 Conflict`), creates `InventoryMovement` (`PURCHASE_IN`, linked via `purchase_receipt_item_id`), creates open FIFO `CostLot` records with optional `batch_code` & `expiry_date`, updates `PurchaseOrderItem.received_qty_base` / `rejected_qty_base`, and transitions the parent PO to `PARTIALLY_RECEIVED` or `RECEIVED`.
4. **Idempotency:**
   - `client_receipt_id` (`UUID`) is unique on `purchasing.purchase_receipts`; retrying creation with the same UUID returns `200 OK` (`is_duplicate_replay: true`) without duplicating receipts or ledger rows.
