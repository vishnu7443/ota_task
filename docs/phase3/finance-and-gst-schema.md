# Purchasing, GST Billing, Dispatch & Receivables Schema (`purchasing`, `billing`, `finance`)

Covers Supplier Purchases, Financial-Year GST Invoice numbering, CGST/SGST vs IGST components, Credit Note cancellations, Dispatches, Payments, and Customer Receivables using strict integer-paisa `BIGINT` arithmetic.

---

## 1. `purchasing` Schema (Suppliers, Optional POs & Purchase Receipts)

### `purchasing.suppliers`
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `code VARCHAR(32) NOT NULL UNIQUE`, `name VARCHAR(160) NOT NULL`
- `gstin VARCHAR(15) NULL CHECK (gstin IS NULL OR gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$')`
- `state_code CHAR(2) NOT NULL CHECK (state_code ~ '^[0-9]{2}$')`
- `phone VARCHAR(20) NULL`, `address TEXT NULL`, `is_active BOOLEAN NOT NULL DEFAULT TRUE`

### `purchasing.purchase_orders` & `purchasing.purchase_order_items`
- **`purchase_orders`:** `id BIGINT PK`, `po_number VARCHAR(32) UNIQUE`, `supplier_id BIGINT FK`, `order_date DATE`, `status VARCHAR(24) CHECK (status IN ('DRAFT','APPROVED','PARTIALLY_RECEIVED','RECEIVED','CLOSED','CANCELLED'))`, `total_paisa BIGINT CHECK (total_paisa >= 0)`, `created_by BIGINT FK`, `approved_by BIGINT NULL FK`.
- **`purchase_order_items`:** `id BIGINT PK`, `purchase_order_id BIGINT FK`, `material_id BIGINT FK -> production.materials`, `ordered_qty_base NUMERIC(18,3) CHECK (ordered_qty_base > 0)`, `received_qty_base NUMERIC(18,3) DEFAULT 0 CHECK (received_qty_base >= 0)`, `entered_uom VARCHAR(16)`, `unit_rate_paisa BIGINT CHECK (unit_rate_paisa >= 0)`.

### `purchasing.purchase_receipts` & `purchasing.purchase_receipt_items`
- **`purchase_receipts`:** `id BIGINT PK`, `receipt_number VARCHAR(32) UNIQUE` (`'PUR-2026-0001'`), `purchase_order_id BIGINT NULL FK`, `supplier_id BIGINT FK`, `supplier_bill_ref VARCHAR(64) NULL`, `receipt_date DATE NOT NULL`, `status VARCHAR(16) NOT NULL CHECK (status IN ('DRAFT','RECEIVED','CLOSED'))`, `subtotal_paisa BIGINT NOT NULL CHECK (subtotal_paisa >= 0)`, `input_gst_paisa BIGINT NOT NULL DEFAULT 0 CHECK (input_gst_paisa >= 0)`, `total_paisa BIGINT GENERATED ALWAYS AS (subtotal_paisa + input_gst_paisa) STORED`, `received_by BIGINT NOT NULL FK`, `received_at TIMESTAMPTZ`.
- **`purchase_receipt_items`:**
  - `id BIGINT PK`, `purchase_receipt_id BIGINT NOT NULL FK`, `material_id BIGINT NOT NULL FK -> production.materials`
  - `entered_qty NUMERIC(18,3) NOT NULL CHECK (entered_qty > 0)`, `entered_uom VARCHAR(16) NOT NULL`
  - `received_qty_base NUMERIC(18,3) NOT NULL CHECK (received_qty_base > 0)` *(e.g. `60000.000` g)*
  - `entered_unit_rate_paisa BIGINT NOT NULL CHECK (entered_unit_rate_paisa >= 0)` *(e.g. `4500` paise/kg)*
  - `unit_cost_paisa_per_base NUMERIC(18,6) NOT NULL CHECK (unit_cost_paisa_per_base >= 0)` *(e.g. `4.500000` paise/g)*
  - `line_total_paisa BIGINT NOT NULL CHECK (line_total_paisa >= 0)` *(e.g. `270000` paise = `₹2,700.00`)*

---

## 2. `billing` Schema (FY Sequences, GST Invoices, Credit Notes & Dispatches)

### `billing.fiscal_sequences`
*Purpose:* Gap-free Indian FY counter (`April 1 – March 31`) locked with `SELECT ... FOR UPDATE` inside `TX-03` / `TX-05`.
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `doc_type VARCHAR(16) NOT NULL CHECK (doc_type IN ('INVOICE','CREDIT_NOTE'))`
- `financial_year VARCHAR(7) NOT NULL CHECK (financial_year ~ '^[0-9]{4}-[0-9]{2}$')` (`'2026-27'`)
- `prefix VARCHAR(16) NOT NULL` (`'INV'` or `'CN'`)
- `last_seq_no INT NOT NULL DEFAULT 0 CHECK (last_seq_no >= 0)`
- **Unique:** `UNIQUE (doc_type, financial_year)`

### `billing.invoices`
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `invoice_number VARCHAR(32) NOT NULL UNIQUE` (`'INV/2026-27/0001'`)
- `financial_year VARCHAR(7) NOT NULL`
- `sales_order_id BIGINT NOT NULL UNIQUE REFERENCES sales.sales_orders(id) ON DELETE RESTRICT`
- `customer_id BIGINT NOT NULL REFERENCES sales.customers(id) ON DELETE RESTRICT`
- `seller_gstin VARCHAR(15) NOT NULL`, `seller_state_code CHAR(2) NOT NULL`
- `buyer_gstin VARCHAR(15) NULL`, `place_of_supply_state_code CHAR(2) NOT NULL`
- `supply_type VARCHAR(16) NOT NULL CHECK (supply_type IN ('INTRA_STATE','INTER_STATE'))`
- `invoice_date DATE NOT NULL`, `due_date DATE NOT NULL`
- `doc_status VARCHAR(20) NOT NULL CHECK (doc_status IN ('DRAFT','ISSUED','CANCELLED_BY_CN'))`
- `payment_status VARCHAR(20) NOT NULL DEFAULT 'UNPAID' CHECK (payment_status IN ('UNPAID','PARTIALLY_PAID','PAID','CREDITED'))`
- `dispatch_status VARCHAR(16) NOT NULL DEFAULT 'PENDING' CHECK (dispatch_status IN ('PENDING','PARTIAL','DISPATCHED'))`
- `taxable_total_paisa BIGINT NOT NULL CHECK (taxable_total_paisa >= 0)`
- `cgst_total_paisa BIGINT NOT NULL DEFAULT 0 CHECK (cgst_total_paisa >= 0)`
- `sgst_total_paisa BIGINT NOT NULL DEFAULT 0 CHECK (sgst_total_paisa >= 0)`
- `igst_total_paisa BIGINT NOT NULL DEFAULT 0 CHECK (igst_total_paisa >= 0)`
- `grand_total_paisa BIGINT GENERATED ALWAYS AS (taxable_total_paisa + cgst_total_paisa + sgst_total_paisa + igst_total_paisa) STORED`
- `issued_by BIGINT NOT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **GST Symmetry & Exclusivity Check (`chk_inv_gst_split`):**
  ```sql
  CHECK (
    (supply_type = 'INTRA_STATE' AND igst_total_paisa = 0 AND cgst_total_paisa = sgst_total_paisa)
    OR
    (supply_type = 'INTER_STATE' AND cgst_total_paisa = 0 AND sgst_total_paisa = 0)
  )
  ```

### `billing.invoice_items` & `billing.invoice_tax_components`
- **`invoice_items`:**
  - `id BIGINT PK`, `invoice_id BIGINT FK`, `sales_order_item_id BIGINT FK`, `pack_size_id BIGINT FK`
  - `hsn_code VARCHAR(12) NOT NULL`, `qty_pkts INT NOT NULL CHECK (qty_pkts > 0)`
  - `unit_price_paisa BIGINT NOT NULL CHECK (unit_price_paisa >= 0)`
  - `taxable_paisa BIGINT NOT NULL CHECK (taxable_paisa >= 0)`
  - `gst_rate_bps INT NOT NULL CHECK (gst_rate_bps >= 0)`
  - `cgst_paisa BIGINT NOT NULL DEFAULT 0`, `sgst_paisa BIGINT NOT NULL DEFAULT 0`, `igst_paisa BIGINT NOT NULL DEFAULT 0`
  - `line_total_paisa BIGINT GENERATED ALWAYS AS (taxable_paisa + cgst_paisa + sgst_paisa + igst_paisa) STORED`
- **`invoice_tax_components`:** *(GSTR-1/3B summary table)*
  - `id BIGINT PK`, `invoice_id BIGINT FK`, `hsn_code VARCHAR(12) NOT NULL`, `tax_type VARCHAR(8) NOT NULL CHECK (tax_type IN ('CGST','SGST','IGST'))`, `rate_bps INT NOT NULL`, `taxable_base_paisa BIGINT NOT NULL`, `tax_amount_paisa BIGINT NOT NULL`
  - `UNIQUE (invoice_id, hsn_code, tax_type, rate_bps)`

### `billing.credit_notes` & `billing.credit_note_items`
- **`credit_notes`:** `id BIGINT PK`, `cn_number VARCHAR(32) UNIQUE` (`'CN/2026-27/0001'`), `financial_year VARCHAR(7)`, `original_invoice_id BIGINT NOT NULL FK -> billing.invoices`, `issue_date DATE NOT NULL`, `reason TEXT NOT NULL CHECK (length(trim(reason)) >= 5)`, `status VARCHAR(16) NOT NULL CHECK (status IN ('DRAFT','ISSUED'))`, `taxable_reversed_paisa BIGINT NOT NULL`, `cgst_reversed_paisa BIGINT NOT NULL`, `sgst_reversed_paisa BIGINT NOT NULL`, `igst_reversed_paisa BIGINT NOT NULL`, `total_reversed_paisa BIGINT GENERATED ALWAYS AS (taxable_reversed_paisa + cgst_reversed_paisa + sgst_reversed_paisa + igst_reversed_paisa) STORED`, `issued_by BIGINT FK`, `issued_at TIMESTAMPTZ`.
- **`credit_note_items`:** `id BIGINT PK`, `credit_note_id BIGINT FK`, `invoice_item_id BIGINT FK`, `pack_size_id BIGINT FK`, `qty_pkts INT NOT NULL CHECK (qty_pkts > 0)`, `return_disposition VARCHAR(24) NOT NULL CHECK (return_disposition IN ('NONE_NOT_DISPATCHED','RESTOCK_SELLABLE','SCRAP_DAMAGED'))`, `taxable_reversed_paisa BIGINT`, `cgst_reversed_paisa BIGINT`, `sgst_reversed_paisa BIGINT`, `igst_reversed_paisa BIGINT`.

### `billing.dispatches` & `billing.dispatch_items`
- **`dispatches`:** `id BIGINT PK`, `dispatch_number VARCHAR(32) UNIQUE` (`'DSP-2026-0001'`), `invoice_id BIGINT NOT NULL FK -> billing.invoices`, `sales_order_id BIGINT NOT NULL FK -> sales.sales_orders`, `dispatch_date DATE NOT NULL`, `vehicle_or_lr_ref VARCHAR(120) NULL`, `notes TEXT NULL`, `dispatched_by BIGINT NOT NULL FK`, `dispatched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`.
- **`dispatch_items`:** `id BIGINT PK`, `dispatch_id BIGINT FK`, `invoice_item_id BIGINT FK`, `pack_size_id BIGINT FK`, `dispatched_qty_pkts INT NOT NULL CHECK (dispatched_qty_pkts > 0)`, `UNIQUE (dispatch_id, invoice_item_id)`. *(Service + trigger verify `SUM(dispatched_qty_pkts) <= invoice_item.qty_pkts`.)*

---

## 3. `finance` Schema (Payments, Allocations & Receivables)

### `finance.payments`
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `payment_number VARCHAR(32) NOT NULL UNIQUE` (`'PMT-2026-0001'`)
- `customer_id BIGINT NOT NULL REFERENCES sales.customers(id) ON DELETE RESTRICT`
- `payment_date DATE NOT NULL`
- `amount_paisa BIGINT NOT NULL CHECK (amount_paisa > 0)`
- `payment_mode VARCHAR(16) NOT NULL CHECK (payment_mode IN ('CASH','UPI','NEFT','RTGS','CHEQUE'))`
- `reference_no VARCHAR(80) NULL`
- **`idempotency_key UUID NOT NULL UNIQUE`** *(Prevents double submission on `PMT-001`!)*
- `status VARCHAR(24) NOT NULL CHECK (status IN ('RECORDED','PARTIALLY_ALLOCATED','ALLOCATED','REVERSED'))`
- `reversal_reason TEXT NULL`, `reversed_by BIGINT NULL REFERENCES iam.users(id)`, `reversed_at TIMESTAMPTZ NULL`
- `recorded_by BIGINT NOT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **Duplicate Reference Heuristic Index:** Partial index on `(customer_id, payment_date, amount_paisa, reference_no) WHERE status <> 'REVERSED' AND reference_no IS NOT NULL`.

### `finance.payment_allocations`
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `payment_id BIGINT NOT NULL REFERENCES finance.payments(id) ON DELETE RESTRICT`
- `invoice_id BIGINT NOT NULL REFERENCES billing.invoices(id) ON DELETE RESTRICT`
- `allocated_paisa BIGINT NOT NULL CHECK (allocated_paisa > 0)`
- `is_reversed BOOLEAN NOT NULL DEFAULT FALSE`
- `allocated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **Unique Active Allocation:** `UNIQUE (payment_id, invoice_id) WHERE is_reversed IS FALSE`

### `finance.customer_receivables`
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `customer_id BIGINT NOT NULL REFERENCES sales.customers(id) ON DELETE RESTRICT`
- `invoice_id BIGINT NOT NULL UNIQUE REFERENCES billing.invoices(id) ON DELETE RESTRICT`
- `invoice_date DATE NOT NULL`, `due_date DATE NOT NULL`
- `original_paisa BIGINT NOT NULL CHECK (original_paisa >= 0)`
- `credited_paisa BIGINT NOT NULL DEFAULT 0 CHECK (credited_paisa >= 0)`
- `paid_paisa BIGINT NOT NULL DEFAULT 0 CHECK (paid_paisa >= 0)`
- `outstanding_paisa BIGINT GENERATED ALWAYS AS (original_paisa - credited_paisa - paid_paisa) STORED`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **Non-Negative Receivable Cap (`chk_ar_non_negative`):** `CHECK (credited_paisa + paid_paisa <= original_paisa)` — guarantees `outstanding_paisa >= 0` mathematically at the database engine!
