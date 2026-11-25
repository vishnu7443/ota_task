# Known Limitations & Phase Boundaries (`docs/phase6/known-limitations.md`)

## Explicit Scope Boundaries (Preserved by Design)
Per Phase 6 boundaries, the following modules remain **intentionally deferred** to Phase 7+ and are NOT fabricated or mocked:
1. **Production Execution & BOM Consumption:** `PROD_ISSUE_OUT`, `PACKAGING_DAMAGE_OUT`, `PROD_OUTPUT_IN`, and `PROD_RETURN_IN` movement types exist in the PostgreSQL ledger constraints (`chk_inventory_movements_mov_type_enum`) and trigger, but production run execution routes/UI will be implemented in the Production phase.
2. **GST Tax Invoicing, Dispatch & Payments / AR:** Finished goods reservations (`reserved_qty_base`) decrease `available_qty_base` upon Sales Order approval (Phase 5), while physical finished-goods deduction (`DISPATCH_OUT`) and AR invoicing remain deferred to Phase 7/8.
3. **Standalone Non-PO Material Master Creation UI:** The 5 benchmark Raw Materials & Packaging Materials (`MAT-FLR`, `MAT-OIL`, `MAT-SPC`, `MAT-PCH-200`, `MAT-CTN-20`) and 6 canonical `unit_conversions` rows are seeded idempotently; UI CRUD for creating arbitrary new materials and custom BOM definitions belongs to the BOM & Production Setup milestone.
4. **Supplier AP / Payment Settlement:** Goods Receipts track `subtotal_paisa`, `input_gst_paisa`, and `total_paisa` accurately for audit & purchase history, whereas supplier accounts payable settlement is deferred cleanly to the financial ledger phase.
5. **FIFO Lot Depletion Reporting UI:** Cost lots (`inventory.cost_lots`) are populated and FIFO-depleted cleanly at the DB layer for purchases and adjustments; batch-wise COGS variance reports will expose lot-level consumption once production batches execute.
