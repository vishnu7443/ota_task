# System Functional & Technical Requirements

**Source Basis:** Official Problem Statement Sections 3, 4, 6, 7, 8, 9  
**Classification Tiers:**
- **Must Have (`FR-M-*`)** — Minimum required for evaluation consideration (Section 6 + core Section 4 & 7 invariants).
- **Should Have (`FR-S-*`)** — Expected for strong production completeness and full benchmark costing/AR depth.
- **Stretch Goals (`FR-G-*`)** — Bonus enhancements implemented only after all Must-Haves and Should-Haves pass cleanly.
- **Technical & Quality Mandates (`NFR-*`)** — Non-negotiable architectural requirements from Section 7.

---

## 1. Must-Have Requirements (`FR-M-*`)

| Req ID | Requirement Description | Responsible Role(s) | Workflow Link | Expected Observable Result in Application |
| --- | --- | --- | --- | --- |
| **FR-M-01** | Role-based authentication & isolated views (`SALESMAN`, `FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR`, plus `ACCOUNTANT_AUDITOR` & `OWNER` in full RBAC). | All Roles | `WF-A`, `WF-B`, `WF-C` | Logging in routes user strictly to their role home screen; unauthorized route/API calls return `403 Forbidden`. |
| **FR-M-02** | Master data management for Finished Products (incl. HSN, GST %, unit, carton pack size, selling price), Customers (incl. State, GSTIN, type), Raw/Packaging Materials, and versioned BOMs. | Factory Admin, Production Supervisor | `WF-A`, `WF-B` | Admin/Supervisor can create/edit masters and BOM recipes; price/BOM changes preserve historical document snapshots. |
| **FR-M-03** | Seed loader for Section 5 Benchmark Master Data (`Murukku 200 g`, BOM, opening balances, Retailer A, Distributor B, Salesmen A & B). | System / Admin | Benchmark | Running single seed command populates exact Section 5 opening data reproducibly so evaluators can re-run the benchmark. |
| **FR-M-04** | Mobile-first Salesman order entry: select customer, add SKUs & quantities using active price list, review summary, and submit directly to factory in `< 1 min`. | Salesman | `WF-A` (A1–A4) | Order transitions to `SUBMITTED` immediately on Admin queue with client idempotency key preventing duplicate orders; no stock deducted yet. |
| **FR-M-05** | Salesman order status tracking (`SUBMITTED`, `APPROVED`, `INVOICED`, `DISPATCHED`, `REJECTED`, `CORRECTION_REQUESTED`) and own customer-wise sales view. | Salesman | `WF-A` (A10) | Salesman sees live badge updates on own orders and totals per customer; cannot view other salesmen's data or factory cost figures. |
| **FR-M-06** | Admin incoming order queue with real-time stock coverage check (`On-Hand`, `Reserved`, `Available`, `Shortage Qty`), inline qty/price edit (audit-logged), Request Correction, Approve, or Reject. | Factory Admin | `WF-A` (A5–A6) | Orders with sufficient stock approve cleanly and reserve stock; insufficient stock (`120` vs `88`) displays exact shortage (`32 packets`) and blocks blind negative-stock approval. |
| **FR-M-07** | GST-compliant Tax Invoice generation from approved orders: FY sequential invoice number, Seller & Buyer GSTIN, HSN code, taxable value, automatic `CGST + SGST` (intra-state) vs `IGST` (inter-state) by Place of Supply, and downloadable PDF + customer share link (WhatsApp/email). | Factory Admin (viewable by Salesman/Auditor) | `WF-A` (A7) | Invoice `INV/2026-27/0001` posts immutably (`₹7,500 + ₹187.50 + ₹187.50 = ₹7,875`); PDF downloads cleanly; WhatsApp/email share action opens pre-filled share summary/link. |
| **FR-M-08** | Dispatch recording linked to invoiced/approved orders, automatically deducting Finished Goods inventory via Stock Ledger and releasing reservation. | Factory Admin | `WF-A` (A8) | Recording dispatch (`150` pkts) writes `-150` `DISPATCH_OUT` ledger row and drops Finished Goods from `238` to `88`. |
| **FR-M-09** | Posted invoice cancellation via Credit Note (never hard-delete), reversing receivable and GST liability (plus optional stock return). | Factory Admin | `WF-A` | Cancelling posted invoice creates `CN/2026-27/0001`; original invoice stays visible marked `CANCELLED_BY_CN` in registers & audit trail. |
| **FR-M-10** | Production Run management: start run from BOM, issue raw materials (`Flour`, `Oil`, `Spice`), record actual good packets, wastage, and damaged packaging (`pouches`, `cartons`), automatically deducting RM/Packaging and adding Finished Goods in Stock Ledger. | Production Supervisor | `WF-B` (B2–B4) | Saving/completing run deducts `40 kg` flour, `10.5 L` oil, `1.2 kg` spice, `194` pouches (`188 + 6`), `9` cartons, and adds `+188` packets Murukku 200 g atomically. |
| **FR-M-11** | Exact multi-unit conversion engine supporting `kg <-> g`, `litres <-> ml`, `pieces`, `packets`, and `cartons` (`1 carton = N packets`). | Production Supervisor, System | `WF-B`, `WF-A` | Entering `1.2 kg` or `1200 g` converts without rounding error; `kg` vs `litre` mismatch is rejected cleanly. |
| **FR-M-12** | Planned vs Actual consumption and yield variance calculation with configurable tolerance threshold (default `3%`) and visual flagging. | Production Supervisor, Owner, Auditor | `WF-B` (B5) | Run summary highlights Oil `+5.0%` (`FLAGGED`) and Yield `-6.0%` (`FLAGGED`) in red/amber warning indicators. |
| **FR-M-13** | Ledger-based Inventory Summary & full Stock Ledger showing Opening, Receipts, Issues/Sales, Adjustments, Closing Balance, and clickable source document links across Raw, Packaging, and Finished Goods. | Admin, Supervisor, Auditor, Owner | `WF-B`, `WF-C` | Every item satisfies `Opening + Receipts - Issues/Sales ± Adjustments = Closing`; clicking any ledger row navigates to its `PUR`, `PRD`, `DSP`, or `CN`. |
| **FR-M-14** | Date-filtered Sales Register (customer-wise & product-wise) and Stock Summary/Ledger Report exportable to **CSV/Excel** and **PDF**. | Accountant / Auditor, Admin | `WF-C` (C1–C3) | Downloaded CSV/Excel/PDF files reconcile 100% to invoice and ledger totals on screen. |

---

## 2. Should-Have Requirements (`FR-S-*`)

| Req ID | Requirement Description | Responsible Role(s) | Workflow Link | Expected Observable Result in Application |
| --- | --- | --- | --- | --- |
| **FR-S-01** | Supplier master and Raw/Packaging Material Purchase Receipt recording (`PUR`), driving Stock Ledger receipts, cost layers (`FIFO` / `WAvg`), and Purchase Register. | Production Supervisor, Factory Admin | `WF-B` (B1), `WF-C` | Recording `60 kg` flour @ `₹45/kg` increases flour from `100` to `160 kg` and updates valuation layer & Purchase Register. |
| **FR-S-02** | Customer Payments recording, invoice allocation, partial payment tracking, Customer Outstanding balance, and AR Ageing (`0-30`, `31-60`, `61-90`, `90+` days). | Factory Admin, Accountant / Auditor | `WF-A` (A9), `WF-C` (C4) | Recording `₹4,000` payment updates Retailer A invoice to `PARTIALLY_PAID` and outstanding balance to `₹3,875` in AR & Ageing report. |
| **FR-S-03** | Production Costing engine: raw material valuation (`FIFO` recommended), packaging cost (incl. damaged units), direct run overheads (`Labour ₹1,200`, `Gas/Power ₹600`), optional monthly pool allocation, yielding **Cost per Packet** & **Gross Margin vs Selling Price**. | Production Supervisor, Owner, Auditor | `WF-B` (B6) | Run displays full cost breakdown (`₹5,810.00` total / `₹30.90` per packet under FIFO; margin `₹19.10` / `38.20%`) and compares planned vs actual unit cost. |
| **FR-S-04** | Outward GST Summary Report shaped for **GSTR-1 / GSTR-3B** (B2B vs B2C breakup, HSN summary, taxable value, CGST, SGST, IGST, Credit Notes) + full Production Report + Collections Report, exportable to Excel/CSV and PDF. | Accountant / Auditor, Admin | `WF-C` (C2–C4) | Auditor exports monthly GSTR summary matching `₹7,500` taxable, `₹187.50` CGST, `₹187.50` SGST cleanly. |
| **FR-S-05** | Active Variance Alerts queue beyond tolerance (`> 3%`) surfaced on Owner & Supervisor dashboards with drill-down to offending run and material/yield line. | Owner, Production Supervisor | `WF-B` (B5) | Dashboard alert banner lists `PRD-001` flags (`Oil +5%`, `Yield -6%`, `Pouches +3.19%`) until acknowledged. |
| **FR-S-06** | Executive **Owner Dashboard** (responsive mobile + desktop): today's order intake, raw & finished stock health, variance alerts, cost/margin per SKU, and total/overdue receivables. | Owner | Cross-Loop | Single-glance KPI cards + alert feed accurately reflect live transactional state. |
| **FR-S-07** | Read-only Accountant/Auditor role enforcement + Audit Trail viewer showing field-level edit history on invoices, orders, production runs, prices, and stock adjustments. | Accountant / Auditor, Owner | `WF-C` | Auditor can inspect every change (`who`, `when`, `before`, `after`, `reason`) while all mutation endpoints reject auditor requests. |
| **FR-S-08** | Partial dispatch & Sales Return workflows (optional per Section 4.2, recommended for real-world resilience). | Factory Admin | `WF-A` (A8) | Admin can dispatch `88` of `88` or split dispatch across two vehicles without exceeding invoiced qty. |

---

## 3. Stretch Goals (`FR-G-*`) — Post-Core Bonus Scope

| Req ID | Stretch Capability (Section 6) | Responsible Role(s) | Expected Observable Result |
| --- | --- | --- | --- |
| **FR-G-01** | **Offline order capture with sync (PWA + IndexedDB outbox):** Cache active customers & price list locally; queue offline orders; auto-sync upon connectivity restoration using idempotency keys. | Salesman | Turning airplane mode ON lets salesman capture an order and queue it locally; turning network ON syncs it cleanly with zero duplicates. |
| **FR-G-02** | **Batch & expiry tracking with FEFO dispatch:** Assign production batch codes (`LOT-YYMMDD-01`) & expiry dates on production completion; suggest/allocate earliest-expiring lot first at dispatch. | Production Supervisor, Admin | Stock ledger tracks batch/expiry; dispatch auto-picks earliest expiring finished batch. |
| **FR-G-03** | **Raw-material reorder levels & low-stock alerts:** Configure min stock thresholds on RM/packaging items; highlight items below threshold on Supervisor & Owner views. | Production Supervisor, Owner | Flour/oil/pouches below min level display `"LOW STOCK"` alert badge. |
| **FR-G-04** | **Production planning from pending orders:** Aggregate unfulfilled/shortage demand across pending orders (`e.g., 32 pkts short -> suggest 1 batch of Murukku 200 g`). | Production Supervisor, Admin | Production Planner widget recommends batch count needed to cover open orders. |
| **FR-G-05** | **Salesman route/visit log with optional GPS check-in.** | Salesman, Owner | Salesman taps "Check in at shop"; records timestamp & optional coordinates alongside order/no-order visit reason. |
| **FR-G-06** | **Tally-compatible XML / Voucher Excel export.** | Accountant / Auditor | Generates Tally-structured Sales & Receipt XML/Excel import file. |
| **FR-G-07** | **e-Invoice / e-Way Bill JSON payload preview (mocked IRP/NIC format).** | Factory Admin | Generates valid NIC-schema JSON export for B2B invoices / inter-state dispatches above threshold. |
| **FR-G-08** | **Tamil language interface toggle (`தமிழ்` / `English`) for floor staff & salesmen.** | Production Supervisor, Salesman | UI labels, units, and action buttons switch seamlessly to clear Tamil terminology. |

---

## 4. Technical & Architectural Mandates (`NFR-*`, Section 7)

| ID | Technical Requirement | Verification Standard |
| --- | --- | --- |
| **NFR-01** | **Real relational database with ledger-derived stock:** Closing balances must strictly reconcile with `StockLedger` movements (`Opening + Receipts - Issues/Sales ± Adjustments`). |Automated reconciliation check passes `0` drift across every item. |
| **NFR-02** | **Exact Decimal / Integer-Paisa Money Arithmetic:** Zero `float` usage for prices, taxes, costs, or payments; deterministic `ROUND_HALF_UP` to nearest paisa. | Unit tests verify tax, payment, and cost-per-packet math to exact paise. |
| **NFR-03** | **End-to-End Traceability & Immutability:** Every stock row points to source document; posted invoices cannot be deleted (Credit Note only); invoice & run edits logged with actor, timestamp, and diff. | Attempted HTTP `DELETE` on posted invoice returns `405`/`409`; edit writes `AuditLog`. |
| **NFR-04** | **Single-Command Reproducibility & Deployability:** Docker Compose (or single startup command) launches DB, seeds Section 5 benchmark data, and serves the app cleanly. | Fresh startup + seed completes deterministically with test credentials for all 5 roles. |
| **NFR-05** | **Automated Test Suite (Section 9):** Unit & integration tests covering stock ledger invariants, unit conversions, GST state tax rules, rounding, variance calculation, and full 9-step benchmark execution. | Automated tests execute cleanly and assert every Section 5 check value. |

---

## 5. Data & Document Traceability Summary (Responsibility #8)

*(Conceptual mapping only — DB schema deferred to Phase 2)*

| Business Entity / Document | Linked Requirements | Primary Authoring Role | Ledger / Audit Side Effects |
| --- | --- | --- | --- |
| **Customer & Supplier Masters** | `FR-M-02`, `FR-M-07`, `FR-S-01` | Factory Admin / Supervisor | State code governs GST; edits logged |
| **Finished Product & Price List** | `FR-M-02`, `FR-M-04`, `FR-S-03` | Factory Admin | HSN & GST % snapshot copied onto orders/invoices |
| **Material Master & Versioned BOM** | `FR-M-02`, `FR-M-10`, `FR-M-11` | Production Supervisor | Historical runs pin exact BOM version used |
| **Sales Order (`ORD`)** | `FR-M-04`, `FR-M-05`, `FR-M-06` | Salesman (create) / Admin (verify) | Approval soft-reserves FG stock; edits audit-logged |
| **Purchase Receipt (`PUR`)** | `FR-S-01`, `FR-M-13` | Production Supervisor / Admin | Writes `PURCHASE_IN` ledger + cost lot / WAvg update |
| **Production Run (`PRD`)** | `FR-M-10`, `FR-M-12`, `FR-S-03` | Production Supervisor | Writes `PROD_ISSUE_OUT`, `PACKAGING_DAMAGE_OUT`, `PROD_OUTPUT_IN` + variance + costing |
| **GST Tax Invoice (`INV`) & Credit Note (`CN`)** | `FR-M-07`, `FR-M-09`, `FR-S-04` | Factory Admin | FY sequence locked; updates Customer AR; CN reverses AR/tax |
| **Dispatch Note (`DSP`)** | `FR-M-08`, `FR-S-08` | Factory Admin | Writes `DISPATCH_OUT` ledger; releases reservation |
| **Payment Receipt (`PMT`)** | `FR-S-02` | Factory Admin | Reduces Invoice & Customer AR outstanding |
| **Stock Ledger (`STK-LEDGER`) & Audit Log (`AUD-LOG`)** | `FR-M-13`, `FR-S-07`, `NFR-01`–`NFR-03` | System (append-only) | Immutable audit & inventory source of truth |
