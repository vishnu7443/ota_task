# Phase 9 — Profitability & Margin Calculations

## Accounting Separation Rules (`finance/service.py::get_profitability_report`)

To preserve statutory GST accounting accuracy, the profitability engine explicitly separates distinct financial concepts and rejects common ERP reporting errors:

1. **Revenue Excludes GST (`net_revenue_paisa`):**
   - `gross_revenue_paisa = SUM(issued invoice_items.taxable_paisa)` (never including CGST, SGST, or IGST).
   - `credited_revenue_paisa = SUM(issued credit_note_items.taxable_reversed_paisa)`.
   - `net_revenue_paisa = gross_revenue_paisa - credited_revenue_paisa`.
2. **GST Collected Reported Separately (`gst_collected_paisa`):**
   - Calculated as statutory tax liability `(cgst + sgst + igst)` net of reversed credit note GST. Never inflationarily added to sales revenue or gross profit.
3. **Cash Receipts Never Counted as Revenue (`cash_received_paisa`):**
   - Customer collections (`finance.payments` net of `REVERSED` payments and posted `payment_refunds`) represent Balance Sheet cash settlement (`AR -> Cash`), tracked separately alongside `outstanding_receivables_paisa`.
4. **COGS & Margin Attribution (`total_cogs_paisa`, `gross_profit_paisa`):**
   - **Dispatched Stock COGS (`dispatched_cogs_paisa`):** Exact FEFO `CostLotConsumption.total_cost_paisa` from posted dispatches (`DISPATCH_OUT`), netted cleanly for `CREDIT_RETURN_IN` restocked sellable returns (`_item_net_cost` fallback when return cost exists).
   - **Pending-Dispatch Invoiced Stock (`pending_dispatch_estimated_cogs_paisa`):** For issued invoices not yet fully dispatched, estimates COGS transparently using current FIFO/production cost layers (`ProductionCostSummary.cost_per_packet_paisa` / FG `CostLot.unit_cost_paisa`) and discloses the dispatched vs estimated split clearly.
   - `gross_profit_paisa = net_revenue_paisa - total_cogs_paisa`
   - `gross_margin_pct = ROUND_HALF_UP((gross_profit_paisa / net_revenue_paisa) * 100, 2)` when `net_revenue_paisa > 0`.
5. **Explicit Net Profit Disclaimer:**
   - Every response returns `disclaimer` stating explicitly that figures represent **Manufacturing & Sales Gross Margin** only; non-production operating expenses (sales commissions, office rent, admin salaries, marketing, outward freight not in BOM, financing costs) are outside system scope and **Net Profit is not claimed**.

## Breakdown Dimensions (`GET /api/v1/finance/profitability`)

Supports `date_from`, `date_to`, `customer_id`, and `pack_size_id` filters across four views:
- **`by_product`:** Invoiced pkts, returned pkts, net sold pkts, gross/credited/net revenue, GST, dispatched COGS, pending estimated COGS, gross profit & margin %.
- **`by_customer`:** Invoice count, net revenue, GST, COGS, gross profit & margin %, cash received, and open AR per customer.
- **`by_order`:** Order-level traceability joining Sales Order -> GST Invoice -> COGS -> Cash Collected -> Outstanding Balance.
- **`by_date`:** Daily revenue, GST, COGS, gross margin, and cash collected on payment dates.
