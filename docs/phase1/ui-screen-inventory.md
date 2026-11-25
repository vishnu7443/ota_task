# UI / UX Screen Inventory & Ergonomic Specifications

**Constraint Note:** Per Phase 1 rules, this document defines screen inventories, user flows, field layouts, and UX ergonomics **only** — no HTML/CSS/UI code or visual mockups are generated yet.

---

## 1. Shared Authentication (`SCR-AUTH`)

- **`SCR-AUTH-01` — Login Screen (Responsive Mobile & Desktop):**
  - Username/phone/email + password login; clear "Quick Demo Role Login" hint or documented test credentials (in non-prod demo mode).
  - Post-login smart redirect per role (`Salesman -> Mobile Order Home`, `Factory Admin -> Incoming Orders Queue`, `Production Supervisor -> Floor Production Hub`, `Accountant/Auditor -> Monthly Reports Hub`, `Owner -> Executive Dashboard`).
  - Clear connection status banner (`Online` / `Weak/Offline — Draft Protected`) on mobile devices.

---

## 2. Salesman Experience — Mobile-First (`SCR-SM-*`)

**Target UX Goal (Section 9):** Place a complete order in **under 1 minute** using one thumb on a smartphone, even on slow/flaky 3G networks.
**Navigation:** Clean 3-tab bottom bar (`New Order`, `My Orders`, `Customer Sales`). Minimal chrome, large `48px+` touch targets, sticky bottom action bar.

1. **`SCR-SM-01` — Mobile Home / Quick Customer Selector ("Start Order"):**
   - Instant search bar (search by shop name, town, or phone) + pinned "Recent / Today's Customers" list.
   - Each customer card shows: Shop Name, Type badge (`Retailer` / `Distributor`), City/State (`Tamil Nadu` / `Karnataka`), and current open dues indicator (read-only helpful context, optional).
   - One tap on customer immediately opens Product Selection (`SCR-SM-02`).

2. **`SCR-SM-02` — Product Selection & Quick-Tap Catalog:**
   - Pre-filtered active finished SKUs (e.g., `Murukku 200 g`, pack info `1 Carton = 20 Packets`, standard rate `₹50.00/pkt`).
   - Category pills (`All`, `Murukku`, `Mixture`, `Chips`, `Sweets`) + quick search.
   - Non-blocking stock availability pill (`In Stock: 238` or `Low/Backorder: 88 avail` — never blocks salesman from capturing customer demand!).
   - Inline `+` / `-` stepper AND direct numeric tap input right on the product card (eliminating unnecessary extra clicks).

3. **`SCR-SM-03` — Quantity Entry & Unit Helper Modal/Control:**
   - Supports direct **Packet** count (`150`) OR **Carton + Loose Packets** quick converter (e.g., typing `7 cartons + 10 pkts` auto-calculates `150 packets`, showing exact subtotal `₹7,500.00` live).
   - Rejects `0` or negative integers cleanly with immediate inline validation.

4. **`SCR-SM-04` — Order Summary / Cart Review:**
   - Displays selected Customer + Place-of-Supply State (`Tamil Nadu` -> Est. `CGST + SGST 5%`, `Karnataka` -> Est. `IGST 5%`).
   - Line-by-line SKU, Qty, Unit Price (`₹50.00`), Line Subtotal (`₹7,500.00`), Estimated Tax (`₹375.00`), and Estimated Order Total (`₹7,875.00`).
   - Optional delivery/order notes field (e.g., `"Urgent morning load"`).
   - Sticky primary button: **Submit Order to Factory** (plus **Save Local Draft** if network is temporarily offline).

5. **`SCR-SM-05` — Submission Confirmation & Weak-Network Retry State:**
   - **If online & succeeded:** Clear confirmation screen with Order Reference (`ORD-001`), timestamp, customer name, total value, and two 1-tap actions: *"Place Another Order"* and *"Track Order"*.
   - **If network timed out / failed:** Preserves exact payload in local storage with the same `client_order_id`, shows clear yellow banner *"Network weak — Order saved safely on phone. Tap Retry now (no duplicate will be created)"*, and triggers auto-retry when signal returns.

6. **`SCR-SM-06` — My Orders Tracker (`SCR-SM-06` + `SCR-SM-07` Detail):**
   - Filterable list by status (`All`, `Submitted`, `Action Needed / Correction`, `Approved`, `Invoiced`, `Dispatched`, `Rejected`).
   - Tapping an order opens **`SCR-SM-07` Order Detail**: timeline of status steps, Admin remarks (e.g., rejection reason or correction request), editable re-submit button **only** if status is `CORRECTION_REQUESTED`, and **Download/Share Invoice PDF** button once `INVOICED`.

7. **`SCR-SM-08` — Customer-Wise Sales Summary (Salesman View):**
   - Shows salesman's own customers ranked by order/invoiced volume for selected date range (`Month-to-date` default): Customer Name, Orders Count, Invoiced Value, and Pending/Open Orders count. (Strictly hides factory cost & margin.)

---

## 3. Factory Admin Experience — Desktop-First (`SCR-ADM-*`)

**Target UX Goal:** Zero re-typing; verify incoming orders, stock coverage, taxes, dispatch, and payments in seconds from a structured desktop workspace with left sidebar navigation.

1. **`SCR-ADM-01` — Incoming Orders Queue & Verification Workspace (Primary Landing):**
   - Tabbed status queue: `Pending Review (SUBMITTED)` (highlighted badge count), `Correction Requested`, `Approved (Ready to Invoice)`, `Invoiced (Ready to Dispatch)`, `Dispatched`, `Rejected/Cancelled`.
   - Each row displays: Order ID, Timestamp, Salesman Name, Customer Name + State (`TN` vs `KA`), Line Count, Ordered Qty, **Live Stock Coverage Pill** (`COVERED: 238 avail >= 150` in green vs `SHORT BY 32: 88 avail < 120` in red), Order Value (`₹7,500.00`).

2. **`SCR-ADM-02` — Order Review, Edit & Approval Side-Drawer / Detail View:**
   - Shows Customer details (GSTIN, State -> auto-detected tax mode `CGST+SGST` vs `IGST`), Order lines with side-by-side columns: `Ordered Qty | Available FG Stock | Shortage/Surplus | Price List Rate | Edit Price/Qty`.
   - Editing qty or price reveals mandatory **"Edit Reason"** field (writes to Audit Log).
   - Action bar:
     - **Approve & Reserve Stock** (disabled with clear banner *"Cannot approve 120 packets: only 88 available (short by 32)"* when stock is insufficient; guides Admin to Hold, Reduce Qty to `<= 88`, or Reject).
     - **Request Correction** (requires comment sent back to salesman).
     - **Reject Order** (requires rejection reason).
   - One-click follow-on action after Approval: **Generate GST Tax Invoice**.

3. **`SCR-ADM-03` — Invoices List & GST Invoice Detail / PDF Preview:**
   - Lists `POSTED` and `CANCELLED_BY_CN` invoices with FY number (`INV/2026-27/0001`), Customer, Place of Supply, Taxable, CGST/SGST/IGST, Grand Total, Paid, Outstanding, Payment Status badge, Dispatch Status badge.
   - Detail view offers: **Download GST PDF**, **Share via WhatsApp / Email** (opens pre-formatted invoice link/text), **Record Dispatch**, **Record Payment**, and **Cancel via Credit Note** (requires reason & confirmation modal; never hard-delete).

4. **`SCR-ADM-04` — Dispatch Recording Screen / Modal:**
   - Displays invoiced items & quantities (`150 packets` Murukku 200 g, `= 7 full cartons + 10 packets` helper readout), dispatch date, vehicle/transporter note, and remaining stock preview (`Before: 238 -> After: 88`).
   - Optional partial dispatch qty input (bounded `1..remaining_qty`) if enabled.

5. **`SCR-ADM-05` — Payments & Customer Receivables Desk:**
   - Record Payment form: Select Customer -> displays open invoices with remaining balance (`INV/2026-27/0001: ₹7,875.00 due`) -> enter Payment Amount (`₹4,000.00`), Mode (`Cash`/`UPI`/`NEFT`/`Cheque`), Date, Reference No.
   - Live preview: `New Invoice Balance: ₹3,875.00` before saving; duplicate-entry detection warning if same reference/amount already posted.

6. **`SCR-ADM-06` — Master Data Management Hub:**
   - Sub-tabs: `Customers`, `Suppliers`, `Finished Products & Prices`, `Raw/Packaging Materials`, `Users & Roles`.
   - Enforces valid GSTIN format (15 chars when provided) and mandatory Indian State selection (`State + Code`).

7. **`SCR-ADM-07` — Purchases & Stock Ledger Viewer:**
   - Shared capability to record Supplier Purchase Invoices (`PUR-001`) and inspect real-time Stock Summary + Stock Ledger drill-down (with source links).

8. **`SCR-ADM-08` — Operational Reports & Exports:**
   - Access to Sales, GST, Purchase, Stock, and Receivables exports (CSV/Excel & PDF).

---

## 4. Production Supervisor Experience — Tablet / Desktop Floor UI (`SCR-PRD-*`)

**Target UX Goal:** Fast, mistake-proof floor data capture with large touch controls, live unit conversion preview, and instant variance alerts.

1. **`SCR-PRD-01` — Floor Production Hub:**
   - Active/In-Progress Runs list, Today's Completed Runs, Quick KPI cards (Raw Stock Warnings, Today's Packets Packed, Active Variance Alerts), and prominent **+ Start Production Run** + **+ Receive Raw Material** buttons.

2. **`SCR-PRD-02` — Raw Material & Packaging Receipt (Purchase Entry):**
   - Select Supplier, Date, Bill/Challan Ref; add line items (Material, Quantity, Unit `kg`/`g`/`L`/`ml`/`piece`, Rate `₹`).
   - Displays exact base-unit preview (`60 kg = 60,000 g`) and new projected stock (`100 -> 160 kg`).

3. **`SCR-PRD-03` — Bill of Materials (BOM) Manager:**
   - View/create/version recipes per Finished Product: Batch Expected Output (`200 packets`), Raw Inputs (`Flour 40 kg`, `Oil 10 L`, `Spice 1.2 kg`), Packaging Inputs (`200 g pouch 200 pcs`, `Carton 10 pcs`).
   - Shows calculated **Standard Cost per Batch** & **Expected Cost per Packet**.

4. **`SCR-PRD-04` — Start Production Run & Issue Raw Materials:**
   - Pick Product (`Murukku 200 g`) and Batch Multiplier (`1` -> Expected `200 packets`).
   - Pre-populates BOM standard quantities (`40 kg`, `10 L`, `1.2 kg`), allows supervisor to adjust actual issued quantities (`10.5 L` oil) with unit selector (`L` or `ml`) and shows:
     - Live stock check (`Avail: 30 L -> Remaining: 19.5 L`).
     - Live **Consumption Variance Badge** (`+5.0% -> EXCEEDS 3% TOLERANCE` in amber/red).

5. **`SCR-PRD-05` — Complete Production Run (Output, Wastage & Overheads):**
   - Displays active `IN_PROGRESS` run summary.
   - Floor inputs: **Actual Good Packets** (`188`), **Damaged Pouches** (`6`), **Good Cartons Used** (`9`), optional **Process Scrap Weight/Notes**, plus **Direct Overheads** (`Labour ₹1,200`, `Gas/Power ₹600`).
   - Live pre-submit calculation card showing:
     - Yield Variance (`188 vs 200 = -6.0% -> FLAGGED`).
     - Packaging Deduction (`Pouches: 188 + 6 = 194 used; remaining 306`; `Cartons: 9 used; remaining 21`).
     - Resulting Finished Goods (`50 + 188 = 238 packets`) and computed **Cost per Packet (`₹30.90` FIFO)**.

6. **`SCR-PRD-06` — Floor Inventory & Variance Alerts View:**
   - Current Raw, Packaging, and Finished stock balances + Variance Alert history.

---

## 5. Accountant / Auditor Experience — Read-Only Desktop (`SCR-AUD-*`)

**Target UX Goal:** Zero-friction month-end reconciliation, auditability, and one-click CSV/Excel/PDF downloads; **no edit/create/delete buttons rendered or authorized**.

1. **`SCR-AUD-01` — Month-End Audit Hub & Period Filter:**
   - Global date-range selector (`This Month`, `Last Month`, `Financial Year`, custom `From – To`), reconciliation health badge (`Stock Ledger Balanced: PASS`), and quick links to all 6 mandatory report packs.
2. **`SCR-AUD-02` — Sales Register & Customer/Product Breakdown:** Filterable by customer, state, salesman, product, status (`POSTED` / `CANCELLED_BY_CN`); Export CSV/Excel & PDF.
3. **`SCR-AUD-03` — Outward GST Summary (GSTR-1 / GSTR-3B Shape):** B2B vs B2C summary, HSN summary table, Credit Notes section, Taxable Value, CGST, SGST, IGST totals; Export CSV/Excel & PDF.
4. **`SCR-AUD-04` — Purchase Register, Stock Summary & Traceable Stock Ledger:** Opening + Receipts − Issues/Sales ± Adjustments = Closing; clicking any row opens source document modal (`PUR`, `PRD`, `DSP`, `CN`); Export CSV/Excel & PDF.
5. **`SCR-AUD-05` — Production Variance & Costing Report:** Run-by-run Planned vs Actual material, yield %, wastage, damaged packaging, overhead breakdown, cost/packet, and margin %; Export CSV/Excel & PDF.
6. **`SCR-AUD-06` — Collections, Receivables & Ageing + Immutable Audit Trail:** Customer AR balance, `0–30 / 31–60 / 61–90 / 90+` day ageing table, plus full chronological Audit Log viewer (`who`, `when`, `entity`, `before -> after`, `reason`).

---

## 6. Owner Experience — Responsive Executive Dashboard (`SCR-OWN-*`)

1. **`SCR-OWN-01` — Executive Overview (Mobile + Desktop Responsive):**
   - **5 Core KPI Cards (Section 3):** Today's Orders (count & ₹), Current Raw & Finished Stock Summary, Active Variance Alerts (`> 3%`), Latest Cost per Packet & Gross Margin per SKU, Total & Overdue Customer Receivables (`₹3,875`).
   - **Actionable Alert Feed:** Oil `+5%` and Yield `-6%` flags from `PRD-001`, low-stock warnings, pending shortage-blocked orders (`Distributor B: short 32 pkts`).
2. **`SCR-OWN-02` — Drill-Down Reports & Governance Settings:**
   - Read-only access to all reports (`SCR-AUD-*`), plus administrative controls for Variance Tolerance % (`3.0%`), Costing Valuation Policy view, and User Role administration.
