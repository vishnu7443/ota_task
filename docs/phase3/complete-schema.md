# Complete Physical PostgreSQL Schema Reference

Authoritative data dictionary for all **51 physical tables** across **9 schemas** (plus 6 reporting views documented in [indexes-and-performance.md](file:///d:/mac/ota/docs/phase3/indexes-and-performance.md)). Detailed domain rules for each area appear in `inventory-schema.md`, `production-schema.md`, `sales-and-orders-schema.md`, and `finance-and-gst-schema.md`.

---

## 1. Schema Summary Overview

| Schema | Tables | Purpose |
| --- | --- | --- |
| `iam` | `company_profiles`, `roles`, `users` | Auth, 5-role RBAC, factory GST & policy config |
| `sales` | `salesman_profiles`, `customers`, `customer_addresses`, `products`, `pack_sizes`, `price_lists`, `price_list_items`, `sales_orders`, `sales_order_items`, `sales_order_status_history`, `sales_order_approvals` | Masters, multi-pack SKUs, pricing, mobile orders, approval audits |
| `purchasing` | `suppliers`, `purchase_orders`, `purchase_order_items`, `purchase_receipts`, `purchase_receipt_items` | Suppliers, optional POs, Goods/Material Receipts |
| `production` | `materials`, `unit_conversions`, `recipe_templates`, `bom_headers`, `bom_versions`, `bom_components`, `production_runs`, `production_material_issues`, `production_outputs`, `production_wastages`, `production_variances` | UOM rules, shared base recipes, versioned BOMs, production runs, wastage, variance |
| `costing` | `production_overheads`, `production_cost_summaries` | Labour/gas/monthly overhead & packet unit cost |
| `inventory` | `opening_balances`, `inventory_balances`, `cost_lots`, `cost_lot_consumptions`, `stock_adjustments`, `inventory_movements` | Source-traceable stock ledger, FIFO lots, concurrency lock anchor |
| `billing` | `fiscal_sequences`, `invoices`, `invoice_items`, `invoice_tax_components`, `credit_notes`, `credit_note_items`, `dispatches`, `dispatch_items` | FY numbering, GST invoices, credit notes, dispatches |
| `finance` | `payments`, `payment_allocations`, `customer_receivables` | Customer collections, allocations, AR tracking |
| `audit` | `variance_alerts`, `audit_logs` | Tolerance alerts & immutable audit log |

---

## 2. `iam` Schema Tables

### `iam.company_profiles`
*Purpose:* Singleton factory configuration (legal GSTIN, state code `33`, tolerance `3%`, valuation strategy).
- **PK:** `id BIGINT GENERATED ALWAYS AS IDENTITY`
- **Columns:**
  - `legal_name VARCHAR(200) NOT NULL`
  - `gstin VARCHAR(15) NOT NULL` (`CHECK (gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$')`)
  - `state_name VARCHAR(80) NOT NULL`
  - `state_code CHAR(2) NOT NULL` (`CHECK (state_code ~ '^[0-9]{2}$')`)
  - `address TEXT NOT NULL`
  - `variance_tolerance_pct NUMERIC(5,2) NOT NULL DEFAULT 3.00` (`CHECK (variance_tolerance_pct >= 0)`)
  - `valuation_method VARCHAR(24) NOT NULL DEFAULT 'FIFO'` (`CHECK (valuation_method IN ('FIFO','WEIGHTED_AVERAGE','LAST_PRICE'))`)
  - `is_singleton BOOLEAN NOT NULL DEFAULT TRUE` (`CHECK (is_singleton IS TRUE)`, `UNIQUE (is_singleton)`)
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

### `iam.roles`
*Purpose:* Canonical 5-role RBAC master (`SALESMAN`, `FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR`, `ACCOUNTANT_AUDITOR`, `OWNER`).
- **PK:** `id BIGINT GENERATED ALWAYS AS IDENTITY`
- **Columns:** `code VARCHAR(32) NOT NULL UNIQUE` (`CHECK (code IN ('SALESMAN','FACTORY_ADMIN','PRODUCTION_SUPERVISOR','ACCOUNTANT_AUDITOR','OWNER'))`), `name VARCHAR(80) NOT NULL`, `description TEXT`, `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

### `iam.users`
*Purpose:* Authenticated actor accounts linked to roles and audit logs.
- **PK:** `id BIGINT GENERATED ALWAYS AS IDENTITY`
- **FK:** `role_id BIGINT NOT NULL REFERENCES iam.roles(id) ON DELETE RESTRICT`
- **Columns:** `username VARCHAR(80) NOT NULL UNIQUE`, `phone VARCHAR(20) UNIQUE`, `full_name VARCHAR(120) NOT NULL`, `password_hash VARCHAR(255) NOT NULL`, `is_active BOOLEAN NOT NULL DEFAULT TRUE`, `last_login_at TIMESTAMPTZ`, `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **Indexes:** `idx_users_role_active (role_id, is_active)`

---

## 3. `sales` Schema Tables

| Table | Business Purpose | Key Columns & Types | PK / FK / Unique / Check |
| --- | --- | --- | --- |
| **`sales.salesman_profiles`** | Salesman employee code & route metadata. | `id BIGINT`, `user_id BIGINT`, `employee_code VARCHAR(32)`, `territory VARCHAR(80)`, `is_active BOOLEAN DEFAULT TRUE` | PK `id`; FK `user_id -> iam.users(id) ON DELETE RESTRICT` (`UNIQUE`); `UNIQUE(employee_code)` |
| **`sales.customers`** | Retailers & distributors (Place of Supply & GSTIN). | `id BIGINT`, `code VARCHAR(32)`, `name VARCHAR(160)`, `customer_type VARCHAR(20)`, `gstin VARCHAR(15) NULL`, `state_name VARCHAR(80)`, `state_code CHAR(2)`, `assigned_salesman_id BIGINT NULL`, `credit_days INT DEFAULT 30`, `is_active BOOLEAN DEFAULT TRUE` | PK `id`; `UNIQUE(code)`; FK `assigned_salesman_id -> iam.users(id) ON DELETE RESTRICT`; `CHECK (customer_type IN ('RETAILER','DISTRIBUTOR'))`, `CHECK (credit_days >= 0)` |
| **`sales.customer_addresses`** | Billing & shipping addresses per customer. | `id BIGINT`, `customer_id BIGINT`, `address_type VARCHAR(16)`, `line1 VARCHAR(200)`, `line2 VARCHAR(200)`, `city VARCHAR(80)`, `state_name VARCHAR(80)`, `state_code CHAR(2)`, `pincode CHAR(6)`, `is_default BOOLEAN DEFAULT FALSE` | PK `id`; FK `customer_id -> sales.customers(id) ON DELETE RESTRICT`; `CHECK (address_type IN ('BILLING','SHIPPING'))`; Partial Unique `(customer_id, address_type) WHERE is_default` |
| **`sales.products`** | Product family / snack line sharing tax & base cooking identity (`Murukku`). | `id BIGINT`, `product_code VARCHAR(32)`, `name VARCHAR(120)`, `category VARCHAR(60)`, `hsn_code VARCHAR(12)`, `gst_rate_bps INT`, `is_active BOOLEAN DEFAULT TRUE` | PK `id`; `UNIQUE(product_code)`; `CHECK (gst_rate_bps >= 0 AND gst_rate_bps <= 2800)` |
| **`sales.pack_sizes`** | Concrete sellable SKU variant (`Murukku 200 g`, `Murukku 500 g`). | `id BIGINT`, `product_id BIGINT`, `sku_code VARCHAR(40)`, `display_name VARCHAR(140)`, `pack_weight_g INT`, `packets_per_carton INT`, `base_selling_price_paisa BIGINT`, `is_active BOOLEAN DEFAULT TRUE` | PK `id`; `UNIQUE(sku_code)`; FK `product_id -> sales.products(id) ON DELETE RESTRICT`; `CHECK (pack_weight_g > 0 AND packets_per_carton > 0 AND base_selling_price_paisa >= 0)` |
| **`sales.price_lists`** | Standard or customer-specific price schedules. | `id BIGINT`, `name VARCHAR(100)`, `is_default BOOLEAN DEFAULT FALSE`, `customer_id BIGINT NULL`, `effective_from DATE`, `effective_to DATE NULL`, `is_active BOOLEAN DEFAULT TRUE` | PK `id`; FK `customer_id -> sales.customers(id) ON DELETE RESTRICT`; Partial Unique `(is_default) WHERE is_default AND is_active`; `CHECK (effective_to IS NULL OR effective_to >= effective_from)` |
| **`sales.price_list_items`** | Price per `pack_size` in a `price_list`. | `id BIGINT`, `price_list_id BIGINT`, `pack_size_id BIGINT`, `unit_price_paisa BIGINT`, `min_qty INT DEFAULT 1` | PK `id`; FKs to `price_lists`, `pack_sizes` (`ON DELETE RESTRICT`); `UNIQUE(price_list_id, pack_size_id, min_qty)`; `CHECK (unit_price_paisa >= 0 AND min_qty >= 1)` |
| **`sales.sales_orders`** | Field salesman demand orders with idempotency protection. | `id BIGINT`, `order_number VARCHAR(32)`, `client_order_id UUID`, `salesman_id BIGINT`, `customer_id BIGINT`, `billing_state_code CHAR(2)`, `order_date DATE`, `status VARCHAR(28)`, `has_shortage BOOLEAN DEFAULT FALSE`, `notes TEXT`, `submitted_at TIMESTAMPTZ`, `approved_by BIGINT NULL`, `approved_at TIMESTAMPTZ NULL`, `created_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ` | PK `id`; `UNIQUE(order_number)`; **`UNIQUE(salesman_id, client_order_id)`**; FKs to `users`, `customers`; `CHECK (status IN ('DRAFT','SUBMITTED','UNDER_REVIEW','CORRECTION_REQUESTED','APPROVED','REJECTED','INVOICED','PARTIALLY_DISPATCHED','DISPATCHED','CANCELLED'))` |
| **`sales.sales_order_items`** | Ordered SKU lines with frozen price snapshots. | `id BIGINT`, `sales_order_id BIGINT`, `pack_size_id BIGINT`, `ordered_qty_pkts INT`, `approved_qty_pkts INT NULL`, `unit_price_paisa BIGINT`, `line_taxable_paisa BIGINT` | PK `id`; FKs to `sales_orders`, `pack_sizes`; `UNIQUE(sales_order_id, pack_size_id)`; `CHECK (ordered_qty_pkts > 0 AND (approved_qty_pkts IS NULL OR approved_qty_pkts >= 0))` |
| **`sales.sales_order_status_history`** | Append-only order transition timeline. | `id BIGINT`, `sales_order_id BIGINT`, `from_status VARCHAR(28) NULL`, `to_status VARCHAR(28)`, `changed_by BIGINT`, `reason TEXT`, `changed_at TIMESTAMPTZ DEFAULT NOW()` | PK `id`; FKs to `sales_orders`, `users` |
| **`sales.sales_order_approvals`** | Auditable record of Admin stock verification, shortages, or rejections. | `id BIGINT`, `sales_order_id BIGINT`, `reviewed_by BIGINT`, `decision VARCHAR(28)`, `ordered_total_pkts INT`, `available_total_pkts INT`, `shortage_pkts INT`, `stock_snapshot JSONB`, `remarks TEXT`, `decided_at TIMESTAMPTZ DEFAULT NOW()` | PK `id`; FKs to `sales_orders`, `users`; `CHECK (decision IN ('APPROVED','REJECTED','CORRECTION_REQUESTED','HELD_SHORTAGE'))`, `CHECK (shortage_pkts >= 0)` |

---

## 4. `purchasing` Schema Tables

| Table | Business Purpose | Key Columns & Types | PK / FK / Unique / Check |
| --- | --- | --- | --- |
| **`purchasing.suppliers`** | Raw & packaging vendor master. | `id BIGINT`, `code VARCHAR(32)`, `name VARCHAR(160)`, `gstin VARCHAR(15) NULL`, `state_code CHAR(2)`, `phone VARCHAR(20)`, `address TEXT`, `is_active BOOLEAN DEFAULT TRUE` | PK `id`; `UNIQUE(code)` |
| **`purchasing.purchase_orders`** | Optional formal supplier PO (`Draft -> Approved -> Received -> Closed`). | `id BIGINT`, `po_number VARCHAR(32)`, `supplier_id BIGINT`, `order_date DATE`, `status VARCHAR(24)`, `total_paisa BIGINT DEFAULT 0`, `created_by BIGINT`, `approved_by BIGINT NULL` | PK `id`; `UNIQUE(po_number)`; FKs to `suppliers`, `users`; `CHECK (status IN ('DRAFT','APPROVED','PARTIALLY_RECEIVED','RECEIVED','CLOSED','CANCELLED'))` |
| **`purchasing.purchase_order_items`** | Ordered material lines on a PO. | `id BIGINT`, `purchase_order_id BIGINT`, `material_id BIGINT`, `ordered_qty_base NUMERIC(18,3)`, `received_qty_base NUMERIC(18,3) DEFAULT 0`, `entered_uom VARCHAR(16)`, `unit_rate_paisa BIGINT` | PK `id`; FKs to `purchase_orders`, `materials`; `CHECK (ordered_qty_base > 0 AND received_qty_base >= 0)` |
| **`purchasing.purchase_receipts`** | Supplier Goods/Material Receipt (`PUR-001` — PO-linked or direct). | `id BIGINT`, `receipt_number VARCHAR(32)`, `purchase_order_id BIGINT NULL`, `supplier_id BIGINT`, `supplier_bill_ref VARCHAR(64)`, `receipt_date DATE`, `status VARCHAR(20)`, `subtotal_paisa BIGINT`, `input_gst_paisa BIGINT DEFAULT 0`, `total_paisa BIGINT`, `received_by BIGINT` | PK `id`; `UNIQUE(receipt_number)`; FKs to `purchase_orders`, `suppliers`, `users`; `CHECK (status IN ('DRAFT','RECEIVED','CLOSED'))` |
| **`purchasing.purchase_receipt_items`** | Received material qty & cost rate driving `PURCHASE_IN` + `CostLot`. | `id BIGINT`, `purchase_receipt_id BIGINT`, `material_id BIGINT`, `entered_qty NUMERIC(18,3)`, `entered_uom VARCHAR(16)`, `received_qty_base NUMERIC(18,3)`, `entered_unit_rate_paisa BIGINT`, `unit_cost_paisa_per_base NUMERIC(18,6)`, `line_total_paisa BIGINT` | PK `id`; FKs to `purchase_receipts`, `materials`; `CHECK (received_qty_base > 0 AND entered_unit_rate_paisa >= 0)` |

---

## 5. `production` & `costing` Schema Tables

| Table | Business Purpose | Key Columns & Types | PK / FK / Unique / Check |
| --- | --- | --- | --- |
| **`production.materials`** | Unified Raw Materials & Packaging Materials. | `id BIGINT`, `code VARCHAR(32)`, `name VARCHAR(120)`, `material_category VARCHAR(24)`, `unit_dimension VARCHAR(16)`, `base_uom VARCHAR(16)`, `display_uom VARCHAR(16)`, `reorder_level_base NUMERIC(18,3) DEFAULT 0`, `is_active BOOLEAN DEFAULT TRUE` | PK `id`; `UNIQUE(code)`; `CHECK (material_category IN ('RAW_MATERIAL','PACKAGING_MATERIAL'))`, `CHECK (unit_dimension IN ('MASS','VOLUME','COUNT'))` |
| **`production.unit_conversions`** | Exact rational UOM conversions within same dimension. | `id BIGINT`, `from_uom VARCHAR(16)`, `to_base_uom VARCHAR(16)`, `unit_dimension VARCHAR(16)`, `multiplier NUMERIC(18,6)` | PK `id`; `UNIQUE(from_uom, to_base_uom)`; `CHECK (multiplier > 0)` |
| **`production.recipe_templates`** | Shared bulk cooking formula (`Murukku Base Mix`: 40 kg cooked bulk). | `id BIGINT`, `code VARCHAR(32)`, `name VARCHAR(120)`, `product_id BIGINT`, `base_yield_weight_g NUMERIC(18,3)`, `is_active BOOLEAN DEFAULT TRUE` | PK `id`; `UNIQUE(code)`; FK `product_id -> sales.products(id)` |
| **`production.bom_headers`** | BOM container per sellable `pack_size`. | `id BIGINT`, `pack_size_id BIGINT`, `active_version_id BIGINT NULL`, `created_at TIMESTAMPTZ` | PK `id`; `UNIQUE(pack_size_id)`; FK `pack_size_id -> sales.pack_sizes(id)` |
| **`production.bom_versions`** | Immutable numbered recipe snapshots. | `id BIGINT`, `bom_header_id BIGINT`, `recipe_template_id BIGINT NULL`, `version_no INT`, `expected_yield_pkts INT`, `status VARCHAR(20)`, `effective_from DATE`, `created_by BIGINT` | PK `id`; `UNIQUE(bom_header_id, version_no)`; FKs to `bom_headers`, `recipe_templates`, `users`; `CHECK (expected_yield_pkts > 0 AND status IN ('DRAFT','ACTIVE','SUPERSEDED'))` |
| **`production.bom_components`** | Standard raw/packaging quantity per 1 batch of a `BomVersion`. | `id BIGINT`, `bom_version_id BIGINT`, `material_id BIGINT`, `component_role VARCHAR(20)`, `std_qty_base NUMERIC(18,3)`, `display_qty NUMERIC(18,3)`, `display_uom VARCHAR(16)` | PK `id`; `UNIQUE(bom_version_id, material_id)`; FKs to `bom_versions`, `materials`; `CHECK (std_qty_base > 0 AND component_role IN ('COOKING_RAW','PACKAGING'))` |
| **`production.production_runs`** | Factory batch execution header (`PRD-001`). | `id BIGINT`, `run_number VARCHAR(32)`, `pack_size_id BIGINT`, `bom_version_id BIGINT`, `batch_multiplier NUMERIC(10,4)`, `expected_output_pkts INT`, `actual_good_output_pkts INT DEFAULT 0`, `status VARCHAR(20)`, `run_date DATE`, `started_at TIMESTAMPTZ`, `completed_at TIMESTAMPTZ`, `posted_at TIMESTAMPTZ`, `supervisor_id BIGINT` | PK `id`; `UNIQUE(run_number)`; FKs to `pack_sizes`, `bom_versions`, `users`; `CHECK (batch_multiplier > 0 AND actual_good_output_pkts >= 0 AND status IN ('DRAFT','PLANNED','IN_PROGRESS','COMPLETED','POSTED','CANCELLED'))` |
| **`production.production_material_issues`** | Planned vs actual raw/packaging usage & absorbed FIFO cost. | `id BIGINT`, `production_run_id BIGINT`, `material_id BIGINT`, `issue_phase VARCHAR(20)`, `planned_qty_base NUMERIC(18,3)`, `actual_good_used_base NUMERIC(18,3)`, `damaged_qty_base NUMERIC(18,3) DEFAULT 0`, `returned_qty_base NUMERIC(18,3) DEFAULT 0`, `cost_absorbed_paisa BIGINT DEFAULT 0` | PK `id`; `UNIQUE(production_run_id, material_id, issue_phase)`; FKs to `production_runs`, `materials`; `CHECK (actual_good_used_base >= 0 AND damaged_qty_base >= 0)` |
| **`production.production_outputs`** | Good packet output batches (supports partial shift outputs + batch/expiry FEFO). | `id BIGINT`, `production_run_id BIGINT`, `pack_size_id BIGINT`, `good_qty_pkts INT`, `batch_code VARCHAR(40)`, `expiry_date DATE NULL`, `recorded_by BIGINT`, `recorded_at TIMESTAMPTZ` | PK `id`; FKs to `production_runs`, `pack_sizes`, `users`; `CHECK (good_qty_pkts > 0)` |
| **`production.production_wastages`** | Explicit damaged packaging & process scrap records (`6` pouches damaged). | `id BIGINT`, `production_run_id BIGINT`, `material_id BIGINT NULL`, `wastage_type VARCHAR(28)`, `qty_base NUMERIC(18,3)`, `cost_impact_paisa BIGINT DEFAULT 0`, `reason TEXT`, `recorded_by BIGINT` | PK `id`; FKs to `production_runs`, `materials`, `users`; `CHECK (wastage_type IN ('DAMAGED_PACKAGING','COOKING_SCRAP','BURNT_BATCH','SPILLAGE'))` |
| **`production.production_variances`** | Computed planned vs actual variance lines & tolerance flags. | `id BIGINT`, `production_run_id BIGINT`, `variance_scope VARCHAR(24)`, `material_id BIGINT NULL`, `planned_qty_base NUMERIC(18,3)`, `actual_qty_base NUMERIC(18,3)`, `variance_pct NUMERIC(8,2)`, `tolerance_pct NUMERIC(5,2)`, `is_flagged BOOLEAN` | PK `id`; FKs to `production_runs`, `materials`; `CHECK (variance_scope IN ('YIELD','RAW_CONSUMPTION','PACKAGING_CONSUMPTION'))` |
| **`costing.production_overheads`** | Direct run (`Labour`, `Gas/Power`) or monthly shared overhead entries. | `id BIGINT`, `production_run_id BIGINT NULL`, `period_month CHAR(7)`, `overhead_type VARCHAR(24)`, `allocation_scope VARCHAR(20)`, `amount_paisa BIGINT`, `notes TEXT`, `recorded_by BIGINT` | PK `id`; FKs to `production_runs`, `users`; `CHECK (amount_paisa >= 0 AND allocation_scope IN ('DIRECT_RUN','MONTHLY_POOL'))` |
| **`costing.production_cost_summaries`** | Audited cost per good packet & selling margin per run. | `id BIGINT`, `production_run_id BIGINT`, `valuation_method VARCHAR(24)`, `raw_material_cost_paisa BIGINT`, `packaging_cost_paisa BIGINT`, `direct_overhead_paisa BIGINT`, `allocated_overhead_paisa BIGINT`, `total_cost_paisa BIGINT`, `good_packets INT`, `cost_per_packet_paisa BIGINT NULL`, `selling_price_snapshot_paisa BIGINT`, `gross_margin_paisa BIGINT NULL`, `computed_at TIMESTAMPTZ` | PK `id`; `UNIQUE(production_run_id)`; FK `production_run_id -> production.production_runs(id)`; `CHECK (total_cost_paisa >= 0 AND good_packets >= 0)` |

---

## 6. `inventory`, `billing`, `finance` & `audit` Schema Tables

*(Detailed column specifications appear in [inventory-schema.md](file:///d:/mac/ota/docs/phase3/inventory-schema.md) and [finance-and-gst-schema.md](file:///d:/mac/ota/docs/phase3/finance-and-gst-schema.md).)*

- **`inventory`:** `opening_balances`, `inventory_balances`, `cost_lots`, `cost_lot_consumptions`, `stock_adjustments`, `inventory_movements`.
- **`billing`:** `fiscal_sequences`, `invoices`, `invoice_items`, `invoice_tax_components`, `credit_notes`, `credit_note_items`, `dispatches`, `dispatch_items`.
- **`finance`:** `payments`, `payment_allocations`, `customer_receivables`.
- **`audit`:**
  - **`audit.variance_alerts`:** `id BIGINT PK`, `production_run_id BIGINT FK`, `production_variance_id BIGINT FK`, `alert_type VARCHAR(24)`, `message TEXT`, `status VARCHAR(16)` (`OPEN|ACKNOWLEDGED`), `acknowledged_by BIGINT NULL`, `acknowledged_at TIMESTAMPTZ NULL`, `created_at TIMESTAMPTZ`.
  - **`audit.audit_logs`:** `id BIGINT PK`, `actor_user_id BIGINT FK`, `actor_role VARCHAR(32) NOT NULL`, `occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`, `action VARCHAR(32) NOT NULL`, `entity_schema VARCHAR(32) NOT NULL`, `entity_table VARCHAR(64) NOT NULL`, `entity_id BIGINT NOT NULL`, `before_state JSONB NULL`, `after_state JSONB NULL`, `reason TEXT NULL`.
