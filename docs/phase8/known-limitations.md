# Phase 8 — Known Limitations & Scope Boundaries

## Explicit Phase Boundaries (Stop After Phase 8)

Per project phasing rules, the following accounting and final-stage ERP capabilities are intentionally **not implemented in Phase 8** and remain reserved for subsequent finance/costing phases:

1. **Customer Payment Receipts & Accounts Receivable Settlement:**
   - `billing.invoices.paid_paisa` remains `0` across Phase 8.
   - `payment_status` reflects `'UNPAID'` or `'CREDITED'` (when cancelled/credited), and `outstanding_paisa` equals `GREATEST(0, grand_total_paisa - credited_paisa - paid_paisa)`.
   - Benchmark Step 14 partial payment settlement (`₹4,000` receipt against `INV-...` reducing `Retailer A` receivable from `₹7,875.00` to `₹3,875.00`) is **explicitly deferred** until the Payments/Receivables phase.
2. **Step 8 Overhead & Final Batch Costing:**
   - Production `CostLot` FG valuation continues to reflect material FIFO consumption from Phase 7 without post-run labour/gas/overhead allocation.
3. **Final Financial / P&L Reconciliation Statements:**
   - Phase 8 reports provide operational Sales Register, GST Output Tax / HSN Summary, Credit Notes, Dispatch Register, Customer/Product Sales, and Invoice Outstanding views, accompanied by an explicit operational-register disclaimer (not statutory GSTR-1/GSTR-3B portal e-filing or IRP e-Invoice/E-Way Bill JSON signing).
4. **PDF Rendering:**
   - Uses a deterministic pure-Python PDF 1.4 renderer ([`pdf_generator.py`](file:///d:/mac/ota/backend/app/modules/billing/pdf_generator.py)) optimized for exact-paisa A4 single-page invoices and speed without external native C dependencies; very large invoices with dozens of distinct SKUs would require multi-page pagination support if extended beyond small-business catalogue sizes.
5. **Production Batch Traceability on Split Lots:**
   - `DispatchItem.batch_code_ref` records comma-separated batch codes depleted across FEFO `CostLot` layers (up to 120 characters) cleanly in `cost_lot_consumptions`.
