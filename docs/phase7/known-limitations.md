# Phase 7 Known Limitations & Phase Boundaries (`docs/phase7/known-limitations.md`)

## Explicit Scope Boundaries (Deferred by Design Beyond Phase 7)
Per Phase 7 scope constraints, the following modules remain **intentionally deferred** to subsequent phases and are not mocked or fabricated:

1. **Step 8 Final Costing & Overhead Allocation:**
   - Phase 7 computes direct FIFO raw-material & packaging cost absorption (`cost_absorbed_paisa` -> FG `CostLot.unit_cost_paisa_per_base`) for accurate stock valuation.
   - Direct Labour (`₹1,200`), Gas/Power (`₹600`), monthly factory overheads, and finished unit COGS allocation belong exclusively to the dedicated Costing module/schema (`costing`).
2. **GST Tax Invoicing, Finished Goods Dispatch (`DISPATCH_OUT`), and Payments / Receivables:**
   - Approved Sales Orders (`Phase 5`) reserve `FINISHED_GOOD` packets via `reserved_qty_base`, and posted Production Runs increase `MRK-200G` physical stock via `PROD_OUTPUT_IN` (`50 -> 238 pkts`).
   - Generating sequential GST invoices, dispatching FIFO finished goods (`DISPATCH_OUT`), and settling customer receivables remain deferred to the Dispatch, Invoicing & Payments phase.
3. **Standalone Multi-Stage Sub-Assembly Routing / Work-in-Progress Transfers:**
   - Snack batches follow single-run cooking + packing lifecycle (`DRAFT -> PLANNED -> IN_PROGRESS -> COMPLETED -> POSTED`) with split `RAW_ISSUE` / `PACKAGING_PACK` tracking rather than multi-factory semi-finished WIP transfers.
4. **Master Product Deletion / Material Archive UI:**
   - Pack sizes and materials support creation and active/inactive catalog seeding (`POST /catalog/pack-sizes`, `POST /catalog/materials`); soft archival/deactivation UI controls can be layered additively when catalog maintenance expands.
