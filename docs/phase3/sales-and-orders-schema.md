# Sales, Catalog & Order Management Schema (`sales` Schema)

Designed for sub-minute mobile order capture, weak-network duplicate protection (`client_order_id`), place-of-supply GST readiness, and complete Admin approval traceability.

---

## 1. Salesmen, Customers & Address/GST Masters

### `sales.salesman_profiles`
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `user_id BIGINT NOT NULL UNIQUE REFERENCES iam.users(id) ON DELETE RESTRICT`
- `employee_code VARCHAR(32) NOT NULL UNIQUE`
- `territory VARCHAR(80) NULL`
- `is_active BOOLEAN NOT NULL DEFAULT TRUE`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

### `sales.customers`
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `code VARCHAR(32) NOT NULL UNIQUE` (`'CUST-RET-A'`, `'CUST-DIST-B'`)
- `name VARCHAR(160) NOT NULL`
- `customer_type VARCHAR(20) NOT NULL CHECK (customer_type IN ('RETAILER','DISTRIBUTOR'))`
- `gstin VARCHAR(15) NULL CHECK (gstin IS NULL OR gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$')`
- `primary_state_name VARCHAR(80) NOT NULL`
- `primary_state_code CHAR(2) NOT NULL CHECK (primary_state_code ~ '^[0-9]{2}$')`
- `phone VARCHAR(20) NULL`
- `assigned_salesman_id BIGINT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `credit_days INT NOT NULL DEFAULT 30 CHECK (credit_days >= 0)`
- `is_active BOOLEAN NOT NULL DEFAULT TRUE`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **GSTIN Cross-State Check (`chk_cust_gstin_state`):** `CHECK (gstin IS NULL OR SUBSTRING(gstin FROM 1 FOR 2) = primary_state_code)` — prevents typo where a Karnataka GSTIN (`29...`) is paired with state code `33`!

### `sales.customer_addresses`
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `customer_id BIGINT NOT NULL REFERENCES sales.customers(id) ON DELETE RESTRICT`
- `address_type VARCHAR(16) NOT NULL CHECK (address_type IN ('BILLING','SHIPPING'))`
- `line1 VARCHAR(200) NOT NULL`, `line2 VARCHAR(200) NULL`, `city VARCHAR(80) NOT NULL`
- `state_name VARCHAR(80) NOT NULL`, `state_code CHAR(2) NOT NULL CHECK (state_code ~ '^[0-9]{2}$')`
- `pincode CHAR(6) NOT NULL CHECK (pincode ~ '^[0-9]{6}$')`
- `is_default BOOLEAN NOT NULL DEFAULT FALSE`
- **Partial Unique Index:** `uq_cust_addr_default (customer_id, address_type) WHERE is_default IS TRUE`

---

## 2. Products, Pack Sizes & Price Lists

### `sales.products`
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `product_code VARCHAR(32) NOT NULL UNIQUE` (`'PROD-MURUKKU'`)
- `name VARCHAR(120) NOT NULL` (`'Murukku'`)
- `category VARCHAR(60) NOT NULL` (`'Murukku'`, `'Mixture'`, `'Chips'`, `'Sweets'`)
- `hsn_code VARCHAR(12) NOT NULL CHECK (hsn_code ~ '^[0-9]{4,8}$')` (`'21069099'`)
- `gst_rate_bps INT NOT NULL CHECK (gst_rate_bps >= 0 AND gst_rate_bps <= 2800 AND gst_rate_bps % 2 = 0)` (`500` = `5.0%`, divisible by 2 so CGST == SGST!)
- `is_active BOOLEAN NOT NULL DEFAULT TRUE`

### `sales.pack_sizes` *(Concrete Sellable SKUs)*
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `product_id BIGINT NOT NULL REFERENCES sales.products(id) ON DELETE RESTRICT`
- `sku_code VARCHAR(40) NOT NULL UNIQUE` (`'MRK-200G'`, `'MRK-500G'`)
- `display_name VARCHAR(140) NOT NULL` (`'Murukku 200 g'`)
- `pack_weight_g INT NOT NULL CHECK (pack_weight_g > 0)` (`200`)
- `packets_per_carton INT NOT NULL CHECK (packets_per_carton > 0)` (`20`)
- `base_selling_price_paisa BIGINT NOT NULL CHECK (base_selling_price_paisa >= 0)` (`5000` = `₹50.00`)
- `is_active BOOLEAN NOT NULL DEFAULT TRUE`
- **Unique:** `UNIQUE (product_id, pack_weight_g)`

### `sales.price_lists` & `sales.price_list_items`
- **`sales.price_lists`:**
  - `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
  - `name VARCHAR(100) NOT NULL`
  - `is_default BOOLEAN NOT NULL DEFAULT FALSE`
  - `customer_id BIGINT NULL REFERENCES sales.customers(id) ON DELETE RESTRICT` *(nullable; non-null for customer-specific override lists)*
  - `effective_from DATE NOT NULL`, `effective_to DATE NULL`
  - `is_active BOOLEAN NOT NULL DEFAULT TRUE`
  - **Constraints:** `CHECK (NOT (is_default AND customer_id IS NOT NULL))`, `CHECK (effective_to IS NULL OR effective_to >= effective_from)`
  - **Partial Unique:** `uq_pricelist_single_default (is_default) WHERE is_default IS TRUE AND is_active IS TRUE`
- **`sales.price_list_items`:**
  - `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
  - `price_list_id BIGINT NOT NULL REFERENCES sales.price_lists(id) ON DELETE RESTRICT`
  - `pack_size_id BIGINT NOT NULL REFERENCES sales.pack_sizes(id) ON DELETE RESTRICT`
  - `unit_price_paisa BIGINT NOT NULL CHECK (unit_price_paisa >= 0)`
  - `min_qty INT NOT NULL DEFAULT 1 CHECK (min_qty >= 1)`
  - `UNIQUE (price_list_id, pack_size_id, min_qty)`

---

## 3. Sales Orders, Status History & Approval Records

### `sales.sales_orders`
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `order_number VARCHAR(32) NOT NULL UNIQUE` (`'ORD-2026-0001'`)
- **`client_order_id UUID NOT NULL`** *(Generated on salesman phone before submit — prevents weak-network duplicates!)*
- `salesman_id BIGINT NOT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `customer_id BIGINT NOT NULL REFERENCES sales.customers(id) ON DELETE RESTRICT`
- `shipping_address_id BIGINT NULL REFERENCES sales.customer_addresses(id) ON DELETE RESTRICT`
- `place_of_supply_state_code CHAR(2) NOT NULL CHECK (place_of_supply_state_code ~ '^[0-9]{2}$')`
- `order_date DATE NOT NULL`
- `status VARCHAR(28) NOT NULL CHECK (status IN ('DRAFT','SUBMITTED','UNDER_REVIEW','CORRECTION_REQUESTED','APPROVED','REJECTED','INVOICED','PARTIALLY_DISPATCHED','DISPATCHED','CANCELLED'))`
- `has_shortage BOOLEAN NOT NULL DEFAULT FALSE`
- `notes TEXT NULL`
- `submitted_at TIMESTAMPTZ NULL`
- `approved_by BIGINT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `approved_at TIMESTAMPTZ NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **Duplicate Submission Constraint:** **`CONSTRAINT uq_sales_orders_idempotency UNIQUE (salesman_id, client_order_id)`**

### `sales.sales_order_items`
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `sales_order_id BIGINT NOT NULL REFERENCES sales.sales_orders(id) ON DELETE RESTRICT`
- `pack_size_id BIGINT NOT NULL REFERENCES sales.pack_sizes(id) ON DELETE RESTRICT`
- `ordered_qty_pkts INT NOT NULL CHECK (ordered_qty_pkts > 0)`
- `approved_qty_pkts INT NULL CHECK (approved_qty_pkts IS NULL OR approved_qty_pkts >= 0)`
- `unit_price_paisa BIGINT NOT NULL CHECK (unit_price_paisa >= 0)` *(Snapshot from price list; Admin edits logged in `audit.audit_logs`)*
- `line_taxable_paisa BIGINT GENERATED ALWAYS AS ((COALESCE(approved_qty_pkts, ordered_qty_pkts))::BIGINT * unit_price_paisa) STORED`
- **Unique:** `UNIQUE (sales_order_id, pack_size_id)`

### `sales.sales_order_status_history`
*Purpose:* Append-only timeline powering the salesman's live order status screen (`SCR-SM-07`) and audit timelines.
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `sales_order_id BIGINT NOT NULL REFERENCES sales.sales_orders(id) ON DELETE RESTRICT`
- `from_status VARCHAR(28) NULL`
- `to_status VARCHAR(28) NOT NULL`
- `changed_by BIGINT NOT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `reason TEXT NULL`
- `changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

### `sales.sales_order_approvals`
*Purpose:* Records every Admin verification pass, exact stock snapshot seen at verification time, shortage flags (`120` ordered vs `88` available = `32` shortage for Distributor B), and decision reason.
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `sales_order_id BIGINT NOT NULL REFERENCES sales.sales_orders(id) ON DELETE RESTRICT`
- `reviewed_by BIGINT NOT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `decision VARCHAR(28) NOT NULL CHECK (decision IN ('APPROVED','REJECTED','CORRECTION_REQUESTED','HELD_SHORTAGE'))`
- `ordered_total_pkts INT NOT NULL CHECK (ordered_total_pkts > 0)`
- `available_total_pkts INT NOT NULL CHECK (available_total_pkts >= 0)`
- `shortage_pkts INT NOT NULL CHECK (shortage_pkts >= 0)`
- `stock_snapshot JSONB NOT NULL` *(Exact per-SKU `on_hand`, `reserved`, `available`, `shortage` at review moment)*
- `remarks TEXT NULL`
- `decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **Check (`chk_soa_shortage_approve`):** `CHECK (NOT (decision = 'APPROVED' AND shortage_pkts > 0))` — database itself forbids recording an `APPROVED` decision with `shortage_pkts > 0`!
