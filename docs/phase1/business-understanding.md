# Business Understanding — Order-to-Audit Management System

**Source Basis:** Official Problem Statement (`Problem Statement - Winter Internship Application - 2026.docx`, Centre for Digital Infrastructure, NIT Tiruchirappalli)  
**Document Status:** Phase 1 — Business Discovery & Requirements Engineering (No schema or code yet)

---

## 1. Domain Context & Core Business Problem

### 1.1 Company Profile (Fictional Domain)
- **Business Type:** Small-scale packaged South Indian snack manufacturer operating **one factory** (located in **Tamil Nadu** per the Section 5 benchmark).
- **Product Portfolio:** Packaged snacks across pack sizes — e.g., **Murukku 200 g** (benchmark SKU), mixture, chips, and sweets, sold to **retailers** (e.g., Retailer A in Tamil Nadu) and **distributors** (e.g., Distributor B in Karnataka).
- **Sales Force:** **5–15 field salesmen** visiting retail shops and regional distributors on mobile phones, frequently under weak or intermittent cellular connectivity.
- **Factory Staff & Governance:** Admin/billing desk, production floor supervisor(s), business owner, and an external accountant/auditor.

### 1.2 Pain Points in the Current Manual Operation (Official Problem Statement, Section 1)
1. **Fragmented Order Capture:** Field salesmen phone in or WhatsApp orders to the factory desk; admin staff manually re-type them into billing software, causing transcription mistakes, missed orders, and pricing errors.
2. **Disconnected Stock & Production Records:** Tax invoices sit in one billing tool, inventory balances live in paper notebooks or ad-hoc spreadsheets, and daily production runs are written on paper logs.
3. **Invisible Wastage & Unknown Unit Cost:** Nobody can rapidly compare **planned raw material** (from a recipe) against **actual material issued** or **expected packet yield** against **actual good packets packed**, hiding oil/flour shrinkage, damaged pouches, and true **cost per packet**.
4. **Month-End Audit Scramble:** At month-end, staff manually reconcile sales registers, GST outward tax figures, stock balances, purchases, and customer collections for the external accountant and auditor.

### 1.3 Target Operational Model: Single-Entry, Two Linked Loops (Section 2)
Every business event is captured **once at its origin** and automatically drives downstream inventory, costing, receivables, and audit reporting without requiring third-party accounting tools (such as Tally) for daily operations:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              SALES LOOP                                    │
│  Field Order (Mobile) ─► Admin Verification ─► GST Tax Invoice ─► Dispatch │
│         (No stock impact)      (Stock check)       (AR created)   (FG -qty)│
└───────────────────────────────────────────────────────────────────────┬────┘
                                                                        ▼
                                                        ┌────────────────────┐
                                                        │  FINISHED GOODS    │
                                                        │   STOCK LEDGER     │
                                                        └───────────────▲────┘
┌───────────────────────────────────────────────────────────────────────┴────┐
│                           PRODUCTION LOOP                                  │
│  RM Purchase ─► RM Stock (+qty) ─► BOM Issue ─► Production Run ─► FG (+qty)│
│                                      (RM -qty)   (Yield & Variance + Cost) │
└────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                        MONTH-END AUDIT & COSTING                           │
│  Sales & GSTR-1/3B Summary │ Stock Ledger │ Variance │ Cost/Packet │ AR    │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Plain-Language & Technical Glossary of Key Domain Terms

| Term | Plain-Language Explanation | Technical / Accounting Meaning |
| --- | --- | --- |
| **Bill of Materials (BOM)** | The standard factory recipe showing exactly how much ingredient and packaging is needed to make one batch of snack packets. | A versioned master recipe defining input items, quantities, units of measure, and expected yield (`packets per batch`) for a finished product SKU. |
| **SKU (Stock Keeping Unit)** | A specific sellable product and pack size (e.g., *Murukku 200 g* is a different SKU from *Murukku 500 g*). | A uniquely coded finished-goods inventory item carrying its own price, HSN code, GST rate, pack weight, carton pack ratio, and ledger balance. |
| **Stock Ledger** | A bank passbook for factory goods: instead of overwriting "how much is left", every addition and subtraction is written down with a reason. | An append-only (or strictly source-linked) transaction log where closing balance equals `Opening + Receipts - Issues/Sales ± Adjustments`, traceable to a source document. |
| **Yield Variance** | Making fewer (or more) packets than the recipe promised from one batch of ingredients. | `(Actual Good Packets - Expected Batch Packets) / Expected Batch Packets × 100%`; negative values indicate production output loss. |
| **Consumption Variance** | Using more (or less) raw material or packaging than the recipe specified (e.g., using 10.5 L oil instead of 10 L). | `(Actual Quantity Issued - Planned Quantity) / Planned Quantity × 100%`; positive values indicate excess material usage or wastage. |
| **HSN Code** | A standardized government product code printed on Indian GST invoices to classify goods and tax rates. | Harmonized System of Nomenclature code (typically 4–8 digits) required on B2B/B2C GST tax invoices and GSTR-1 summaries. |
| **GSTIN** | A business's 15-character tax registration number used to identify the seller and registered buyers. | Goods and Services Tax Identification Number; the first two digits denote state code (e.g., `33` for Tamil Nadu, `29` for Karnataka), governing place-of-supply tax split. |
| **CGST / SGST vs IGST** | When selling inside the same state (Tamil Nadu -> Tamil Nadu), GST splits 50/50 between Central and State tax; across states (Tamil Nadu -> Karnataka), one combined Integrated tax applies. | Intra-state supplies charge `CGST (rate/2) + SGST (rate/2)`; inter-state supplies charge `IGST (full rate)` determined by supplier state vs buyer place of supply. |
| **Credit Note** | A formal negative invoice issued to cancel or reduce a previously finalized tax invoice instead of erasing it. | An immutable GST adjustment document referencing the original tax invoice that reverses revenue, tax liability, and customer receivable without breaking invoice sequence or audit history. |
| **Receivables & Ageing** | Money customers still owe us, grouped by how many days overdue the bills are (0–30, 31–60, 61–90, 90+ days). | Accounts Receivable (`AR = Invoiced Amount - Allocated Payments - Credit Notes`) bucketed by days elapsed from invoice date or due date. |
| **FIFO vs Weighted Average** | Two ways to price flour used in production when older bags cost ₹42/kg and newer bags cost ₹45/kg: FIFO uses the ₹42 price first; Weighted Average blends them to ₹43.125/kg. | Inventory valuation methods under accounting standards (Ind AS 2 / AS 2): First-In-First-Out consumes oldest receipt cost layers first; Moving Weighted Average recalculates average unit cost upon each receipt. |
| **Integer-Paisa Arithmetic** | Storing ₹7,875.00 as `787500` paise (whole numbers) or exact fixed decimals so computer binary floats never lose 1 paisa. | Using integer minor currency units (`1 INR = 100 paise`) or arbitrary-precision `Decimal` rather than IEEE 754 binary floating-point (`float`), with explicit deterministic rounding (`ROUND_HALF_UP`). |

---

## 3. Actors, Responsibilities & System Interactions

| Actor | Primary Context | Core Operational Responsibilities | Key Interactions with Other Actors |
| --- | --- | --- | --- |
| **Field Salesman** | On the road visiting retailers & distributors (mobile, weak network) | Select customer, pick SKUs and quantities using active price list, submit orders directly to factory, monitor own order progress, view customer-wise sales totals. | Submits orders into central backend for **Factory Admin**; relays dispatch/invoice status or shared PDF invoice to **Customers**. |
| **Factory Admin (Billing & Dispatch Desk)** | Factory office (desktop) | Monitor incoming salesman orders; verify customer, prices, and finished-goods stock coverage; edit/approve/reject orders; generate GST invoices (PDF) and share; record dispatch; record customer payments; issue credit notes if cancelling posted invoices. | Reviews orders from **Salesmen**; checks finished goods produced by **Production Supervisor**; creates accounting/GST records reviewed by **Accountant/Auditor**. |
| **Production Supervisor** | Factory production floor (tablet/desktop) | Record raw-material and packaging receipts from suppliers (purchases); issue raw materials & packaging to production runs; log actual good packets, damaged packaging, and wastage; view BOM targets and variance flags. | Replenishes raw material stock from **Suppliers**; increases finished-goods stock available for **Factory Admin** sales approvals; logs run labour/gas inputs. |
| **Accountant / Auditor** | Office / External practice (desktop, read-only) | Inspect and export monthly sales register, GSTR-1/3B summary, purchase register, stock summary & movement ledger, production variance report, cost-per-packet analysis, and AR ageing without altering operational data. | Audits all transactions created by **Salesman**, **Factory Admin**, and **Production Supervisor**; flags anomalies to **Owner** / **Factory Admin**. |
| **Owner** | Any device (responsive executive view) | Monitor daily snapshot: today's order intake, raw & finished stock levels, production variance alerts, unit cost & margin per packet, and outstanding receivables. | Reviews KPIs and variance alerts across **Sales**, **Production**, and **Finance**; sets pricing, overhead rates, and variance tolerances (via Admin or Owner controls). |
| **External Entities (Non-Login)** | Counterparties | **Customers (Retailers / Distributors):** Place demand orders via salesman, receive GST tax invoice PDF & dispatched goods, remit payments.<br>**Suppliers:** Supply raw & packaging materials recorded via purchases/receipts. | Transacted against by **Salesman**, **Factory Admin**, and **Production Supervisor**. |

---

## 4. Business Entities & Business Documents Identification (Conceptual Model — No DB Schema Yet)

Per Phase 1 scope, the following identifies the core **master entities**, **transactional documents**, and **derived ledgers/records** without finalizing table layouts, keys, or migrations.

### 4.1 Master Data Entities
1. **User & Role Principal:** Identity, credentials, assigned role (`Salesman`, `Factory Admin`, `Production Supervisor`, `Accountant/Auditor`, `Owner`), active status, linked salesman territory/profile if applicable.
2. **Company / Factory Profile (Tenant Settings):** Legal business name, factory address, state (`Tamil Nadu`, code `33`), GSTIN, financial-year invoice prefix rules, default variance tolerance (e.g., `3%`), default costing method.
3. **Customer:** Customer code, legal/trade name, type (`Retailer` | `Distributor`), billing/shipping address, **State & State Code** (place of supply — mandatory for CGST/SGST vs IGST), GSTIN (optional for unregistered small retailers, required for registered B2B), assigned salesman (or territory), credit terms/days (optional for ageing), active flag.
4. **Supplier:** Supplier code, name, contact details, state, GSTIN (optional), active flag.
5. **Item / Material Master (Raw & Packaging Materials):** Item code, name (e.g., Flour, Cooking Oil, Salt & Spice Mix, 200 g Pouch, Carton), category (`Raw Material` | `Packaging Material`), base unit of measure (`kg`, `litre`, `piece`), purchase/conversion unit rules, reorder level (stretch), opening quantity & opening unit cost rate.
6. **Finished Product (SKU):** Product code, name (e.g., `Murukku 200 g`), pack weight (`200 g`), base selling unit (`packet`), secondary pack conversion (`1 carton = 20 packets`), HSN code, GST tax slab (`5%`), standard selling price before tax (`₹50.00`), opening finished quantity & opening cost rate (assumed/seeded), active flag.
7. **Price List / Customer Price Override (Optional):** Effective price per SKU (standard price list mandatory; customer-specific price or promotional scheme optional per Section 4.1).
8. **Bill of Materials (BOM):** Recipe header tied to a Finished Product (or bulk base recipe + pack-size packaging BOM — see Architectural Note on 500 g pack size in `reference-analysis.md`), version number, effective status, expected batch output (`200 packets`), and **BOM Line Items** (material/packaging item, standard quantity per batch, unit of measure).

### 4.2 Transactional Business Documents
1. **Sales Order (`ORD`):** Initiated by Salesman; captures customer, salesman, order date, client idempotency reference, status (`SUBMITTED`, `APPROVED`, `REJECTED`, `CORRECTION_REQUESTED`, `INVOICED`, `DISPATCHED`, `CANCELLED`), order lines (SKU, ordered qty, quoted unit price, line total), shortage/stock-check snapshot, and approval/rejection notes.
2. **Purchase / Material Receipt (`PUR` / `GRN`):** Initiated by Production Supervisor or Factory Admin; captures supplier, invoice/challan reference, receipt date, lines (raw/packaging item, qty received, unit, unit cost rate, optional input GST), driving positive stock ledger entries and cost-layer/weighted-average updates.
3. **Production Run (`PRD`):** Initiated by Production Supervisor; references Finished Product & BOM version, batch multiplier / planned output (`200 packets`), run status (`IN_PROGRESS` | `COMPLETED` | `CANCELLED`), **Material Issue / Consumption Lines** (planned qty vs actual issued qty, unit, variance %), **Output & Wastage Summary** (actual good packets, process scrap/wastage notes, damaged packaging count), **Direct Overheads** (labour, gas/power), and computed unit cost per good packet.
4. **GST Tax Invoice (`INV`):** Generated by Factory Admin from an approved Sales Order; carries immutable Financial-Year sequence number (`INV/2026-27/0001`), seller GSTIN/state, buyer GSTIN/place-of-supply state, line items (HSN, qty, unit price, taxable value), tax split (`CGST + SGST` vs `IGST`), total invoice value, payment status (`UNPAID`, `PARTIALLY_PAID`, `PAID`, `CANCELLED`), and generated PDF artifact.
5. **Credit Note (`CN`):** Generated by Factory Admin only to cancel or adjust a posted GST Tax Invoice; references original `INV` number, FY sequence number (`CN/2026-27/0001`), reason, reversed taxable value and tax amounts, and optional stock-return link if goods were already dispatched.
6. **Dispatch Note / Delivery Challan (`DSP`):** Recorded by Factory Admin against an invoiced (or approved) order; captures dispatch date, carrier/vehicle/LR details, dispatched lines & quantities, triggering the finished-goods **stock deduction**.
7. **Payment Receipt (`PMT`):** Recorded by Factory Admin against a customer and allocated to one or more posted invoices; captures payment date, amount, payment mode (Cash / UPI / NEFT / Cheque), reference number, and updated invoice/customer outstanding balance.

### 4.3 Immutable Ledger & Governance Records
1. **Inventory Stock Ledger (`STK-LEDGER`):** Every physical stock change across Raw Materials, Packaging Materials, WIP (if modelled), and Finished Goods creates an immutable movement entry: timestamp, item, location/bucket (optional lot/batch), movement type (`OPENING`, `PURCHASE_IN`, `PROD_ISSUE_OUT`, `PROD_OUTPUT_IN`, `PACKAGING_DAMAGE_OUT`, `DISPATCH_OUT`, `CREDIT_RETURN_IN`, `ADJUSTMENT`), signed quantity delta, unit cost / total valuation impact, running or reconcilable balance, acting user, and **mandatory source document reference** (`PUR`, `PRD`, `DSP`, `CN`, `ADJ`).
2. **Costing & Overhead Record (`COST-RUN`):** Links production run material consumption valuation, packaging consumption (including damaged units), and allocated direct/monthly overheads to produce batch total cost, cost per good packet, and gross margin vs selling price.
3. **Audit Trail Log (`AUD-LOG`):** Chronological, tamper-evident log recording actor, role, timestamp, entity/document type, document ID, action (`CREATE`, `EDIT`, `APPROVE`, `REJECT`, `CANCEL`, `OVERRIDE`), reason, and field-level before/after JSON snapshots (especially mandatory for edits to invoices, production runs, prices, and stock adjustments).

---

## 5. Clear Distinction: Official Scope vs Assumptions

- **Official Problem Statement Mandates:** Two linked loops (Sales + Production), 5 user roles (with at least 3 in Must-have minimum), BOM recipe + planned-vs-actual consumption/yield + variance alerts, unit conversion (`kg/g/litres/pieces/packets/cartons`), ledger-backed stock with source traceability, decimal/integer-paisa math, GST invoice PDF + FY numbering + CGST/SGST vs IGST + Credit Note cancellation, audit logs on edits to invoices & production runs, Section 5 benchmark reproducibility via seed data, and auditor exports (Excel/CSV + PDF).
- **Documented Engineering Assumptions (Detailed in `business-rules.md` & `benchmark-analysis.md`):** Exact status transitions, stock reservation on approval vs deduction at dispatch, raw material valuation method selection (FIFO vs Weighted Average), handling of damaged packaging in unit cost & consumption variance, opening finished-goods valuation, and offline retry/idempotency boundaries between Must-Have and Stretch.
