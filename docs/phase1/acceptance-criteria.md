# Testable Acceptance Criteria

Each criterion defines **Preconditions / Action -> Observable Expected Result** so QA, automated tests, and the live internship walkthrough can verify exact pass/fail behavior.

---

## 1. Authentication & Role-Based Access Control (`AC-AUTH`)

- **`AC-01` (Role Isolation):**
  - **Action:** Log in as `Salesman A` and attempt to view `Salesman B`'s order (`GET /orders/{orderB_id}`), BOM costs, or approve `ORD-001`.
  - **Expected Result:** UI hides all Admin/Production/Cost menus; direct API requests return `403 Forbidden` with zero data returned or mutated.
- **`AC-02` (Read-Only Auditor Enforcement):**
  - **Action:** Log in as `Accountant/Auditor` and attempt to call any create/update/approve/delete action (e.g., edit invoice, record payment, create stock adjustment).
  - **Expected Result:** UI renders zero mutation controls; any write API request fails with `403 Forbidden`.

---

## 2. Mobile Salesman Order Workflow (`AC-SALES`)

- **`AC-03` (Under-1-Minute Mobile Order Placement):**
  - **Action:** On a mobile viewport (`375px` width), `Salesman A` logs in, selects `Retailer A (Tamil Nadu)`, adds `Murukku 200 g` qty `150`, reviews summary (`₹7,500.00` before tax), and submits.
  - **Expected Result:** Order saves as `SUBMITTED`, receives ID `ORD-001`, shows confirmation screen to Salesman A, appears immediately in Factory Admin's `Pending Review` queue, and **does not** alter Finished Goods balance yet (`238` remains `238`).
- **`AC-04` (Weak-Network Retry & Duplicate Prevention):**
  - **Action:** Submit an order payload twice with the same `client_order_id` (simulating flaky network timeout + retry).
  - **Expected Result:** Backend creates strictly **one** `SalesOrder` record; the second request returns the existing order ID without duplicating line items or revenue.
- **`AC-05` (Salesman Status & Customer-Wise Tracking):**
  - **Action:** After Admin approves, invoices, and dispatches `ORD-001`, `Salesman A` opens `My Orders` and `Customer Sales`.
  - **Expected Result:** `ORD-001` badge reflects `DISPATCHED`; `Retailer A` shows `₹7,500.00` taxable / `₹7,875.00` billed under Salesman A's view; `Salesman B` cannot see `ORD-001`.

---

## 3. Admin Verification, Stock Checks, GST Invoicing & Dispatch (`AC-ADMIN`)

- **`AC-06` (Sufficient Stock Approval & Soft Reservation):**
  - **Action:** With `238` packets on hand and `0` reserved, Admin opens `ORD-001` (`150` packets) and clicks **Approve**.
  - **Expected Result:** Stock check shows `Available: 238 >= 150 (Surplus 88)`; order transitions to `APPROVED`; `Reserved = 150`, `Available = 88`; Audit Log captures approver & timestamp.
- **`AC-07` (Admin Pre-Invoice Edit Audit):**
  - **Action:** Admin edits an un-invoiced order's quantity or price with reason `"Agreed promo discount"` before approval.
  - **Expected Result:** Order updates cleanly; `AuditLog` contains an immutable entry with `actor`, `timestamp`, `before` value, `after` value, and `"Agreed promo discount"`.
- **`AC-08` (Intra-State GST Invoice & PDF Generation — TN to TN):**
  - **Action:** Admin generates GST invoice for approved `ORD-001` (`Retailer A`, Tamil Nadu, `150 × ₹50`, `5%` GST) and downloads PDF.
  - **Expected Result:** Invoice gets FY number `INV/2026-27/0001`; Taxable = `₹7,500.00`, CGST (2.5%) = `₹187.50`, SGST (2.5%) = `₹187.50`, IGST = `₹0.00`, Grand Total = `₹7,875.00`; Customer AR = `₹7,875.00`; PDF renders Seller/Buyer GSTIN, HSN, FY number, tax split, and totals cleanly; Finished Goods On-Hand is still `238` until dispatch.
- **`AC-09` (Dispatch & Finished Goods Ledger Deduction):**
  - **Action:** Admin records dispatch `DSP-001` for `INV/2026-27/0001` (`150` packets).
  - **Expected Result:** Order status -> `DISPATCHED`; Stock Ledger adds `DISPATCH_OUT -150 packets` linked to `DSP-001`/`INV/2026-27/0001`; Finished Goods On-Hand drops `238 -> 88 packets`; Reservation drops `150 -> 0`; Packaging cartons remain `21` (not double-deducted).
- **`AC-10` (Insufficient Stock Flagging & Inter-State IGST — Karnataka):**
  - **Action:** `Salesman B` submits `ORD-002` for `Distributor B (Karnataka)` for `120 packets` when `Available = 88 packets`; Admin opens `ORD-002` and attempts full approval.
  - **Expected Result:** Order is accepted on mobile (`SUBMITTED`); Admin view prominently flags **`Shortage of 32 packets`** (`120 ordered vs 88 available`); full approval is **blocked** (`409` / disabled button); preview correctly shows **IGST @ 5%** (e.g., `₹300` on `₹6,000` if 120 invoiced after production, or `₹220` on `₹4,400` if edited to 88); Finished Goods stays `88 packets`.
- **`AC-11` (Invoice Cancellation via Credit Note):**
  - **Action:** Admin attempts to hard-delete a `POSTED` invoice, then cancels it via **Credit Note**.
  - **Expected Result:** Hard-delete is rejected (`405/409`); Credit Note `CN/2026-27/0001` posts with matching reversed taxable & GST values; original invoice remains visible as `CANCELLED_BY_CN`; AR drops to `₹0` (and sellable stock restores only if Goods Return is confirmed).

---

## 4. Payments & Receivables (`AC-PAY`)

- **`AC-12` (Partial Payment & Outstanding Balance):**
  - **Action:** Admin records `₹4,000.00` payment from `Retailer A` allocated to `INV/2026-27/0001` (`₹7,875.00`), then submits the exact same payment payload again (duplicate test).
  - **Expected Result:** First entry sets invoice status to `PARTIALLY_PAID` and Retailer A outstanding to `₹3,875.00`; duplicate replay is blocked/idempotent so outstanding does **not** drop to `-₹125.00`.

---

## 5. Purchases, BOM, Production, Variance & Costing (`AC-PROD`)

- **`AC-13` (Raw Material Purchase & Cost Layer Update):**
  - **Action:** Supervisor records purchase `PUR-001` of `60 kg` Flour at `₹45.00/kg`.
  - **Expected Result:** Stock Ledger records `PURCHASE_IN +60.000 kg` linked to `PUR-001`; Flour balance moves `100 -> 160 kg`; Purchase Register shows `₹2,700.00`.
- **`AC-14` (Unit Conversion Validation):**
  - **Action:** Supervisor enters `1200 g` Spice Mix (or `10500 ml` Oil) against a BOM configured in `kg` and `L`; then attempts to enter `10 L` for Flour (`kg` item).
  - **Expected Result:** `1200 g` converts accurately to `1.200 kg` and `10500 ml` to `10.500 L` with zero rounding drift; cross-dimension `Flour in Litres` fails validation immediately.
- **`AC-15` (Production Run Execution, Damaged Packaging & Automatic Ledger Updates):**
  - **Action:** Supervisor starts `PRD-001` (`1 batch Murukku 200 g`, expected `200 pkts`), issues `40 kg` flour, `10.5 L` oil, `1.2 kg` spice mix, and completes run with `188` good packets, `6` damaged pouches, and `9` cartons used.
  - **Expected Result:** Stock balances update atomically: Flour `120 kg`, Oil `19.5 L`, Spice `3.8 kg`, Pouches `306 pcs` (`500 - 188 - 6`), Cartons `21 pcs` (`30 - 9`), Finished Murukku 200 g `238 pkts` (`50 + 188`). Every ledger entry links to `PRD-001`.
- **`AC-16` (Variance Calculation & Alert Flagging):**
  - **Action:** Inspect `PRD-001` summary and Owner Dashboard after completion.
  - **Expected Result:** Oil consumption variance shows `+5.00%` (`FLAGGED > 3%`); Yield variance shows `-6.00%` (`188 vs 200`, `FLAGGED > 3%`); Pouches wastage shows `6 damaged` (`+3.19%` vs 188 good packets, `FLAGGED`); Owner Dashboard shows active variance alerts.
- **`AC-17` (Direct Overhead Allocation & Cost per Packet):**
  - **Action:** Add `Labour ₹1,200.00` and `Gas/Power ₹600.00` to `PRD-001` and view costing breakdown.
  - **Expected Result:** Under active `FIFO` policy, Materials = `₹3,390.00`, Packaging = `₹620.00` (incl. `₹15.00` damaged pouches), Overheads = `₹1,800.00`, Total Run Cost = `₹5,810.00`, **Cost per Packet = `₹30.90`** (`₹5,810 / 188`), **Gross Margin = `₹19.10` (`38.20%`)** against `₹50.00` selling price.

---

## 6. Month-End Reports, Exports & Benchmark Parity (`AC-AUD`)

- **`AC-18` (Full Benchmark Reconciliation & Exports):**
  - **Action:** Seed benchmark master data, run Benchmark Steps 1–8 via UI/API, then log in as `Accountant/Auditor` and pull & export (`CSV/Excel` and `PDF`) all Step 9 reports.
  - **Expected Result:**
    - Every Section 5 Check value matches 100% (`120 kg`, `19.5 L`, `306 pouches`, `238 pkts`, `88 pkts`, `-6% yield`, `+5% oil`, `₹7,500 + ₹187.50 + ₹187.50 = ₹7,875`, `₹3,875` AR, `32 shortage / IGST`, `₹30.90` FIFO cost/packet).
    - Every Stock Summary row equals `Opening + Receipts - Issues/Sales ± Adjustments` computed directly from `StockLedger`.
    - Exported CSV/Excel and PDF files match on-screen numbers to the exact paisa.
