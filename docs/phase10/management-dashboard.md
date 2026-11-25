# Management Intelligence Dashboard (`intelligence`)

## 1. Purpose & Data Integrity Guarantee

`GET /api/v1/intelligence/dashboard` provides Factory Admin, Owner, and Accountant/Auditor roles with an executive cockpit backed 100% by real operational and financial records (`app/modules/intelligence/service.py`). Zero hardcoded or simulated numbers are used.

All financial revenue, COGS, cash, and AR metrics reuse the single-source-of-truth functions in `app/modules/finance/service.py` (`get_profitability_report`, `get_customer_receivables_summary`, `get_ageing_report`) and `app/modules/inventory/service.py` (`get_inventory_overview`), guaranteeing zero KPI drift across dashboards.

---

## 2. Executive Sections Delivered

1. **Sales & GST Revenue Summary:**
   - Gross Taxable Value, GST Liability Collected, Credit Notes Reversed, **Net Sales (Excl. GST)**, Invoice Count, Credit Note Count.
   - Order Pipeline Counts (`pending_verification`, `approved`, `invoiced`, `dispatched_or_partial`, `rejected_or_cancelled`, `shortage_orders`).
   - Top 10 Product SKUs (`net_sold_qty_pkts`, `net_revenue_paisa`, `total_cogs_paisa`, `gross_profit_paisa`, `gross_margin_pct`).
   - Top 10 Customers (`net_revenue_paisa`, `cash_received_paisa`, `outstanding_receivables_paisa`, `gross_profit_paisa`).
   - Chronological Daily Sales & Collection Trend (`daily_trend`).
2. **Inventory Intelligence:**
   - Tracked SKU counts across `RAW_MATERIAL`, `PACKAGING_MATERIAL`, and `FINISHED_GOOD`.
   - Total FIFO open `CostLot` Stock Valuation in integer paise.
   - Low Stock Alerts (`available <= reorder_level`) + Pending Stock Adjustments count.
   - Period Inventory Movement aggregation grouped by `movement_type`.
3. **Production Intelligence:**
   - Total runs in period (`posted`, `in_progress`, `planned`), expected vs good vs rejected packets, and computed **Yield Efficiency %**.
   - Total Batch Cost, Weighted Average Unit Cost per Good Packet (`paise`), and Wastage + Packaging Damage + Rejected Cost Impact.
   - Flagged BOM/yield variances, Open Variance Alerts, and Per-SKU Production Performance table.
4. **Finance, Cash & AR Ageing:**
   - Gross Receipts, Refunds Issued, **Net Cash Collected**, and Unallocated Customer Advances.
   - Total Outstanding Receivables vs Overdue Receivables broken down strictly by `due_date` across `Not Due`, `1–30`, `31–60`, `61–90`, and `> 90` days.
   - Explicit `profitability_disclaimer`: **Gross Profit = Net Revenue (excl. GST) − COGS (Materials + Packaging + Configured Production Overheads)**. Net Profit is explicitly NOT claimed because non-production SG&A operating expenses lie outside system scope.
5. **Operations Queues & Actionable Watchlist:**
   - Live counters for pending POs, GRNs, Stock Adjustments, Dispatches, Delivery Exceptions, Open Reconciliation Discrepancies, and Period Security Events (`LOGIN_FAILED`, `ACCESS_DENIED`).
   - Severity-ranked Watchlist items (`CRITICAL`, `HIGH`, `MEDIUM`, `INFO`) with direct navigation routes (`/admin/reconciliation`, `/admin/dispatch`, `/admin/finance/receivables`, `/admin/inventory`, `/admin/production/variances`, `/admin/orders`, `/admin/audit`).
6. **Executive CSV Export (`GET /api/v1/intelligence/reports/export/csv`):**
   - Streams formatted CSV containing Executive KPIs, Product Performance, Customer Performance, and Low-Stock Alerts.
