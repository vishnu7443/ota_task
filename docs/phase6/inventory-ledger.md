# Immutable Inventory Ledger (`docs/phase6/inventory-ledger.md`)

## Single Source of Truth Architecture
`inventory.inventory_movements` is the append-only ledger recording every physical stock delta across Raw Materials, Packaging Materials, and Finished Goods.

## Database Enforcement
- **Append-Only Trigger:** `trg_inventory_movements_append_only` executes `audit.fn_prevent_mutation()` `BEFORE UPDATE OR DELETE`, rejecting any attempt to alter or delete historical ledger entries at the PostgreSQL layer.
- **Movement Taxonomy (`mov_type_enum`) & Sign Direction (`mov_sign_direction`):**
  - **Inbound (`signed_qty_base > 0`):** `OPENING`, `PURCHASE_IN`, `PROD_OUTPUT_IN`, `PROD_RETURN_IN`, `CREDIT_RETURN_IN`.
  - **Outbound (`signed_qty_base < 0`):** `PROD_ISSUE_OUT`, `PACKAGING_DAMAGE_OUT`, `DISPATCH_OUT`, `SUPPLIER_RETURN`, `DAMAGE_WASTAGE`.
  - **Bidirectional Non-Zero (`signed_qty_base <> 0`):** `ADJUSTMENT`.
- **Mandatory Source Traceability (`mov_source_required`):**
  - `OPENING_BALANCE` requires `opening_balance_id`.
  - `PURCHASE_RECEIPT` requires `purchase_receipt_item_id`.
  - `STOCK_ADJUSTMENT` / `SUPPLIER_RETURN` requires `stock_adjustment_id`.
- **Single-Item XOR (`mov_one_item`):**
  - Raw / Packaging movements set `material_id IS NOT NULL AND pack_size_id IS NULL`.
  - Finished Good movements set `pack_size_id IS NOT NULL AND material_id IS NULL`.

## Atomic Balance Projection Trigger (`fn_sync_balance_from_movement`)
Whenever a row is inserted into `inventory.inventory_movements`, `trg_sync_inventory_balance` executes `AFTER INSERT`:
1. Ensures the balance row exists using `INSERT INTO inventory.inventory_balances (..., 0, 0) ON CONFLICT ... DO NOTHING`.
2. Atomically applies `UPDATE ... SET on_hand_qty_base = on_hand_qty_base + NEW.signed_qty_base`.

Performing the zero-row `ON CONFLICT DO NOTHING` insert before the delta `UPDATE` ensures PostgreSQL evaluates `CHECK (on_hand_qty_base >= 0)` and `CHECK (reserved_qty_base <= on_hand_qty_base)` on the real post-delta stock balance rather than falsely failing on negative candidate `VALUES` tuples.
