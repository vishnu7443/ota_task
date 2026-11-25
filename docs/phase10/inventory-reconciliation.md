# Inventory & Purchasing Reconciliation

## 1. Mathematical Verification Formula

 Implemented in `backend/app/modules/reconciliation/engine.py` (`evaluate_inventory_reconciliation`), every active Raw Material, Packaging Material (`MATERIAL`), and Finished Goods SKU (`PACK_SIZE`) is deterministically verified in canonical base UOM (`g`, `ml`, `piece`, `packet`) using `Decimal` arithmetic (`QTY_TOLERANCE = 0.0005`):

$$\text{Expected Closing} = \text{Opening} + \text{Total Inward} - \text{Total Outward}$$

Where:
- **Opening:** Sum of `OPENING` movements plus any movements with `occurred_at < period_start (00:00 IST)`.
- **Total Inward:** `PURCHASE_IN` + `PROD_OUTPUT_IN` + (`PROD_RETURN_IN` + `CREDIT_RETURN_IN`) + positive `ADJUSTMENT`.
- **Total Outward:** `PROD_ISSUE_OUT` + `DISPATCH_OUT` + (`PACKAGING_DAMAGE_OUT` + `DAMAGE_WASTAGE`) + `SUPPLIER_RETURN` + negative `ADJUSTMENT` magnitude.
- Movements strictly deduplicated by immutable `inventory_movements.id`.

---

## 2. Three-Way Parity Checks Executed

For every item (`MATERIAL` and `PACK_SIZE`) up to `cutoff_at`:
1. **Ledger-vs-Persisted Balance (`INV_BAL_MISMATCH`, Severity `HIGH`):**
   - Compares recomputed `expected_closing_qty_base` against `inventory.inventory_balances.on_hand_qty_base`.
   - When evaluating an older historical cutoff and later movements exist after `cutoff_at`, live `inventory_balances` comparison suppresses false lag mismatches while preserving exact historical period closing calculation.
2. **Balance-vs-Open FIFO CostLot Parity (`COST_LOT_MISMATCH`, Severity `MEDIUM`):**
   - Compares `inventory.inventory_balances.on_hand_qty_base` against $\sum \text{CostLot.remaining\_qty\_base}$ (across open layers where `remaining_qty_base > 0`).
3. **Posted Goods Receipt vs Ledger Parity (`PR_ACC_VS_LEDGER_MISMATCH`, Domain `PURCHASING`, Severity `HIGH`):**
   - Cross-checks every posted `purchasing.purchase_receipt_items.accepted_qty_base` in the selected period against `PURCHASE_IN` movements referencing `purchase_receipt_item_id`.

---

## 3. CSV Diagnostic Export & Reporting

- `GET /api/v1/reconciliation/reports/inventory` returns structured summary counters (`total_items`, `matched_count`, `mismatch_count`) and per-SKU breakdowns (`opening_qty_base`, `inward_*`, `outward_*`, `expected_closing_qty_base`, `persisted_closing_qty_base`, `difference_qty_base`, `cost_lot_remaining_qty_base`).
- `GET /api/v1/reconciliation/reports/inventory/export/csv` streams full tabular breakdown with `only_mismatches` and `item_category` filters for warehouse and external audit inspection.
