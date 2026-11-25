# Stock Balance Management & Concurrency (`docs/phase6/stock-balance-management.md`)

## Mathematical Balance Identities
For every tracked Material (`production.materials`) and Finished Good (`sales.pack_sizes`), balances follow:

```
Physical Stock  = Opening + Received - Issued - Dispatched + Adjusted
Available Stock = Physical Stock - Reserved Stock
```

Where:
- **Opening:** `OPENING`
- **Received:** `PURCHASE_IN`, `PROD_OUTPUT_IN`, `PROD_RETURN_IN`, `CREDIT_RETURN_IN`
- **Issued:** `PROD_ISSUE_OUT`, `PACKAGING_DAMAGE_OUT` (reserved for Phase 7 production runs)
- **Dispatched:** `DISPATCH_OUT` (reserved for Phase 8 dispatch)
- **Adjusted:** `ADJUSTMENT`, `DAMAGE_WASTAGE`, `SUPPLIER_RETURN`

## PostgreSQL Balance Constraints (`inventory.inventory_balances`)
- `on_hand_qty_base >= 0` (prohibits negative physical stock).
- `reserved_qty_base >= 0`.
- `reserved_qty_base <= on_hand_qty_base` (prohibits reducing physical stock below active sales reservations).
- `available_qty_base` is a stored generated column: `GENERATED ALWAYS AS (on_hand_qty_base - reserved_qty_base) STORED`.

## Concurrency & Sales Integration
- **Deterministic Row Locking:** All inventory-mutating operations acquire locks in ascending primary-key order via `SELECT ... FROM inventory.inventory_balances ... ORDER BY id ASC FOR UPDATE`, eliminating deadlocks and race conditions across parallel HTTP requests.
- **FIFO Open Cost Lots (`inventory.cost_lots`):**
  - Inbound flows (`OPENING_BALANCE`, `PURCHASE_RECEIPT`, positive `STOCK_ADJUSTMENT`) insert immutable cost layers with `unit_cost_paisa_per_base` (`NUMERIC(18,6)`).
  - Outbound stock adjustments deplete open lots strictly in FIFO order (`received_at ASC, id ASC FOR UPDATE`).
- **Low-Stock Reorder Alerts:** Items where `available_qty_base <= reorder_level_base` are flagged automatically on the Inventory Dashboard and Low-Stock Report.
