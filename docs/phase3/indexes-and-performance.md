# Indexing, Performance & Reporting Views (`reporting` Schema)

Every index below maps directly to a concrete operational screen (`docs/phase1/ui-screen-inventory.md`) or monthly audit report (`Section 4.6`). Unnecessary speculative indexes are omitted to keep writes fast.

---

## 1. Strategic Index Catalogue

| Target Workload | Index Definition (Table & Columns) | Index Type | Business & Query Justification |
| --- | --- | --- | --- |
| **Salesman Order History (`SCR-SM-06`, `SCR-SM-08`)** | `idx_orders_salesman_date` on `sales.sales_orders (salesman_id, order_date DESC, id DESC)` | B-tree Composite | Mobile "My Orders" and Customer-wise sales filter strictly by `salesman_id` sorted newest-first without scanning other salesmen's orders. |
| **Admin Pending Queue (`SCR-ADM-01`)** | `idx_orders_pending_queue` on `sales.sales_orders (status, created_at ASC)` **Partial:** `WHERE status IN ('SUBMITTED','UNDER_REVIEW','CORRECTION_REQUESTED','APPROVED','INVOICED')` | Partial B-tree | Keeps the active Admin verification queue tiny (`O(open orders)`) even after years of `DISPATCHED`/`REJECTED` history! |
| **Customer Orders & Invoices (`SCR-ADM-03`)** | `idx_invoices_customer_date` on `billing.invoices (customer_id, invoice_date DESC)` | B-tree Composite | Instant lookup of customer billing history and receivable drill-down. |
| **Monthly Sales & GSTR-1/3B Reports** | `idx_invoices_fy_date_status` on `billing.invoices (invoice_date, doc_status, supply_type)` `INCLUDE (taxable_total_paisa, cgst_total_paisa, sgst_total_paisa, igst_total_paisa, grand_total_paisa)` | Covering B-tree | Enables index-only scans for monthly Sales Register & Outward GST summaries filtered by date range (`Section 4.6`). |
| **Inventory Ledger Drill-Down (`SCR-ADM-07`, `SCR-AUD-04`)** | `idx_mov_material_time` on `inventory.inventory_movements (material_id, occurred_at ASC, id ASC) WHERE material_id IS NOT NULL`<br>`idx_mov_pack_time` on `inventory.inventory_movements (pack_size_id, occurred_at ASC, id ASC) WHERE pack_size_id IS NOT NULL` | Partial Composite | Reconstructs chronological running passbook balance and period opening/closing stock (`Opening + Δ = Closing`) per item without scanning unrelated items. |
| **Inventory Source Document Reverse Lookup** | `idx_mov_prod_run` on `inventory.inventory_movements (production_run_id) WHERE production_run_id IS NOT NULL` *(and similarly for `purchase_receipt_item_id`, `dispatch_item_id`)* | Partial B-tree | Instant drill-down from any Production Run / Purchase / Dispatch to all its stock ledger rows. |
| **FIFO & FEFO Lot Consumption (`TX-08`, `TX-04`)** | `idx_lots_fifo_open` on `inventory.cost_lots (material_id, received_at ASC, id ASC) WHERE remaining_qty_base > 0`<br>`idx_lots_fg_fefo` on `inventory.cost_lots (pack_size_id, expiry_date ASC NULLS LAST, received_at ASC) WHERE remaining_qty_base > 0` | Partial Composite | Only indexes non-empty open lots; FIFO lot lookup hits index tip in sub-millisecond time. |
| **Production Runs & Variance Report** | `idx_runs_date_status` on `production.production_runs (run_date DESC, status, pack_size_id)` | B-tree Composite | Supports floor hub today's runs + monthly Production Variance & Costing reports. |
| **Open Variance Alerts (`SCR-OWN-01`)** | `idx_alerts_open` on `audit.variance_alerts (created_at DESC) WHERE status = 'OPEN'` | Partial B-tree | Instant Owner dashboard alert badge & banner load. |
| **Payment Ageing & Collections (`SCR-AUD-06`)** | `idx_ar_open_ageing` on `finance.customer_receivables (customer_id, invoice_date ASC) WHERE outstanding_paisa > 0` | Partial B-tree | Scans strictly unpaid/partially paid invoices (`outstanding_paisa > 0`) for `0–30 / 31–60 / 61–90 / 90+` day AR ageing buckets. |
| **Audit Trail Explorer (`SCR-AUD-06`)** | `idx_audit_entity_time` on `audit.audit_logs (entity_table, entity_id, occurred_at DESC)` + `idx_audit_actor_time (actor_user_id, occurred_at DESC)` | B-tree Composite | Fast filtering of who edited which invoice/production run and when. |
| **Customer & SKU Search (Mobile `<1 min`)** | `idx_customers_name_trgm` on `sales.customers USING GIN (name gin_trgm_ops)` *(optional `pg_trgm`)* + B-tree on `(assigned_salesman_id, is_active)` | GIN Trigram + B-tree | Instant mobile substring search (`"Retailer A"`) as salesman types 2–3 characters on phone. |

---

## 2. `reporting` Schema Read-Only Views

All 6 mandatory monthly audit reports (`Section 4.6`) operate over deterministic SQL `VIEW`s querying immutable posted sources:

1. **`reporting.v_sales_register`:** Joins `billing.invoices` (`doc_status <> 'DRAFT'`), `sales.customers`, `sales.sales_orders`, and `iam.users` (salesman), showing invoice number, FY, state, supply type, taxable, CGST, SGST, IGST, grand total, and status (`ISSUED` vs `CANCELLED_BY_CN`).
2. **`reporting.v_gst_outward_summary`:** Aggregates `billing.invoice_tax_components` (positive outward tax) netted against `billing.credit_notes` (`status = 'ISSUED'`), grouped by `supply_type`, `hsn_code`, B2B (`buyer_gstin IS NOT NULL`) vs B2C (`buyer_gstin IS NULL`) for GSTR-1 / GSTR-3B export.
3. **`reporting.v_purchase_register`:** Joins `purchasing.purchase_receipts` (`status IN ('RECEIVED','CLOSED')`), `purchasing.purchase_receipt_items`, `purchasing.suppliers`, and `production.materials`.
4. **`reporting.v_stock_reconciliation`:** Joins `inventory.inventory_balances` against aggregated `SUM(inventory.inventory_movements.signed_qty_base)` verifying `drift_qty_base = 0.000` across every raw material, packaging item, and finished SKU.
5. **`reporting.v_production_summary`:** Joins `production.production_runs`, `sales.pack_sizes`, `production.bom_versions`, `production.production_variances`, and `costing.production_cost_summaries` for planned vs actual consumption, yield %, wastage, overhead, cost/packet, and margin %.
6. **`reporting.v_ar_ageing`:** Queries `finance.customer_receivables` (`WHERE outstanding_paisa > 0`) calculating `CURRENT_DATE - invoice_date` into `0–30`, `31–60`, `61–90`, and `>90` day buckets per customer.
