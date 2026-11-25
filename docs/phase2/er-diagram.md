# Conceptual Entity-Relationship Diagrams

**Diagram Strategy:** To avoid an unreadable spaghetti diagram across ~35 domain entities, this document presents:
1. **Diagram 1:** High-Level Cross-Module Conceptual Architecture ER Diagram (Core Aggregates & Bridge Keys).
2. **Diagram 2:** IAM & Commercial Masters (`Users`, `Customers`, `Products`, `PriceLists`).
3. **Diagram 3:** Sales Loop (`SalesOrder` -> `Invoice` / `CreditNote` -> `Dispatch` -> `Payment` / `Receivable`).
4. **Diagram 4:** Production Loop (`Suppliers`, `PurchaseReceipt`, `RecipeTemplate`, `BOM`, `ProductionRun`, `Costing`).
5. **Diagram 5:** Inventory Ledger, Cost Lots & Audit Trail (`InventoryBalance`, `InventoryMovement`, `CostLot`, `AuditLog`).

> *Note:* Attribute types (`uuid`, `string`, `integer_paisa`, `decimal_qty`, `enum`, `date`, `datetime`, `boolean`) represent **conceptual domain types**, not physical SQL DDL types.

---

## 1. High-Level Cross-Module ER Overview (Core Aggregates)

```mermaid
erDiagram
    COMPANY_PROFILE ||--o{ USER : "employs"
    ROLE ||--o{ USER : "authorizes"
    USER ||--o{ CUSTOMER : "assigned_to"
    USER ||--o{ SALES_ORDER : "submits"

    CUSTOMER ||--o{ SALES_ORDER : "places"
    SALES_ORDER ||--o| INVOICE : "billed_as"
    INVOICE ||--o{ CREDIT_NOTE : "cancelled_or_adjusted_by"
    INVOICE ||--o{ DISPATCH : "fulfilled_by"
    CUSTOMER ||--o{ PAYMENT : "remits"
    PAYMENT ||--o{ PAYMENT_ALLOCATION : "allocated_via"
    INVOICE ||--o{ PAYMENT_ALLOCATION : "settled_by"

    SUPPLIER ||--o{ PURCHASE_RECEIPT : "supplies"
    PRODUCT ||--o| BILL_OF_MATERIALS : "has_recipe"
    BILL_OF_MATERIALS ||--|{ BOM_VERSION : "versions"
    BOM_VERSION ||--o{ PRODUCTION_RUN : "governs"
    PRODUCTION_RUN ||--|| PRODUCTION_COST_SUMMARY : "costed_by"

    PURCHASE_RECEIPT ||--o{ INVENTORY_MOVEMENT : "credits_rm_pkg"
    PRODUCTION_RUN ||--o{ INVENTORY_MOVEMENT : "debits_rm_pkg_credits_fg"
    DISPATCH ||--o{ INVENTORY_MOVEMENT : "debits_fg"
    CREDIT_NOTE ||--o{ INVENTORY_MOVEMENT : "returns_fg"
```

---

## 2. Module Diagram A — IAM & Commercial Masters

```mermaid
erDiagram
    COMPANY_PROFILE {
        uuid id PK
        string legal_name
        string gstin
        string state_code
        decimal variance_tolerance_pct
        enum valuation_method
    }

    ROLE {
        uuid id PK
        enum code
        string name
    }

    USER {
        uuid id PK
        uuid role_id FK
        string full_name
        string login_identifier
        boolean is_active
    }

    CUSTOMER {
        uuid id PK
        string code
        string name
        enum customer_type
        string state_name
        string state_code
        string gstin
        uuid assigned_salesman_id FK
        boolean is_active
    }

    PRODUCT {
        uuid id PK
        string sku_code
        string name
        string hsn_code
        integer gst_rate_bps
        integer pack_weight_g
        integer packets_per_carton
        integer_paisa base_selling_price_paisa
        boolean is_active
    }

    PRICE_LIST {
        uuid id PK
        string name
        boolean is_default
        uuid customer_id FK
        date effective_from
        date effective_to
    }

    PRICE_LIST_ITEM {
        uuid id PK
        uuid price_list_id FK
        uuid product_id FK
        integer_paisa unit_price_paisa
    }

    ROLE ||--o{ USER : "assigned_to"
    USER ||--o{ CUSTOMER : "manages_territory"
    CUSTOMER ||--o{ PRICE_LIST : "optional_override"
    PRICE_LIST ||--|{ PRICE_LIST_ITEM : "contains"
    PRODUCT ||--o{ PRICE_LIST_ITEM : "priced_in"
```

---

## 3. Module Diagram B — Sales Orders, GST Billing, Dispatch & Payments

```mermaid
erDiagram
    SALES_ORDER {
        uuid id PK
        string order_number
        uuid client_order_id
        uuid salesman_id FK
        uuid customer_id FK
        date order_date
        enum status
        boolean shortage_flag
        uuid approved_by FK
    }

    SALES_ORDER_ITEM {
        uuid id PK
        uuid sales_order_id FK
        uuid product_id FK
        integer ordered_qty_pkts
        integer approved_qty_pkts
        integer_paisa unit_price_paisa
    }

    FISCAL_SEQUENCE {
        uuid id PK
        enum doc_type
        string financial_year
        integer next_seq_no
    }

    INVOICE {
        uuid id PK
        string invoice_number
        string financial_year
        uuid sales_order_id FK
        uuid customer_id FK
        string place_of_supply_state_code
        enum supply_type
        date invoice_date
        enum doc_status
        enum payment_status
        enum dispatch_status
        integer_paisa taxable_total_paisa
        integer_paisa cgst_total_paisa
        integer_paisa sgst_total_paisa
        integer_paisa igst_total_paisa
        integer_paisa grand_total_paisa
    }

    INVOICE_ITEM {
        uuid id PK
        uuid invoice_id FK
        uuid product_id FK
        string hsn_code
        integer qty_pkts
        integer_paisa unit_price_paisa
        integer_paisa taxable_paisa
        integer gst_rate_bps
        integer_paisa cgst_paisa
        integer_paisa sgst_paisa
        integer_paisa igst_paisa
    }

    INVOICE_TAX_COMPONENT {
        uuid id PK
        uuid invoice_id FK
        string hsn_code
        enum tax_type
        integer rate_bps
        integer_paisa taxable_base_paisa
        integer_paisa tax_amount_paisa
    }

    CREDIT_NOTE {
        uuid id PK
        string cn_number
        uuid original_invoice_id FK
        date issue_date
        string reason
        enum status
        integer_paisa total_reversed_paisa
    }

    CREDIT_NOTE_ITEM {
        uuid id PK
        uuid credit_note_id FK
        uuid invoice_item_id FK
        uuid product_id FK
        integer returned_qty_pkts
        enum return_disposition
    }

    DISPATCH {
        uuid id PK
        string dispatch_number
        uuid invoice_id FK
        uuid sales_order_id FK
        date dispatch_date
        string vehicle_or_lr_ref
    }

    DISPATCH_ITEM {
        uuid id PK
        uuid dispatch_id FK
        uuid invoice_item_id FK
        uuid product_id FK
        integer dispatched_qty_pkts
    }

    PAYMENT {
        uuid id PK
        string payment_number
        uuid customer_id FK
        date payment_date
        integer_paisa amount_paisa
        enum payment_mode
        string reference_no
        uuid idempotency_key
        enum status
    }

    PAYMENT_ALLOCATION {
        uuid id PK
        uuid payment_id FK
        uuid invoice_id FK
        integer_paisa allocated_paisa
    }

    CUSTOMER_RECEIVABLE {
        uuid id PK
        uuid customer_id FK
        uuid invoice_id FK
        integer_paisa original_paisa
        integer_paisa credited_paisa
        integer_paisa paid_paisa
        integer_paisa outstanding_paisa
    }

    SALES_ORDER ||--|{ SALES_ORDER_ITEM : "has_lines"
    SALES_ORDER ||--o| INVOICE : "generates"
    INVOICE ||--|{ INVOICE_ITEM : "bills"
    INVOICE ||--|{ INVOICE_TAX_COMPONENT : "summarizes_tax"
    INVOICE ||--o{ CREDIT_NOTE : "offset_by"
    CREDIT_NOTE ||--|{ CREDIT_NOTE_ITEM : "reverses"
    INVOICE ||--o{ DISPATCH : "ships_via"
    DISPATCH ||--|{ DISPATCH_ITEM : "ships_lines"
    INVOICE ||--|| CUSTOMER_RECEIVABLE : "tracks_ar"
    PAYMENT ||--o{ PAYMENT_ALLOCATION : "distributes"
    INVOICE ||--o{ PAYMENT_ALLOCATION : "receives"
```

---

## 4. Module Diagram C — Purchasing, BOM, Production & Costing

```mermaid
erDiagram
    SUPPLIER {
        uuid id PK
        string code
        string name
        string state_code
        string gstin
    }

    PURCHASE_ORDER {
        uuid id PK
        string po_number
        uuid supplier_id FK
        date order_date
        enum status
    }

    PURCHASE_ORDER_ITEM {
        uuid id PK
        uuid purchase_order_id FK
        uuid material_id FK
        decimal_qty ordered_qty_base
        integer_paisa unit_rate_paisa
    }

    PURCHASE_RECEIPT {
        uuid id PK
        string receipt_number
        uuid purchase_order_id FK
        uuid supplier_id FK
        string supplier_bill_ref
        date receipt_date
        enum status
        integer_paisa total_paisa
    }

    PURCHASE_RECEIPT_ITEM {
        uuid id PK
        uuid purchase_receipt_id FK
        uuid material_id FK
        decimal_qty received_qty_base
        integer_paisa unit_cost_paisa
        integer_paisa line_total_paisa
    }

    MATERIAL {
        uuid id PK
        string code
        string name
        enum material_category
        enum unit_dimension
        string base_uom
        string display_uom
        decimal_qty reorder_level_base
    }

    RECIPE_TEMPLATE {
        uuid id PK
        string code
        string name
        integer base_yield_weight_g
    }

    BILL_OF_MATERIALS {
        uuid id PK
        uuid product_id FK
        uuid active_version_id FK
    }

    BOM_VERSION {
        uuid id PK
        uuid bom_id FK
        uuid recipe_template_id FK
        integer version_no
        integer expected_yield_packets
        enum status
    }

    BOM_ITEM {
        uuid id PK
        uuid bom_version_id FK
        uuid material_id FK
        enum input_role
        decimal_qty std_qty_base
    }

    PRODUCTION_RUN {
        uuid id PK
        string run_number
        uuid product_id FK
        uuid bom_version_id FK
        decimal_qty batch_multiplier
        integer expected_output_qty
        integer actual_good_output_qty
        decimal_qty yield_variance_pct
        boolean yield_flagged
        enum status
    }

    PRODUCTION_MATERIAL_ISSUE {
        uuid id PK
        uuid production_run_id FK
        uuid material_id FK
        enum issue_phase
        decimal_qty planned_qty_base
        decimal_qty actual_used_qty_base
        decimal_qty damaged_qty_base
        decimal_qty consumption_variance_pct
        boolean is_flagged
        integer_paisa cost_absorbed_paisa
    }

    PRODUCTION_OVERHEAD {
        uuid id PK
        uuid production_run_id FK
        string period_month
        enum overhead_type
        enum allocation_scope
        integer_paisa amount_paisa
    }

    PRODUCTION_COST_SUMMARY {
        uuid id PK
        uuid production_run_id FK
        enum valuation_method
        integer_paisa raw_material_cost_paisa
        integer_paisa packaging_cost_paisa
        integer_paisa overhead_cost_paisa
        integer_paisa total_cost_paisa
        integer_paisa cost_per_packet_paisa
        integer_paisa gross_margin_paisa
    }

    SUPPLIER ||--o{ PURCHASE_ORDER : "receives_po"
    PURCHASE_ORDER ||--|{ PURCHASE_ORDER_ITEM : "orders"
    PURCHASE_ORDER ||--o{ PURCHASE_RECEIPT : "fulfilled_by"
    SUPPLIER ||--o{ PURCHASE_RECEIPT : "delivers"
    PURCHASE_RECEIPT ||--|{ PURCHASE_RECEIPT_ITEM : "contains"
    MATERIAL ||--o{ PURCHASE_RECEIPT_ITEM : "stocked_from"

    BILL_OF_MATERIALS ||--|{ BOM_VERSION : "versions"
    RECIPE_TEMPLATE ||--o{ BOM_VERSION : "shared_cooking_base"
    BOM_VERSION ||--|{ BOM_ITEM : "defines"
    MATERIAL ||--o{ BOM_ITEM : "consumed_in"

    BOM_VERSION ||--o{ PRODUCTION_RUN : "templates"
    PRODUCTION_RUN ||--|{ PRODUCTION_MATERIAL_ISSUE : "consumes"
    MATERIAL ||--o{ PRODUCTION_MATERIAL_ISSUE : "issued_to"
    PRODUCTION_RUN ||--o{ PRODUCTION_OVERHEAD : "absorbs"
    PRODUCTION_RUN ||--|| PRODUCTION_COST_SUMMARY : "summarized_in"
```

---

## 5. Module Diagram D — Inventory Ledger, Cost Lots, Variance Alerts & Audit

```mermaid
erDiagram
    INVENTORY_BALANCE {
        uuid id PK
        enum item_type
        uuid item_id
        decimal_qty on_hand_qty_base
        decimal_qty reserved_qty_base
        datetime updated_at
    }

    INVENTORY_MOVEMENT {
        uuid id PK
        enum item_type
        uuid item_id
        enum movement_type
        decimal_qty signed_qty_base
        integer_paisa unit_cost_paisa
        integer_paisa total_cost_paisa
        enum source_doc_type
        uuid source_doc_id
        uuid cost_lot_id FK
        uuid created_by FK
        datetime occurred_at
    }

    COST_LOT {
        uuid id PK
        enum item_type
        uuid item_id
        enum source_doc_type
        uuid source_doc_id
        string batch_code
        date expiry_date
        decimal_qty original_qty_base
        decimal_qty remaining_qty_base
        integer_paisa unit_cost_paisa
    }

    STOCK_ADJUSTMENT {
        uuid id PK
        string adjustment_number
        enum item_type
        uuid item_id
        decimal_qty delta_qty_base
        string reason
        enum status
        uuid approved_by FK
    }

    VARIANCE_ALERT {
        uuid id PK
        uuid production_run_id FK
        enum alert_type
        string item_name
        decimal_qty variance_pct
        decimal_qty tolerance_pct
        enum status
    }

    AUDIT_LOG {
        uuid id PK
        uuid actor_user_id FK
        enum actor_role
        datetime occurred_at
        string action
        string entity_type
        uuid entity_id
        string before_json
        string after_json
        string reason
    }

    COST_LOT ||--o{ INVENTORY_MOVEMENT : "depletes_from"
    STOCK_ADJUSTMENT ||--o{ INVENTORY_MOVEMENT : "posts_ledger"
    INVENTORY_BALANCE ||--o{ INVENTORY_MOVEMENT : "reconciles_100pct"
```
