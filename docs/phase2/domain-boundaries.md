# Domain Boundaries & Logical Modules

**Architectural Style:** Modular Monolith with strict module ownership, explicit public service interfaces (commands/queries), and zero cross-module direct table mutation.

---

## 1. Module Dependency Rules (Acyclic Architecture)

To prevent circular dependencies ("big ball of mud"), dependencies follow a strict layered directed graph:
- **Foundation / Kernel:** `Identity & Access Management` and `Inventory Management` (and `Reporting & Audit` subscribing read-only across all modules).
- **No direct write access across boundaries:** e.g., `Billing & GST` never updates `InventoryBalance` directly — it invokes `InventoryManagement.RecordDispatchDeduction(...)` inside the shared transaction boundary.
- **Read-only audit isolation:** `Reporting & Audit` queries posted records and subscribes to audit/alert hooks, never mutating transactional aggregates.

---

## 2. Logical Modules Specification (All 10 Modules)

### Module 1: Identity & Access Management (`IAM`)
- **Responsibility:** User authentication, active session validation, role-based authorization (`5` roles), salesman territory/record scoping, and factory statutory configuration (`CompanyProfile`).
- **Owns:** `CompanyProfile`, `User`, `Role`.
- **Exposes:** `AuthenticateUser`, `AuthorizeAction(actor, permission, resourceScope)`, `GetFactoryTaxProfile()`, `GetVarianceTolerance()`.
- **Depends On:** None (foundation module; writes security denials to `AuditLog`).

### Module 2: Customer & Sales Management (`SalesCatalog`)
- **Responsibility:** Manage commercial customer master data (Retailers/Distributors, Place-of-Supply State & Code, GSTIN, territory ownership), finished product SKU catalog (`HSN`, `GST %`, `pack_weight_g`, `packets_per_carton`), and active price lists / customer price overrides.
- **Owns:** `Customer`, `Product`, `PriceList`, `PriceListItem`.
- **Exposes:** `GetCustomerTaxContext(customer_id)`, `ListActiveProductsForSalesman(customer_id)`, `ResolveUnitPrice(product_id, customer_id, date)`.
- **Depends On:** `IAM` (for salesman territory scoping & audit actor).

### Module 3: Order Management (`Orders`)
- **Responsibility:** Capture field salesman mobile orders idempotently (`client_order_id`), manage Admin verification workflow (`Request Correction`, `Approve`, `Reject`), enforce pre-invoice edit auditing, trigger soft FG stock reservation on Approval, and compute live shortage visibility (`Ordered vs Available`).
- **Owns:** `SalesOrder`, `SalesOrderItem`.
- **Exposes:** `SubmitOrder`, `RequestOrderCorrection`, `EditOrderBeforeInvoice`, `ApproveOrder`, `RejectOrder`, `GetPendingDemandForProduct` *(Stretch planning support)*.
- **Depends On:** `IAM`, `SalesCatalog` (customer & price snapshots), `Inventory` (availability query + reserve/release commands), `Audit` (logging edits/approvals).

### Module 4: Billing & GST (`Billing`)
- **Responsibility:** Generate gap-free Indian FY sequential GST Tax Invoices (`CGST+SGST` vs `IGST`), render compliant GST PDFs, manage Dispatch Notes (deducting physical FG stock via Inventory), and enforce Credit Note issuance for cancelling/adjusting posted invoices.
- **Owns:** `FiscalSequence`, `Invoice`, `InvoiceItem`, `InvoiceTaxComponent`, `CreditNote`, `CreditNoteItem`, `Dispatch`, `DispatchItem`.
- **Exposes:** `IssueInvoiceFromOrder`, `RenderInvoicePdf`, `RecordDispatch`, `IssueCreditNote`.
- **Depends On:** `IAM`, `SalesCatalog` (factory & buyer state/GSTIN, HSN/rate), `Orders` (transition `Approved -> Invoiced -> Dispatched`), `Inventory` (post `DISPATCH_OUT` / `CREDIT_RETURN_IN` & release reservation), `Payments` (create/adjust `CustomerReceivable`), `Audit`.

### Module 5: Purchasing & Supplier Management (`Purchasing`)
- **Responsibility:** Maintain supplier master records, optional Purchase Orders (`PO`), and goods/material Purchase Receipts (`PUR`), validating unit conversions and feeding incoming material stock and cost rates into Inventory.
- **Owns:** `Supplier`, `PurchaseOrder`, `PurchaseOrderItem`, `PurchaseReceipt`, `PurchaseReceiptItem`.
- **Exposes:** `CreatePurchaseOrder`, `ApprovePurchaseOrder`, `RecordPurchaseReceipt`.
- **Depends On:** `IAM`, `ProductionAndBom` (reads `Material` master & `UnitConversion`), `Inventory` (posts `PURCHASE_IN` ledger + `CostLot`), `Audit`.

### Module 6: Inventory Management (`Inventory`)
- **Responsibility:** Serve as the single authoritative gatekeeper for all Raw Material, Packaging Material, and Finished Goods stock balances, source-linked `InventoryMovement` ledger rows, `CostLot` valuation layers (FIFO / Weighted Average), soft stock reservations, and logged `StockAdjustment` reconciliations.
- **Owns:** `InventoryBalance`, `InventoryMovement`, `CostLot`, `StockAdjustment`.
- **Exposes:** `GetAvailability(item)`, `ReserveFinishedStock(order_id, lines)`, `ReleaseFinishedReservation(order_id)`, `PostPurchaseReceiptMovements`, `PostProductionIssues` *(returns consumed cost)*, `PostProductionOutput`, `PostDispatchDeduction`, `PostCreditReturn`, `PostStockAdjustment`, `ReconcileBalancesFromLedger`.
- **Depends On:** `IAM`, `SalesCatalog` (read Product ref), `ProductionAndBom` (read Material & UOM conversion rules), `Audit`. *(Never writes directly to Orders, Billing, or Production tables.)*

### Module 7: Production & BOM Management (`ProductionAndBom`)
- **Responsibility:** Own `Material` definitions, `UnitConversion` rules, shared `RecipeTemplate`s, versioned `BillOfMaterials` (`BomVersion`), and `ProductionRun` execution (issuing raw materials, recording good output, process scrap, and damaged packaging, and computing consumption & yield variances against tolerance).
- **Owns:** `Material`, `UnitConversion`, `RecipeTemplate`, `BillOfMaterials`, `BomVersion`, `BomItem`, `ProductionRun`, `ProductionMaterialIssue`.
- **Exposes:** `CreateBomVersion`, `ConvertToCanonicalUnit`, `StartProductionRun`, `CompleteProductionRun`, `CancelProductionRun`, `CorrectCompletedRun`.
- **Depends On:** `IAM` (tolerance settings), `SalesCatalog` (read finished `Product` ref), `Inventory` (checks & posts `PROD_ISSUE_OUT`, `PACKAGING_DAMAGE_OUT`, `PROD_OUTPUT_IN`, `PROD_RETURN_IN`), `Costing` (passes consumed material cost & triggers costing calculation), `ReportingAndAudit` (raises `VarianceAlert` & `AuditLog`).

### Module 8: Costing (`Costing`)
- **Responsibility:** Capture direct production run overheads (`Labour`, `Gas/Power`) and optional monthly factory overhead pools; combine absorbed material + packaging (including damaged packaging) + overhead costs to calculate `Cost per Good Packet` and gross margin against selling price.
- **Owns:** `ProductionOverhead`, `ProductionCostSummary`.
- **Exposes:** `RecordRunOverheads`, `AllocateMonthlyOverheads`, `ComputeRunCostSummary`, `GetLatestSkuCostAndMargin`.
- **Depends On:** `IAM`, `SalesCatalog` (selling price reference), `ProductionAndBom` (run good output & material issue costs), `Audit`.

### Module 9: Payments & Receivables (`Payments`)
- **Responsibility:** Record customer payments, prevent duplicate entry/over-allocation, allocate receipts to posted invoices, track customer advances, and maintain real-time invoice and customer `CustomerReceivable` balances for AR Ageing.
- **Owns:** `Payment`, `PaymentAllocation`, `CustomerReceivable`.
- **Exposes:** `CreateReceivableFromInvoice`, `AdjustReceivableFromCreditNote`, `RecordAndAllocatePayment`, `ReversePayment`, `GetCustomerOutstanding`.
- **Depends On:** `IAM`, `SalesCatalog` (customer ref), `Billing` (invoice totals & payment status updates), `Audit`.

### Module 10: Reporting & Audit (`ReportingAndAudit`)
- **Responsibility:** Provide strictly read-only monthly statutory and audit query views (Sales Register, GSTR-1/3B Outward Summary, Purchase Register, Stock Summary & Ledger drill-down, Production Variance & Costing Report, Collections & AR Ageing), Owner executive KPIs, active `VarianceAlert` management, and immutable `AuditLog` persistence.
- **Owns:** `AuditLog`, `VarianceAlert` *(plus read-only projection queries across Modules 2–9)*.
- **Exposes:** `AppendAuditLog`, `RaiseVarianceAlert`, `AcknowledgeVarianceAlert`, `QueryMonthlyAuditPack`, `ExportCsvExcel`, `ExportReportPdf`, `GetOwnerDashboardKpis`.
- **Depends On:** Read-only read access to `SalesCatalog`, `Orders`, `Billing`, `Purchasing`, `Inventory`, `ProductionAndBom`, `Costing`, `Payments`. *(Strictly zero write operations on operational modules!)*
