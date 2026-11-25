# Domain Entities Catalogue & Justification

**Goal:** Classify every necessary domain concept cleanly — avoiding both missing critical audit structures and bloated generic-ERP overengineering.

---

## 1. Master Classification Table

| Classification | Canonical Entities | Role in System |
| --- | --- | --- |
| **Reference / Master Data** | `CompanyProfile`, `Role`, `User`, `Customer`, `Supplier`, `Product`, `PriceList`, `PriceListItem`, `Material`, `UnitConversion`, `RecipeTemplate`, `BillOfMaterials`, `BomVersion`, `BomItem` | Slow-changing business definitions, tax rules, UOM algebra, prices, and versioned recipes. |
| **Core Domain Entities** | `SalesOrder`, `ProductionRun`, `InventoryMovement`, `InventoryBalance`, `CostLot`, `Invoice`, `CreditNote`, `ProductionCostSummary` | Central aggregates enforcing business invariants, stock physics, BOM math, GST compliance, and costing. |
| **Supporting Entities** | `SalesOrderItem`, `InvoiceItem`, `InvoiceTaxComponent`, `CreditNoteItem`, `Dispatch`, `DispatchItem`, `FiscalSequence`, `PurchaseOrder`, `PurchaseOrderItem`, `PurchaseReceipt`, `PurchaseReceiptItem`, `ProductionMaterialIssue`, `ProductionOverhead`, `PaymentAllocation`, `CustomerReceivable`, `VarianceAlert` | Line items, sequence generators, allocation bridges, optional procurement stage, overhead pools, and operational alerts. |
| **Transaction Records** | `SalesOrder`, `PurchaseReceipt`, `ProductionRun`, `Invoice`, `CreditNote`, `Dispatch`, `Payment`, `StockAdjustment`, `InventoryMovement` | Time-stamped operational events that initiate state changes, stock movements, or AR movements. |
| **Audit & Traceability Records** | `AuditLog`, `InventoryMovement` *(dual-classified as ledger + traceability)*, `BomVersion` *(historical recipe snapshot)*, `CostLot` *(valuation provenance)* | Immutable tamper-evident proof explaining *who* changed *what*, *when*, *why*, and *from which source document*. |

---

## 2. Detailed Entity Classification & Inclusion Justification

### 2.1 Identity & Governance Masters
1. **`CompanyProfile`** *(Reference / Master)* — Holds factory legal name, GSTIN, **Factory State & State Code (`Tamil Nadu / 33`)**, default variance tolerance (`3.0%`), active inventory valuation policy (`FIFO` vs `WEIGHTED_AVERAGE`), and invoice numbering settings. Essential so GST Place-of-Supply logic is data-driven rather than hardcoded.
2. **`Role`** *(Reference / Master)* — Defines the 5 system roles (`SALESMAN`, `FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR`, `ACCOUNTANT_AUDITOR`, `OWNER`) and permission capability set (`Section 3`).
3. **`User`** *(Reference / Master)* — Authenticates actors and anchors every audit entry and `salesman_id` ownership check (`Section 3`, `Section 7`).

### 2.2 Commercial & Sales Masters
4. **`Customer`** *(Reference / Master)* — Represents Retailers and Distributors (`Retailer A`, `Distributor B`). Mandatory `state_code` governs `CGST+SGST` vs `IGST`; optional `gstin` separates B2B vs B2C in GSTR-1; optional `assigned_salesman_id` scopes mobile customer lists.
5. **`Product`** *(Reference / Master — Finished SKU)* — Represents a sellable pack SKU (e.g., `Murukku 200 g`, `Murukku 500 g`). Carries `hsn_code`, `gst_rate_bps`, `pack_weight_grams`, `packets_per_carton`, and `base_selling_price_paisa`. Consolidates "Product + Pack Size" cleanly into SKU master records so orders, GST invoices, and finished inventory operate on concrete sellable units.
6. **`PriceList` & `PriceListItem`** *(Supporting Master)* — Supports active standard selling prices (`₹50.00`) plus optional customer/tier-specific pricing or validity windows (`Section 4.1`: *"Price comes from a price list; customer-specific prices or schemes are optional"*). Kept minimal (standard default list + optional customer override).

### 2.3 Production & Material Masters
7. **`Material`** *(Reference / Master)* — Unified representation for both **Raw Materials** (`Flour`, `Cooking oil`, `Salt and spice mix`) and **Packaging Materials** (`200 g pouch`, `Carton`), differentiated by `material_category`. *Justification for unifying:* Both undergo supplier purchases, stock ledger movements, unit conversions, FIFO cost layers, and BOM issues — separating them into two tables would duplicate inventory ledger code unnecessarily.
8. **`UnitConversion`** *(Reference / Master)* — Formalizes exact rational conversion factors within dimensions (`1 kg = 1000 g`, `1 L = 1000 ml`, `1 piece = 1 piece`) and blocks invalid cross-dimension conversions (`kg` to `L`).
9. **`RecipeTemplate`** *(Supporting Core Master)* — Optional shared cooking recipe (e.g., `Murukku Base Cooking Formula`: `40 kg` flour, `10 L` oil, `1.2 kg` spice yielding `40,000 g` bulk snack). *Justification:* Directly enables adding `Murukku 500 g` sharing the same base cooking recipe (`Section 9` interview scenario) without duplicating ingredients!
10. **`BillOfMaterials` & `BomVersion` & `BomItem`** *(Core Master)* — `BillOfMaterials` anchors the recipe to a `Product`; `BomVersion` creates an immutable numbered recipe snapshot (`expected_yield_packets`, optional `recipe_template_id`); `BomItem` specifies standard input material, quantity, and unit per 1 batch. *Justification:* Guarantees historical production runs never mutate when a recipe changes (`EC-15`).

### 2.4 Purchasing Documents
11. **`Supplier`** *(Reference / Master)* — Vendor providing raw or packaging materials (`Should have`, `FR-S-01`).
12. **`PurchaseOrder` & `PurchaseOrderItem`** *(Supporting Transaction)* — Models formal procurement lifecycle (`Draft -> Approved -> Ordered -> Closed`) per Task 5. Optional in daily floor flow: `PurchaseReceipt` may reference a `PurchaseOrder` OR be recorded directly on material arrival (`Benchmark Step 1`).
13. **`PurchaseReceipt` & `PurchaseReceiptItem`** *(Core Transaction)* — The goods receipt / supplier purchase voucher (`PUR-001`: `60 kg` Flour @ `₹45/kg`). Directly drives positive stock ledger movements and FIFO cost layers.

### 2.5 Sales Order, Billing, Dispatch & Collections
14. **`SalesOrder` & `SalesOrderItem`** *(Core Transaction + Line)* — Captures field salesman demand (`ORD-001`, `ORD-002`) with `client_order_id` idempotency key, frozen price snapshot at submission/approval, stock shortage flags, and Admin approval metadata.
15. **`FiscalSequence`** *(Supporting Control)* — Guarantees concurrency-safe, gap-free Indian Financial Year sequential numbering (`INV/2026-27/0001`, `CN/2026-27/0001`).
16. **`Invoice`, `InvoiceItem` & `InvoiceTaxComponent`** *(Core Transaction + Lines)* — Immutable GST tax invoice once `POSTED`/`ISSUED`. `InvoiceTaxComponent` groups tax by `(tax_type, rate_bps, hsn_code)` for exact GSTR-1/3B mapping and `CGST == SGST` rounding integrity.
17. **`CreditNote` & `CreditNoteItem`** *(Core Transaction + Line)* — Mandatory compensating document for cancelling or adjusting a `POSTED` invoice (`Section 7`), never deleting original invoice history.
18. **`Dispatch` & `DispatchItem`** *(Supporting Transaction + Line)* — Records physical shipment (`DSP-001`), carrier details, and triggers Finished Goods stock ledger deduction (`BR-DSP-01`) while releasing order reservation. Supports both single and partial dispatch.
19. **`Payment`, `PaymentAllocation` & `CustomerReceivable`** *(Core/Supporting Financial)* — `Payment` records money received (`₹4,000`); `PaymentAllocation` maps payments N:M to open invoices; `CustomerReceivable` tracks open AR balance per invoice/customer (derived/reconciled against `Invoice - CreditNote - PaymentAllocation`) for fast ageing queries.

### 2.6 Production, Inventory Ledger, Costing & Audit
20. **`ProductionRun` & `ProductionMaterialIssue`** *(Core Transaction + Lines)* — `ProductionRun` pins `bom_version_id`, `batch_multiplier`, `expected_output_qty`, `actual_good_output_qty`, `process_scrap_qty`, `yield_variance_pct`, and `yield_flagged`. `ProductionMaterialIssue` logs every raw & packaging input: `planned_qty_base`, `actual_issued_qty_base`, `damaged_qty_base` (e.g., `6` pouches), `consumption_variance_pct`, `is_flagged`, and absorbed valuation cost (`paisa`).
21. **`InventoryBalance`** *(Core Concurrency/Projection)* — Maintains `on_hand_qty_base` and `reserved_qty_base` per `(item_type, item_id)` for fast atomic row-locking during concurrent approvals/issues (`EC-03`). **Strictly subordinate to `InventoryMovement`**: `on_hand_qty_base` must always reconcile 100% with the sum of `InventoryMovement` rows.
22. **`InventoryMovement`** *(Core Ledger & Audit)* — Append-only stock ledger recording every physical change (`OPENING`, `PURCHASE_IN`, `PROD_ISSUE_OUT`, `PACKAGING_DAMAGE_OUT`, `PROD_OUTPUT_IN`, `PROD_RETURN_IN`, `DISPATCH_OUT`, `CREDIT_RETURN_IN`, `ADJUSTMENT`), unit cost, and mandatory `(source_doc_type, source_doc_id)`.
23. **`CostLot`** *(Core Valuation)* — Receipt-created cost layer (`remaining_qty_base`, `unit_cost_paisa`, `batch_code`, `expiry_date`) enabling exact FIFO depletion and future FEFO food expiry tracking (`FR-G-02`).
24. **`StockAdjustment`** *(Supporting Transaction)* — Controlled document for physical count discrepancies or floor spoilage outside runs, requiring reason code & approver before writing to `InventoryMovement`.
25. **`ProductionOverhead` & `ProductionCostSummary`** *(Supporting / Core Costing)* — `ProductionOverhead` records direct run overheads (`Labour ₹1,200`, `Gas/Power ₹600`) or monthly shared factory overhead pools (`Section 4.5`). `ProductionCostSummary` persists the audited cost computation (RM cost + Packaging cost incl. damaged + Overheads, cost per good packet, margin vs selling price).
26. **`VarianceAlert`** *(Supporting Operational Alert)* — Generated automatically when consumption or yield variance exceeds configured tolerance (`> 3%`), surfaced on Owner & Supervisor dashboards until acknowledged.
27. **`AuditLog`** *(Audit & Traceability)* — Immutable append-only audit trail (`actor_user_id`, `actor_role`, `timestamp`, `entity_type`, `entity_id`, `action`, `before_json`, `after_json`, `reason`).

---

## 3. Intentional Exclusions (Avoiding Overengineering)

| Candidate Concept | Decision | Justification |
| --- | --- | --- |
| **Separate `RawMaterial` & `PackagingMaterial` entities** | **Excluded (Unified into `Material`)** | Identical inventory, UOM, purchase, and cost-lot behavior; `material_category` flag avoids duplicate tables and joins. |
| **Separate `ProductionOutput` table (1:1 with Run)** | **Excluded (Embedded in `ProductionRun`)** | Each run manufactures one SKU (`Murukku 200 g`); a separate 1:1 output table adds joins with zero domain benefit. |
| **Persisted `Report` tables** | **Excluded (Modeled as Read Models)** | Sales Register, GSTR-1/3B, Stock Summary, and AR Ageing must always reflect live posted ledger truth — storing duplicate report tables risks drift. |
| **General Ledger / Chart of Accounts / Journal Entries** | **Excluded** | Official Problem Statement Section 2 specifies accounting software like Tally is *not* required; Invoice/CN/AR/Costing satisfies all audit requirements cleanly. |
| **Multi-Warehouse / Bin Locations** | **Excluded (Single Factory Scope)** | Section 1 defines *"one factory"*; abstracting `StockBalance` per item without multi-warehouse complexity keeps the model sharp (can be added cleanly later if needed). |
| **Separate `WIP` Warehouse Ledger** | **Deferred / Implicit via `ProductionRun`** | Section 4.4 marks WIP *"if you choose to model it"*. Modeling raw issue immediately on `IN_PROGRESS` and FG receipt on `COMPLETED` captures WIP without redundant intermediate warehouse transfers. |
