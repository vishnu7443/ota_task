# Entity Relationships Specification

Every domain entity is documented with purpose, conceptual attributes, relationships, cardinalities, lifecycle, responsible module, and concrete factory examples.

---

## 1. Identity & Governance Entities

| Entity | Purpose | Important Conceptual Attributes | Responsible Module | Lifecycle |
| --- | --- | --- | --- | --- |
| **`CompanyProfile`** | Stores factory statutory & policy defaults. | `id`, `legal_name`, `gstin`, `state_name`, `state_code` (`33`), `variance_tolerance_pct` (`3.0`), `valuation_method` (`FIFO` \| `WAVG`), `active_fy_code` | `IAM` | Singleton config (audited edits) |
| **`Role`** | Defines access capability profile. | `id`, `code` (`SALESMAN`, `FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR`, `ACCOUNTANT_AUDITOR`, `OWNER`), `name`, `permissions_set` | `IAM` | Seeded Reference |
| **`User`** | Authenticated operator account. | `id`, `role_id` (FK), `full_name`, `username_or_phone`, `password_hash`, `is_active`, `created_at` | `IAM` | `Active` <-> `Inactive` |

- **Relationships:** `Role (1) ─── (N) User`. Every operational document carries `created_by_user_id` (`User (1) ─── (N) Docs`).

---

## 2. Commercial & Sales Master Entities

| Entity | Purpose | Important Conceptual Attributes | Responsible Module | Lifecycle |
| --- | --- | --- | --- | --- |
| **`Customer`** | Retailer or distributor buyer. | `id`, `code`, `name`, `customer_type` (`RETAILER` \| `DISTRIBUTOR`), `state_name`, `state_code`, `gstin` (nullable), `address`, `assigned_salesman_id` (FK->User, nullable), `credit_days`, `is_active` | `SalesCatalog` | `Active` <-> `Inactive` |
| **`Product`** | Finished sellable snack SKU. | `id`, `sku_code`, `name` (`Murukku 200 g`), `category`, `hsn_code`, `gst_rate_bps` (`500` = 5%), `pack_weight_g` (`200`), `packets_per_carton` (`20`), `base_selling_price_paisa` (`5000`), `is_active` | `SalesCatalog` | `Active` <-> `Discontinued` |
| **`PriceList`** | Named pricing schedule (Standard or Customer Tier). | `id`, `name`, `is_default`, `customer_id` (nullable FK for customer-specific list), `effective_from`, `effective_to`, `is_active` | `SalesCatalog` | `Active` -> `Expired` |
| **`PriceListItem`** | Rate per SKU within a PriceList. | `id`, `price_list_id` (FK), `product_id` (FK), `unit_price_paisa` (`5000`), `min_qty` | `SalesCatalog` | Versioned by `PriceList` |

- **Concrete Factory Example:** `Retailer A` (`state_code = 33`, Tamil Nadu) and `Distributor B` (`state_code = 29`, Karnataka) both buy `Murukku 200 g` (`base_selling_price_paisa = 5000`, `gst_rate_bps = 500`). When `PriceList` updates from `₹50` to `₹55`, past `SalesOrderItem` and `InvoiceItem` rows retain `5000 paise` as frozen snapshots.
- **Relationships:**
  - `User [Salesman] (1) ─── (0..N) Customer` (assigned field salesman)
  - `PriceList (1) ─── (N) PriceListItem`
  - `Product (1) ─── (0..N) PriceListItem`

---

## 3. Production, Material & BOM Entities

| Entity | Purpose | Important Conceptual Attributes | Responsible Module | Lifecycle |
| --- | --- | --- | --- | --- |
| **`Material`** | Raw ingredient or packaging supply item. | `id`, `code`, `name`, `material_category` (`RAW_MATERIAL` \| `PACKAGING_MATERIAL`), `unit_dimension` (`MASS` \| `VOLUME` \| `COUNT`), `base_uom` (`g`, `ml`, `piece`), `display_uom` (`kg`, `L`, `piece`), `reorder_level_base`, `is_active` | `ProductionAndBom` | `Active` <-> `Inactive` |
| **`UnitConversion`** | Authoritative conversion rule between UOMs in same dimension. | `id`, `from_uom`, `to_base_uom`, `unit_dimension`, `multiplier_numerator`, `multiplier_denominator` | `ProductionAndBom` | Seeded Reference |
| **`RecipeTemplate`** | Shared base cooking formula across pack sizes. | `id`, `code`, `name` (`Murukku Base Mix`), `base_yield_weight_g` (`40000`), `is_active` | `ProductionAndBom` | `Active` <-> `Archived` |
| **`BillOfMaterials`** | Product-level BOM identity for one finished SKU. | `id`, `product_id` (FK, unique 1:1 with Product), `active_version_id` (FK) | `ProductionAndBom` | `Active` |
| **`BomVersion`** | Immutable versioned recipe snapshot for batch runs. | `id`, `bom_id` (FK), `recipe_template_id` (nullable FK), `version_no` (`1, 2...`), `expected_yield_packets` (`200`), `effective_from`, `status` (`DRAFT` \| `ACTIVE` \| `SUPERSEDED`), `created_by` | `ProductionAndBom` | `Draft` -> `Active` -> `Superseded` |
| **`BomItem`** | Standard material quantity per 1 batch of a `BomVersion`. | `id`, `bom_version_id` (FK), `material_id` (FK), `input_role` (`COOKING_RAW` \| `PACKAGING`), `std_qty_base`, `display_qty`, `display_uom` | `ProductionAndBom` | Immutable once `BomVersion` active |

- **Concrete Factory Example (Shared Recipe for `200 g` & `500 g`):** `RecipeTemplate` *"Murukku Base Mix"* defines `40 kg` flour, `10 L` oil, `1.2 kg` spice for `40,000 g` cooked snack. `Murukku 200 g` (`BomVersion v1`, `expected_yield = 200 pkts`) uses `1×` recipe + `200` `200 g pouches` + `10` `cartons`. Adding `Murukku 500 g` later links a new `BillOfMaterials` (`expected_yield = 80 pkts`) to the **exact same `RecipeTemplate`** plus `80` `500 g pouches`!
- **Relationships:**
  - `Product (1) ─── (0..1) BillOfMaterials`
  - `BillOfMaterials (1) ─── (1..N) BomVersion`
  - `RecipeTemplate (0..1) ─── (0..N) BomVersion`
  - `BomVersion (1) ─── (1..N) BomItem`
  - `Material (1) ─── (0..N) BomItem`

---

## 4. Purchasing Entities

| Entity | Purpose | Important Conceptual Attributes | Responsible Module | Lifecycle |
| --- | --- | --- | --- | --- |
| **`Supplier`** | Vendor supplying raw/packaging inputs. | `id`, `code`, `name`, `state_code`, `gstin`, `phone`, `is_active` | `Purchasing` | `Active` <-> `Inactive` |
| **`PurchaseOrder`** | Optional formal supplier procurement order. | `id`, `po_number`, `supplier_id` (FK), `order_date`, `status` (`DRAFT` \| `APPROVED` \| `PARTIALLY_RECEIVED` \| `RECEIVED` \| `CLOSED` \| `CANCELLED`), `total_paisa` | `Purchasing` | State Machine D |
| **`PurchaseOrderItem`** | Line item on a PurchaseOrder. | `id`, `purchase_order_id` (FK), `material_id` (FK), `ordered_qty_base`, `received_qty_base`, `unit_rate_paisa` | `Purchasing` | Follows PO |
| **`PurchaseReceipt`** | Recorded material intake voucher (`PUR-001`). | `id`, `receipt_number`, `purchase_order_id` (nullable FK), `supplier_id` (FK), `supplier_bill_ref`, `receipt_date`, `status` (`DRAFT` \| `RECEIVED` \| `CLOSED`), `subtotal_paisa`, `input_gst_paisa`, `total_paisa`, `created_by` | `Purchasing` | Direct or PO-linked receipt |
| **`PurchaseReceiptItem`** | Material qty & unit cost received (`60 kg` Flour @ `₹45`). | `id`, `purchase_receipt_id` (FK), `material_id` (FK), `received_qty_base`, `entered_qty`, `entered_uom`, `unit_cost_paisa`, `line_total_paisa` | `Purchasing` | Immutable once `RECEIVED` |

- **Relationships:** `Supplier (1) ─── (N) PurchaseOrder (1) ─── (0..N) PurchaseReceipt`; `PurchaseReceipt (1) ─── (1..N) PurchaseReceiptItem`; `Material (1) ─── (N) PurchaseReceiptItem`.

---

## 5. Production Run & Costing Entities

| Entity | Purpose | Important Conceptual Attributes | Responsible Module | Lifecycle |
| --- | --- | --- | --- | --- |
| **`ProductionRun`** | Factory batch execution (`PRD-001`). | `id`, `run_number`, `product_id` (FK), `bom_version_id` (FK), `batch_multiplier`, `expected_output_qty` (`200`), `actual_good_output_qty` (`188`), `process_scrap_qty`, `yield_variance_pct` (`-6.00`), `yield_flagged` (`true`), `status` (`DRAFT` \| `PLANNED` \| `IN_PROGRESS` \| `COMPLETED` \| `POSTED` \| `CANCELLED`), `started_at`, `completed_at`, `supervisor_id` | `ProductionAndBom` | State Machine C |
| **`ProductionMaterialIssue`** | Planned vs actual raw & packaging usage per run. | `id`, `production_run_id` (FK), `material_id` (FK), `issue_phase` (`RAW_ISSUE` \| `PACKAGING_PACK`), `planned_qty_base`, `actual_used_qty_base`, `damaged_qty_base` (`6` pouches), `consumption_variance_pct`, `is_flagged`, `cost_absorbed_paisa` | `ProductionAndBom` | Locked upon `COMPLETED` |
| **`ProductionOverhead`** | Direct run or monthly pool overhead cost. | `id`, `production_run_id` (nullable FK), `period_month` (`2026-11`), `overhead_type` (`LABOUR` \| `GAS_POWER` \| `OTHER_MONTHLY`), `allocation_scope` (`DIRECT_RUN` \| `MONTHLY_POOL`), `amount_paisa`, `notes` | `Costing` | Immutable once closed/posted |
| **`ProductionCostSummary`** | Audited unit cost & margin snapshot for a run. | `id`, `production_run_id` (FK, unique 1:1), `valuation_method`, `raw_material_cost_paisa`, `packaging_cost_paisa`, `direct_overhead_paisa`, `allocated_overhead_paisa`, `total_cost_paisa`, `good_packets`, `cost_per_packet_paisa`, `selling_price_paisa`, `gross_margin_paisa`, `computed_at` | `Costing` | Recomputed only via logged overhead/correction |

- **Concrete Factory Example (`PRD-001`):** Pins `Murukku 200 g` `BomVersion v1` (`200` expected). Issues `40 kg` flour, `10.5 L` oil (`+5.0%` flagged), `1.2 kg` spice (`RAW_ISSUE`), then completes with `188` good packets (`-6.0%` yield flagged), `188` good + `6` damaged pouches (`PACKAGING_PACK`), `9` cartons (`PACKAGING_PACK`). `ProductionOverhead` adds Labour (`₹1,200`) + Gas/Power (`₹600`) -> `ProductionCostSummary` computes `₹5,810.00 / 188 = ₹30.90/packet` (FIFO).

---

## 6. Sales Order, Billing, Dispatch & Payment Entities

| Entity | Purpose | Important Conceptual Attributes | Responsible Module | Lifecycle |
| --- | --- | --- | --- | --- |
| **`SalesOrder`** | Field demand order (`ORD-001`, `ORD-002`). | `id`, `order_number`, `client_order_id` (`UUID`, unique per salesman), `salesman_id` (FK->User), `customer_id` (FK), `order_date`, `status` (`DRAFT` \| `SUBMITTED` \| `UNDER_REVIEW` \| `CORRECTION_REQUESTED` \| `APPROVED` \| `REJECTED` \| `INVOICED` \| `PARTIALLY_DISPATCHED` \| `DISPATCHED` \| `CANCELLED`), `shortage_flag`, `notes`, `approved_by`, `approved_at` | `Orders` | State Machine A |
| **`SalesOrderItem`** | SKU line inside a `SalesOrder`. | `id`, `sales_order_id` (FK), `product_id` (FK), `ordered_qty_pkts`, `approved_qty_pkts`, `unit_price_paisa`, `line_taxable_paisa` | `Orders` | Locked on Approval |
| **`FiscalSequence`** | Gap-free FY invoice/CN number counter. | `id`, `doc_type` (`INVOICE` \| `CREDIT_NOTE`), `financial_year` (`2026-27`), `next_seq_no` | `Billing` | Monotonic per FY |
| **`Invoice`** | Statutory GST tax invoice (`INV/2026-27/0001`). | `id`, `invoice_number`, `financial_year`, `sales_order_id` (FK), `customer_id` (FK), `seller_gstin`, `seller_state_code`, `buyer_gstin`, `place_of_supply_state_code`, `supply_type` (`INTRA_STATE` \| `INTER_STATE`), `invoice_date`, `doc_status` (`DRAFT` \| `ISSUED` \| `CANCELLED_BY_CN`), `payment_status` (`UNPAID` \| `PARTIALLY_PAID` \| `PAID` \| `CREDITED`), `dispatch_status` (`PENDING` \| `PARTIAL` \| `DISPATCHED`), `taxable_total_paisa`, `cgst_total_paisa`, `sgst_total_paisa`, `igst_total_paisa`, `grand_total_paisa` | `Billing` | State Machine B |
| **`InvoiceItem`** | Frozen line item & HSN tax breakdown on invoice. | `id`, `invoice_id` (FK), `product_id` (FK), `hsn_code`, `qty_pkts`, `unit_price_paisa`, `taxable_paisa`, `gst_rate_bps`, `cgst_paisa`, `sgst_paisa`, `igst_paisa`, `line_total_paisa` | `Billing` | Immutable once `ISSUED` |
| **`InvoiceTaxComponent`** | GSTR-1/3B-ready tax bucket summary per invoice. | `id`, `invoice_id` (FK), `hsn_code`, `tax_type` (`CGST` \| `SGST` \| `IGST`), `rate_bps`, `taxable_base_paisa`, `tax_amount_paisa` | `Billing` | Immutable once `ISSUED` |
| **`CreditNote`** | Compensating GST cancellation/return document. | `id`, `cn_number`, `financial_year`, `original_invoice_id` (FK), `issue_date`, `reason`, `status` (`DRAFT` \| `ISSUED`), `taxable_reversed_paisa`, `cgst_reversed_paisa`, `sgst_reversed_paisa`, `igst_reversed_paisa`, `total_reversed_paisa`, `has_physical_return` | `Billing` | `Draft` -> `Issued` |
| **`CreditNoteItem`** | Line-level reversal for a Credit Note. | `id`, `credit_note_id` (FK), `invoice_item_id` (FK), `product_id` (FK), `returned_qty_pkts`, `return_disposition` (`NONE` \| `RESTOCK_SELLABLE` \| `SCRAP`), `reversed_total_paisa` | `Billing` | Immutable once `ISSUED` |
| **`Dispatch`** | Physical goods dispatch note (`DSP-001`). | `id`, `dispatch_number`, `invoice_id` (FK), `sales_order_id` (FK), `dispatch_date`, `vehicle_or_lr_ref`, `dispatched_by`, `status` (`RECORDED`) | `Billing` | Immutable once posted |
| **`DispatchItem`** | SKU quantity shipped on a Dispatch Note. | `id`, `dispatch_id` (FK), `invoice_item_id` (FK), `product_id` (FK), `dispatched_qty_pkts` | `Billing` | Immutable |
| **`Payment`** | Money received from a customer (`PMT-001`: `₹4,000`). | `id`, `payment_number`, `customer_id` (FK), `payment_date`, `amount_paisa`, `payment_mode` (`CASH` \| `UPI` \| `NEFT` \| `CHEQUE`), `reference_no`, `idempotency_key`, `status` (`RECORDED` \| `PARTIALLY_ALLOCATED` \| `ALLOCATED` \| `REVERSED`), `reversal_reason` | `Payments` | State Machine E |
| **`PaymentAllocation`** | Links a Payment to one or more Invoices. | `id`, `payment_id` (FK), `invoice_id` (FK), `allocated_paisa`, `allocated_at` | `Payments` | Immutable (offset on reversal) |
| **`CustomerReceivable`** | Invoice-level open AR tracking for fast ageing. | `id`, `customer_id` (FK), `invoice_id` (FK, unique 1:1), `invoice_date`, `due_date`, `original_paisa`, `credited_paisa`, `paid_paisa`, `outstanding_paisa` | `Payments` | Updated atomically on `INV`/`CN`/`PMT` |

---

## 7. Inventory Ledger & Audit Entities

| Entity | Purpose | Important Conceptual Attributes | Responsible Module | Lifecycle |
| --- | --- | --- | --- | --- |
| **`InventoryBalance`** | Concurrency-locked current balance & soft reservation. | `id`, `item_type` (`MATERIAL` \| `PRODUCT`), `item_id`, `on_hand_qty_base`, `reserved_qty_base`, `updated_at` | `Inventory` | Continuous (Strictly reconcilable to `InventoryMovement`) |
| **`InventoryMovement`** | Immutable append-only Stock Ledger entry. | `id`, `item_type`, `item_id`, `movement_type`, `signed_qty_base`, `unit_cost_paisa`, `total_cost_paisa`, `source_doc_type`, `source_doc_id`, `cost_lot_id` (nullable FK), `occurred_at`, `created_by` | `Inventory` | Append-Only (Never mutated/deleted) |
| **`CostLot`** | Receipt cost layer for FIFO & optional FEFO batches. | `id`, `item_type`, `item_id`, `source_doc_type`, `source_doc_id`, `batch_code`, `expiry_date` (nullable), `original_qty_base`, `remaining_qty_base`, `unit_cost_paisa`, `received_at` | `Inventory` | `Open` (`remaining > 0`) -> `Depleted` (`remaining = 0`) |
| **`StockAdjustment`** | Logged correction for physical count / damage outside run. | `id`, `adjustment_number`, `item_type`, `item_id`, `delta_qty_base`, `reason`, `status` (`DRAFT` \| `POSTED`), `requested_by`, `approved_by` | `Inventory` | `Draft` -> `Posted` |
| **`VarianceAlert`** | Flagged variance > tolerance (`3%`) for Owner/Supervisor. | `id`, `production_run_id` (FK), `alert_type` (`YIELD` \| `CONSUMPTION` \| `PACKAGING_DAMAGE`), `item_name`, `variance_pct`, `tolerance_pct`, `status` (`OPEN` \| `ACKNOWLEDGED`), `acknowledged_by` | `ReportingAndAudit` | `Open` -> `Acknowledged` |
| **`AuditLog`** | Immutable change history across sensitive actions. | `id`, `actor_user_id`, `actor_role`, `occurred_at`, `action`, `entity_type`, `entity_id`, `before_json`, `after_json`, `reason` | `ReportingAndAudit` | Append-Only |
