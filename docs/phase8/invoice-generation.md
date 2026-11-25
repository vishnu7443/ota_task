# Phase 8 — Invoice Generation Workflow

## Preconditions & Order Binding

`create_invoice_from_order` in [`service.py`](file:///d:/mac/ota/backend/app/modules/billing/service.py) creates a GST Tax Invoice strictly from an **existing approved Sales Order**:

1. Locks the `SalesOrder` row (`FOR UPDATE`).
2. Requires `order.status == 'APPROVED'`; rejects non-approved orders with `409 INVALID_STATE_TRANSITION`.
3. Enforces one active invoice per order via both application guard and partial unique DB index `uq_invoices_active_order` (`sales_order_id` unique where `doc_status <> 'CANCELLED_BY_CN'`); duplicates raise `409 DUPLICATE_INVOICE`.
4. Requires `Customer.is_active == True`.

---

## Authoritative Server-Side Snapshot Capture

All prices, HSN classifications, GST rates, customer GSTINs, and company profiles come strictly from authoritative PostgreSQL records:
- **Seller Snapshot:** `iam.company_profile` (`legal_name`, `gstin`, `state_name`, `state_code`, `address`).
- **Buyer Snapshot:** `sales.customers` & `sales.customer_addresses` (`customer_name`, `customer_type`, `buyer_gstin`, `billing_address_snapshot`, `shipping_address_snapshot`, `credit_days` -> `due_date`, `payment_terms`).
- **Line Snapshot (`billing.invoice_items`):** Captures `sku_code`, `product_name`, `description`, `hsn_code`, approved `qty_pkts`, authoritative `unit_price_paisa`, validated per-item `discount_paisa`, `taxable_paisa`, `gst_rate_bps`, `cgst_rate_bps`, `sgst_rate_bps`, `igst_rate_bps`, `cgst_paisa`, `sgst_paisa`, `igst_paisa`, and persisted generated column `line_total_paisa`.
- **Tax Bucket Snapshot (`billing.invoice_tax_components`):** Summarizes tax base & tax amount per `(hsn_code, tax_type, rate_bps)`.
- **Audit Snapshot (`tax_calculation_snapshot` JSONB):** Stores full supply rationale and inputs so subsequent product/tax master edits cannot mutate historical invoice behavior.

---

## Draft vs. Direct Issue & Stock Isolation

- Invoice creation accepts `issue_immediately` (`false` creates an unnumbered `DRAFT` with `DRF-INV-...`; `true` generates draft and executes `_perform_issue_invoice` atomically in the same transaction).
- Generating or issuing an invoice **never deducts physical inventory (`on_hand_qty_base`) or releases stock reservations**; finished goods stay physically reserved until `DISPATCH_POSTED` (`billing.dispatches`).
