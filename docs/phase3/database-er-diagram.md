# Physical PostgreSQL Entity-Relationship Diagrams

Matches the exact physical schemas, table names, PostgreSQL data types, primary/foreign keys, and cardinalities defined in [complete-schema.md](file:///d:/mac/ota/docs/phase3/complete-schema.md).

---

## 1. IAM, Sales Masters & Orders (`iam` + `sales` Schemas)

```mermaid
erDiagram
    IAM_COMPANY_PROFILES {
        bigint id PK
        varchar legal_name
        varchar gstin
        char state_code
        numeric variance_tolerance_pct
        varchar valuation_method
        boolean is_singleton
    }
    IAM_ROLES {
        bigint id PK
        varchar code
        varchar name
    }
    IAM_USERS {
        bigint id PK
        bigint role_id FK
        varchar username
        varchar full_name
        varchar password_hash
        boolean is_active
    }
    SALES_SALESMAN_PROFILES {
        bigint id PK
        bigint user_id FK
        varchar employee_code
        varchar territory
    }
    SALES_CUSTOMERS {
        bigint id PK
        varchar code
        varchar name
        varchar customer_type
        varchar gstin
        char primary_state_code
        bigint assigned_salesman_id FK
    }
    SALES_CUSTOMER_ADDRESSES {
        bigint id PK
        bigint customer_id FK
        varchar address_type
        char state_code
        char pincode
        boolean is_default
    }
    SALES_PRODUCTS {
        bigint id PK
        varchar product_code
        varchar name
        varchar hsn_code
        integer gst_rate_bps
    }
    SALES_PACK_SIZES {
        bigint id PK
        bigint product_id FK
        varchar sku_code
        varchar display_name
        integer pack_weight_g
        integer packets_per_carton
        bigint base_selling_price_paisa
    }
    SALES_PRICE_LISTS {
        bigint id PK
        varchar name
        boolean is_default
        bigint customer_id FK
        date effective_from
    }
    SALES_PRICE_LIST_ITEMS {
        bigint id PK
        bigint price_list_id FK
        bigint pack_size_id FK
        bigint unit_price_paisa
    }
    SALES_SALES_ORDERS {
        bigint id PK
        varchar order_number
        uuid client_order_id
        bigint salesman_id FK
        bigint customer_id FK
        char place_of_supply_state_code
        date order_date
        varchar status
        boolean has_shortage
        bigint approved_by FK
    }
    SALES_SALES_ORDER_ITEMS {
        bigint id PK
        bigint sales_order_id FK
        bigint pack_size_id FK
        integer ordered_qty_pkts
        integer approved_qty_pkts
        bigint unit_price_paisa
        bigint line_taxable_paisa
    }
    SALES_ORDER_STATUS_HISTORY {
        bigint id PK
        bigint sales_order_id FK
        varchar from_status
        varchar to_status
        bigint changed_by FK
        timestamptz changed_at
    }
    SALES_ORDER_APPROVALS {
        bigint id PK
        bigint sales_order_id FK
        bigint reviewed_by FK
        varchar decision
        integer ordered_total_pkts
        integer available_total_pkts
        integer shortage_pkts
        jsonb stock_snapshot
    }

    IAM_ROLES ||--o{ IAM_USERS : "assigned_to"
    IAM_USERS ||--o| SALES_SALESMAN_PROFILES : "extends"
    IAM_USERS ||--o{ SALES_CUSTOMERS : "assigned_salesman"
    IAM_USERS ||--o{ SALES_SALES_ORDERS : "submitted_by"
    SALES_CUSTOMERS ||--|{ SALES_CUSTOMER_ADDRESSES : "has_addresses"
    SALES_CUSTOMERS ||--o{ SALES_PRICE_LISTS : "optional_pricing"
    SALES_CUSTOMERS ||--o{ SALES_SALES_ORDERS : "places"
    SALES_PRODUCTS ||--|{ SALES_PACK_SIZES : "packaged_as"
    SALES_PRICE_LISTS ||--|{ SALES_PRICE_LIST_ITEMS : "defines"
    SALES_PACK_SIZES ||--o{ SALES_PRICE_LIST_ITEMS : "priced_in"
    SALES_SALES_ORDERS ||--|{ SALES_SALES_ORDER_ITEMS : "contains"
    SALES_PACK_SIZES ||--o{ SALES_SALES_ORDER_ITEMS : "ordered_sku"
    SALES_SALES_ORDERS ||--|{ SALES_ORDER_STATUS_HISTORY : "tracks_status"
    SALES_SALES_ORDERS ||--o{ SALES_ORDER_APPROVALS : "verified_by"
```

---

## 2. GST Billing, Dispatches & Finance (`billing` + `finance` Schemas)

```mermaid
erDiagram
    BILLING_FISCAL_SEQUENCES {
        bigint id PK
        varchar doc_type
        varchar financial_year
        integer last_seq_no
    }
    BILLING_INVOICES {
        bigint id PK
        varchar invoice_number
        varchar financial_year
        bigint sales_order_id FK
        bigint customer_id FK
        char place_of_supply_state_code
        varchar supply_type
        varchar doc_status
        varchar payment_status
        varchar dispatch_status
        bigint taxable_total_paisa
        bigint cgst_total_paisa
        bigint sgst_total_paisa
        bigint igst_total_paisa
        bigint grand_total_paisa
    }
    BILLING_INVOICE_ITEMS {
        bigint id PK
        bigint invoice_id FK
        bigint sales_order_item_id FK
        bigint pack_size_id FK
        varchar hsn_code
        integer qty_pkts
        bigint unit_price_paisa
        bigint taxable_paisa
        bigint cgst_paisa
        bigint sgst_paisa
        bigint igst_paisa
    }
    BILLING_INVOICE_TAX_COMPONENTS {
        bigint id PK
        bigint invoice_id FK
        varchar hsn_code
        varchar tax_type
        integer rate_bps
        bigint taxable_base_paisa
        bigint tax_amount_paisa
    }
    BILLING_CREDIT_NOTES {
        bigint id PK
        varchar cn_number
        bigint original_invoice_id FK
        date issue_date
        text reason
        varchar status
        bigint total_reversed_paisa
    }
    BILLING_CREDIT_NOTE_ITEMS {
        bigint id PK
        bigint credit_note_id FK
        bigint invoice_item_id FK
        bigint pack_size_id FK
        integer qty_pkts
        varchar return_disposition
    }
    BILLING_DISPATCHES {
        bigint id PK
        varchar dispatch_number
        bigint invoice_id FK
        bigint sales_order_id FK
        date dispatch_date
        varchar vehicle_or_lr_ref
    }
    BILLING_DISPATCH_ITEMS {
        bigint id PK
        bigint dispatch_id FK
        bigint invoice_item_id FK
        bigint pack_size_id FK
        integer dispatched_qty_pkts
    }
    FINANCE_PAYMENTS {
        bigint id PK
        varchar payment_number
        bigint customer_id FK
        date payment_date
        bigint amount_paisa
        varchar payment_mode
        uuid idempotency_key
        varchar status
    }
    FINANCE_PAYMENT_ALLOCATIONS {
        bigint id PK
        bigint payment_id FK
        bigint invoice_id FK
        bigint allocated_paisa
        boolean is_reversed
    }
    FINANCE_CUSTOMER_RECEIVABLES {
        bigint id PK
        bigint customer_id FK
        bigint invoice_id FK
        date invoice_date
        bigint original_paisa
        bigint credited_paisa
        bigint paid_paisa
        bigint outstanding_paisa
    }

    BILLING_INVOICES ||--|{ BILLING_INVOICE_ITEMS : "lines"
    BILLING_INVOICES ||--|{ BILLING_INVOICE_TAX_COMPONENTS : "gstr_buckets"
    BILLING_INVOICES ||--o{ BILLING_CREDIT_NOTES : "cancelled_by"
    BILLING_CREDIT_NOTES ||--|{ BILLING_CREDIT_NOTE_ITEMS : "reverses"
    BILLING_INVOICES ||--o{ BILLING_DISPATCHES : "dispatched_via"
    BILLING_DISPATCHES ||--|{ BILLING_DISPATCH_ITEMS : "ships"
    BILLING_INVOICE_ITEMS ||--o{ BILLING_DISPATCH_ITEMS : "fulfills"
    BILLING_INVOICES ||--|| FINANCE_CUSTOMER_RECEIVABLES : "creates_ar"
    FINANCE_PAYMENTS ||--o{ FINANCE_PAYMENT_ALLOCATIONS : "allocates"
    BILLING_INVOICES ||--o{ FINANCE_PAYMENT_ALLOCATIONS : "settled_by"
```

---

## 3. Purchasing, BOM, Production & Costing (`purchasing` + `production` + `costing` Schemas)

```mermaid
erDiagram
    PURCHASING_SUPPLIERS {
        bigint id PK
        varchar code
        varchar name
        char state_code
    }
    PURCHASING_PURCHASE_ORDERS {
        bigint id PK
        varchar po_number
        bigint supplier_id FK
        varchar status
        bigint total_paisa
    }
    PURCHASING_PURCHASE_ORDER_ITEMS {
        bigint id PK
        bigint purchase_order_id FK
        bigint material_id FK
        numeric ordered_qty_base
        bigint unit_rate_paisa
    }
    PURCHASING_PURCHASE_RECEIPTS {
        bigint id PK
        varchar receipt_number
        bigint purchase_order_id FK
        bigint supplier_id FK
        varchar status
        bigint total_paisa
    }
    PURCHASING_PURCHASE_RECEIPT_ITEMS {
        bigint id PK
        bigint purchase_receipt_id FK
        bigint material_id FK
        numeric received_qty_base
        numeric unit_cost_paisa_per_base
        bigint line_total_paisa
    }
    PRODUCTION_MATERIALS {
        bigint id PK
        varchar code
        varchar name
        varchar material_category
        varchar unit_dimension
        varchar base_uom
    }
    PRODUCTION_RECIPE_TEMPLATES {
        bigint id PK
        varchar code
        bigint product_id FK
        numeric base_yield_weight_g
    }
    PRODUCTION_BOM_HEADERS {
        bigint id PK
        bigint pack_size_id FK
        bigint active_version_id FK
    }
    PRODUCTION_BOM_VERSIONS {
        bigint id PK
        bigint bom_header_id FK
        bigint recipe_template_id FK
        integer version_no
        integer expected_yield_pkts
        varchar status
    }
    PRODUCTION_BOM_COMPONENTS {
        bigint id PK
        bigint bom_version_id FK
        bigint material_id FK
        varchar component_role
        numeric std_qty_base
    }
    PRODUCTION_RUNS {
        bigint id PK
        varchar run_number
        bigint pack_size_id FK
        bigint bom_version_id FK
        numeric batch_multiplier
        integer expected_output_pkts
        integer actual_good_output_pkts
        varchar status
    }
    PRODUCTION_MATERIAL_ISSUES {
        bigint id PK
        bigint production_run_id FK
        bigint material_id FK
        varchar issue_phase
        numeric planned_qty_base
        numeric actual_good_used_base
        numeric damaged_qty_base
        bigint cost_absorbed_paisa
    }
    PRODUCTION_OUTPUTS {
        bigint id PK
        bigint production_run_id FK
        bigint pack_size_id FK
        integer good_qty_pkts
        varchar batch_code
        date expiry_date
    }
    PRODUCTION_WASTAGES {
        bigint id PK
        bigint production_run_id FK
        bigint material_id FK
        varchar wastage_type
        numeric qty_base
        bigint cost_impact_paisa
    }
    PRODUCTION_VARIANCES {
        bigint id PK
        bigint production_run_id FK
        varchar variance_scope
        bigint material_id FK
        numeric variance_pct
        boolean is_flagged
    }
    COSTING_PRODUCTION_OVERHEADS {
        bigint id PK
        bigint production_run_id FK
        char period_month
        varchar overhead_type
        varchar allocation_scope
        bigint amount_paisa
    }
    COSTING_PRODUCTION_COST_SUMMARIES {
        bigint id PK
        bigint production_run_id FK
        varchar valuation_method
        bigint raw_material_cost_paisa
        bigint packaging_cost_paisa
        bigint direct_overhead_paisa
        bigint total_cost_paisa
        bigint cost_per_packet_paisa
        bigint gross_margin_paisa
    }

    PURCHASING_SUPPLIERS ||--o{ PURCHASING_PURCHASE_ORDERS : "receives_po"
    PURCHASING_PURCHASE_ORDERS ||--|{ PURCHASING_PURCHASE_ORDER_ITEMS : "lines"
    PURCHASING_PURCHASE_ORDERS ||--o{ PURCHASING_PURCHASE_RECEIPTS : "fulfilled_by"
    PURCHASING_SUPPLIERS ||--o{ PURCHASING_PURCHASE_RECEIPTS : "delivers"
    PURCHASING_PURCHASE_RECEIPTS ||--|{ PURCHASING_PURCHASE_RECEIPT_ITEMS : "items"
    PRODUCTION_MATERIALS ||--o{ PURCHASING_PURCHASE_RECEIPT_ITEMS : "received_as"

    PRODUCTION_BOM_HEADERS ||--|{ PRODUCTION_BOM_VERSIONS : "versions"
    PRODUCTION_RECIPE_TEMPLATES ||--o{ PRODUCTION_BOM_VERSIONS : "shared_base"
    PRODUCTION_BOM_VERSIONS ||--|{ PRODUCTION_BOM_COMPONENTS : "requires"
    PRODUCTION_MATERIALS ||--o{ PRODUCTION_BOM_COMPONENTS : "component"

    PRODUCTION_BOM_VERSIONS ||--o{ PRODUCTION_RUNS : "governs"
    PRODUCTION_RUNS ||--|{ PRODUCTION_MATERIAL_ISSUES : "issues"
    PRODUCTION_RUNS ||--o{ PRODUCTION_OUTPUTS : "yields"
    PRODUCTION_RUNS ||--o{ PRODUCTION_WASTAGES : "incurs"
    PRODUCTION_RUNS ||--|{ PRODUCTION_VARIANCES : "measures"
    PRODUCTION_RUNS ||--o{ COSTING_PRODUCTION_OVERHEADS : "absorbs"
    PRODUCTION_RUNS ||--|| COSTING_PRODUCTION_COST_SUMMARIES : "costed_by"
```

---

## 4. Inventory Ledger, Cost Lots & Audit (`inventory` + `audit` Schemas)

```mermaid
erDiagram
    INVENTORY_OPENING_BALANCES {
        bigint id PK
        varchar batch_ref
        varchar item_category
        bigint material_id FK
        bigint pack_size_id FK
        numeric opening_qty_base
        numeric unit_cost_paisa_per_base
    }
    INVENTORY_BALANCES {
        bigint id PK
        varchar item_category
        bigint material_id FK
        bigint pack_size_id FK
        numeric on_hand_qty_base
        numeric reserved_qty_base
        numeric available_qty_base
    }
    INVENTORY_COST_LOTS {
        bigint id PK
        varchar item_category
        bigint material_id FK
        bigint pack_size_id FK
        varchar source_doc_type
        bigint source_doc_id
        varchar batch_code
        date expiry_date
        numeric original_qty_base
        numeric remaining_qty_base
        numeric unit_cost_paisa_per_base
    }
    INVENTORY_STOCK_ADJUSTMENTS {
        bigint id PK
        varchar adjustment_number
        varchar item_category
        bigint material_id FK
        bigint pack_size_id FK
        numeric delta_qty_base
        text reason
        varchar status
    }
    INVENTORY_MOVEMENTS {
        bigint id PK
        varchar item_category
        bigint material_id FK
        bigint pack_size_id FK
        varchar movement_type
        numeric signed_qty_base
        numeric unit_cost_paisa_per_base
        bigint total_cost_paisa
        varchar source_doc_type
        bigint opening_balance_id FK
        bigint purchase_receipt_item_id FK
        bigint production_run_id FK
        bigint dispatch_item_id FK
        bigint credit_note_item_id FK
        bigint stock_adjustment_id FK
        timestamptz occurred_at
    }
    INVENTORY_COST_LOT_CONSUMPTIONS {
        bigint id PK
        bigint inventory_movement_id FK
        bigint cost_lot_id FK
        numeric consumed_qty_base
        bigint cost_paisa
    }
    AUDIT_VARIANCE_ALERTS {
        bigint id PK
        bigint production_run_id FK
        bigint production_variance_id FK
        varchar alert_type
        varchar status
    }
    AUDIT_AUDIT_LOGS {
        bigint id PK
        bigint actor_user_id FK
        varchar actor_role
        timestamptz occurred_at
        varchar action
        varchar entity_schema
        varchar entity_table
        bigint entity_id
        jsonb before_state
        jsonb after_state
        text reason
    }

    INVENTORY_OPENING_BALANCES ||--o{ INVENTORY_MOVEMENTS : "source_opening"
    INVENTORY_STOCK_ADJUSTMENTS ||--o{ INVENTORY_MOVEMENTS : "source_adj"
    INVENTORY_MOVEMENTS ||--o{ INVENTORY_COST_LOT_CONSUMPTIONS : "depletes"
    INVENTORY_COST_LOTS ||--o{ INVENTORY_COST_LOT_CONSUMPTIONS : "allocated_from"
    INVENTORY_BALANCES ||--o{ INVENTORY_MOVEMENTS : "reconciles_100pct"
```
