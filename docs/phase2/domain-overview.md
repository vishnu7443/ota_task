# Domain Overview — Strategic DDD & System Architecture

**Phase:** Phase 2 — Domain Modelling & System Architecture  
**Approved Baseline:** Phase 1 Deliverables (`docs/phase1/*.md`) & Official NIT Tiruchirappalli CDI Winter Internship 2026 Problem Statement  
**Constraint Notice:** Conceptual domain model and modular architecture only. Technology selection, physical database DDL, migrations, and implementation code are deferred until Phase 2 approval.

---

## 1. Strategic Domain Classification

The Order-to-Audit system unifies two tightly coupled factory loops — **Sales-to-Collection** and **Purchase-to-Production-to-Costing** — meeting at **Finished Goods Inventory** and feeding **Audit & Statutory Reporting**. Using Domain-Driven Design (DDD), subdomains are classified by competitive/evaluation weight (Problem Statement Section 2 & Section 9):

| Subdomain | DDD Type | Evaluation Weight & Business Rationale |
| --- | --- | --- |
| **Production, BOM & Variance Engine** | **Core Domain** | Highest differentiator (`20%` design + core of `30%` benchmark). Handles versioned recipes, multi-pack BOM sharing (`200 g` / `500 g`), exact unit conversions, damaged packaging, and `>3%` tolerance alerts. |
| **Ledger-Driven Inventory & Costing** | **Core Domain** | Backbone linking both loops (`30%` benchmark + `20%` design). Enforces immutable source-linked stock movements, concurrent reservation safety, FIFO cost-lot depletion, and true packet unit cost + margin. |
| **Order-to-Cash & GST Billing** | **Core / Supporting** | `15%` evaluation weight + mobile usability (`10%`). Mobile order capture with weak-network idempotency, stock-checked approvals, place-of-supply GST (`CGST+SGST` vs `IGST`), FY sequences, Credit Notes, dispatch, and AR collections. |
| **Reporting & Audit Trail** | **Supporting (Statutory)** | `10%` evaluation weight. Zero-drift read models over immutable posted records (Sales Register, GSTR-1/3B summary, Stock Ledger, Production Variance, AR Ageing) + field-level `AuditLog`. |
| **Purchasing & Supplier Intake** | **Supporting** | Feeds raw/packaging receipts and cost layers into Inventory. |
| **Identity & Access Management (IAM)** | **Generic / Supporting** | Strict 5-role RBAC (`Salesman`, `Factory Admin`, `Production Supervisor`, `Accountant/Auditor`, `Owner`) with record-level scoping and read-only audit protection. |

---

## 2. Ubiquitous Language (Canonical Domain Terms)

All modules, diagrams, and Phase 3 code must adhere strictly to these canonical terms:

- **Material:** An input commodity purchased from a supplier (`RAW_MATERIAL` such as Flour, Oil, Spice Mix; or `PACKAGING_MATERIAL` such as 200 g Pouch, Carton).
- **Product (SKU):** A finished sellable item at a specific pack size (e.g., `Murukku 200 g`, `Murukku 500 g`), priced per `packet` and optionally packed `N packets per carton`.
- **Recipe Template vs BOM Version:** A `RecipeTemplate` holds the shared base cooking formulation (e.g., `40 kg` flour + `10 L` oil + `1.2 kg` spice -> `40 kg` bulk murukku); a `BomVersion` binds that recipe (or direct ingredients) + SKU-specific packaging (`200` pouches, `10` cartons) into an immutable versioned standard for `expected_yield_packets`.
- **On-Hand vs Reserved vs Available Stock:**
  - `On-Hand` = exact sum of all posted `InventoryMovement` records for an item.
  - `Reserved` = soft allocation held by `Approved` / `Invoiced` orders awaiting dispatch.
  - `Available` = `On-Hand - Reserved` (the quantity available to approve new orders).
- **Inventory Movement (Ledger Entry):** An immutable, signed, unit-normalized record tied to a `source_document_type` and `source_document_id`.
- **Cost Lot:** A receipt-originated valuation slice (`remaining_qty_base`, `unit_cost_paisa`) enabling exact FIFO material depletion (and future batch/expiry FEFO).
- **Posting / Posted:** The irreversible transition of a business document (`Invoice`, `CreditNote`, `PurchaseReceipt`, `ProductionRun`) into the official financial/stock ledger; cancellations after posting require compensating documents (`CreditNote`, `StockAdjustment`), never deletion.
- **Paisa:** Exact integer minor currency unit (`₹1.00 = 100 paise`), representing all monetary amounts without binary floating-point rounding drift.

---

## 3. Bounded Context Map (Modular Monolith)

```
┌──────────────────────────┐        ┌──────────────────────────────────────────┐
│  Identity & Access (IAM) │◄───────│       All Operational Modules            │
│  User, Role, Company     │ AuthZ  │  Enforce Role + Ownership + Audit Actor  │
└──────────────────────────┘        └──────────────────────────────────────────┘

┌──────────────────────┐    Approved     ┌──────────────────────┐
│ Customer & Sales Mgmt│───►Order Qty───►│   Order Management   │
│ Customer, Product,   │                 │ SalesOrder,          │
│ PriceList            │                 │ SalesOrderItem       │
└──────────┬───────────┘                 └──────────┬───────────┘
           │ State/Tax Slab                         │ OrderApproved
           ▼                                        ▼
┌──────────────────────┐    Invoice      ┌──────────────────────┐
│    Billing & GST     │◄───Generated────│ Inventory Management │
│ Invoice, CreditNote, │                 │ InventoryBalance,    │
│ Dispatch, FiscalSeq  │───Dispatch Out─►│ InventoryMovement,   │
└──────────┬───────────┘                 │ CostLot, Adjustment  │
           │                             └──────────▲───────────┘
           │ Receivable                             │
           ▼                                        │ RM Out / FG In
┌──────────────────────┐                 ┌──────────┴───────────┐
│Payments & Receivables│                 │  Production & BOM    │
│ Payment, Allocation, │                 │ RecipeTemplate, BOM, │
│ CustomerReceivable   │                 │ ProductionRun, Issue │
└──────────┬───────────┘                 └──────────┬───────────┘
           │                                        │ Cost Inputs
           │                             ┌──────────▼───────────┐
           │                             │       Costing        │
           │                             │ ProductionOverhead,  │
           │                             │ ProductionCostSummary│
           │                             └──────────┬───────────┘
           │      ┌──────────────────────┐          │
           │      │Purchasing & Suppliers│──────────┘ (Receipt + CostLot)
           │      │ Supplier, PO, Receipt│
           │      └──────────────────────┘
           ▼                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                  Reporting & Audit (Read Models + AuditLog)                  │
│   Sales/GSTR-1/3B, Purchases, Stock Ledger, Variance/Costing, AR Ageing      │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Architectural Style Decision Summary

The system is architected as a **Domain-Modular Monolith** backed by a single **ACID transactional relational data store**. For a single-factory SME with 5–15 salesmen, synchronous in-process module calls and atomic cross-module transactions (e.g., Production Run completion updating Raw Stock, Packaging Stock, Finished Stock, Variances, and Costing inside **one ACID transaction**) eliminate distributed eventual-consistency failures while preserving clean bounded-context seams for future extraction if the business expands to multiple factories.
