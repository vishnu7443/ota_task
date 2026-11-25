# Financial Domain Design (Billing, GST, Receivables & Costing)

**Core Technical Rule (`NFR-02`, Section 7):** Zero binary floating-point (`float`) arithmetic for money, rates, taxes, or costs. All monetary values use exact integer **paise** (`1 INR = 100 paise`) or arbitrary-precision decimal with explicit `ROUND_HALF_UP` rounding.

---

## 1. Financial Distinction Across the Order-to-Cash Lifecycle

Interviewers routinely test whether these five numbers are conflated:

| Financial Concept | Source Entity | What It Represents | Benchmark Example (`Retailer A`) |
| --- | --- | --- | --- |
| **1. Order Value (Demand Quote)** | `SalesOrder` + `SalesOrderItem` | Commercial demand submitted by Salesman before Admin verification/tax posting. **Not** accounting revenue or AR. | `150 × ₹50.00 = ₹7,500.00` (excl. tax; est. `₹7,875.00` incl. 5% GST). |
| **2. Invoice Taxable & Grand Value** | `Invoice` (`ISSUED`) | Statutory revenue recognized on GST Tax Invoice after approval. Creates legal tax liability & Customer AR. | `₹7,500.00` taxable + `₹187.50` CGST + `₹187.50` SGST = **`₹7,875.00`**. |
| **3. Credit Note Reversal Value** | `CreditNote` (`ISSUED`) | Statutory reduction/cancellation of a posted Invoice's revenue, GST, and AR without deleting the invoice. | `₹0.00` (or `-₹7,875.00` if `INV-001` cancelled). |
| **4. Payment Received & Allocated** | `Payment` & `PaymentAllocation` | Actual cash/bank inflow from Customer, mapped to specific Invoices (or held as unallocated advance). | `PMT-001`: **`₹4,000.00`** received & allocated to `INV/2026-27/0001`. |
| **5. Outstanding Balance (AR)** | `CustomerReceivable` | Unpaid collectible legal balance remaining on posted Invoices. | `₹7,875.00 - ₹0.00 - ₹4,000.00` = **`₹3,875.00`**. |

### Fundamental Receivable Equation
$$\text{Invoice Outstanding} = \text{Invoice.grand\_total\_paisa} - \sum \text{CreditNote.total\_reversed\_paisa} - \sum \text{PaymentAllocation.allocated\_paisa}$$
$$\text{Customer Net Receivable} = \sum \text{Open Invoice Outstandings} - \text{Unallocated Customer Advance Credits}$$

---

## 2. GST Place-of-Supply & Tax Component Architecture

### 2.1 Intra-State vs Inter-State Routing
Determined deterministically by comparing `CompanyProfile.state_code` (`33` — Tamil Nadu) vs `Customer.state_code` (Place of Supply):
- **Intra-State (`customer.state_code == factory.state_code`, e.g. `Retailer A`, Tamil Nadu `33`):**
  - `supply_type = INTRA_STATE`
  - Half of total GST (`gst_rate_bps / 2`, e.g., `500 / 2 = 250 bps = 2.5%`) posts to **`CGST`**, and equal half (`250 bps = 2.5%`) posts to **`SGST`**. `IGST = 0`.
- **Inter-State (`customer.state_code != factory.state_code`, e.g. `Distributor B`, Karnataka `29`):**
  - `supply_type = INTER_STATE`
  - Full GST (`gst_rate_bps`, e.g., `500 bps = 5.0%`) posts to **`IGST`**. `CGST = 0`, `SGST = 0`.

### 2.2 Exact Integer-Paisa Tax & Rounding Rule (`EC-13`)
- Store tax rates in **basis points (`bps`)** (`5.0% = 500 bps`, `2.5% = 250 bps`).
- For each `InvoiceItem`:
  - `taxable_paisa = qty_pkts * unit_price_paisa`
  - If `INTRA_STATE`:
    - `half_bps = gst_rate_bps / 2` (assert even bps for standard GST slabs `5%, 12%, 18%, 28%`)
    - `cgst_paisa = round_half_up((taxable_paisa * half_bps) / 10000)`
    - `sgst_paisa = cgst_paisa` *(guarantees exact `CGST == SGST` symmetry!)*
    - `igst_paisa = 0`
  - If `INTER_STATE`:
    - `igst_paisa = round_half_up((taxable_paisa * gst_rate_bps) / 10000)`
    - `cgst_paisa = 0`, `sgst_paisa = 0`
- **`InvoiceTaxComponent` Aggregation:** Rolls up `InvoiceItem` rows by `(hsn_code, tax_type, rate_bps)` so GSTR-1 Table 4/7 and Table 12 (HSN summary) query directly without recalculation mismatch.

---

## 3. Financial-Year Invoice & Credit Note Numbering

- Indian Fiscal Year (`FY`) runs `April 1` to `March 31`:
  - Date `2026-11-25` -> `FY 2026-27`.
  - Date `2027-04-01` -> `FY 2027-28`.
- `FiscalSequence` locks `(doc_type, financial_year)` transactionally **only when transitioning to `ISSUED`**, generating `INV/2026-27/0001` or `CN/2026-27/0001`. Drafts or rejected orders never consume sequence numbers.

---

## 4. Production Costing & Gross Margin Model

### 4.1 Cost Accumulation per `ProductionRun`
1. **Direct Raw Material Cost:** Sum of exact `CostLot` depletions (`FIFO` primary policy) across `ProductionMaterialIssue` lines with `issue_phase = RAW_ISSUE`:
   - Benchmark `PRD-001` (FIFO): Flour (`40 × ₹42 = ₹1,680`) + Oil (`10.5 × ₹140 = ₹1,470`) + Spice (`1.2 × ₹200 = ₹240`) = **`₹3,390.00`**.
2. **Packaging Cost (incl. Damaged Units):** All pouches (`188 + 6 = 194 × ₹2.50 = ₹485.00`) + Cartons (`9 × ₹15.00 = ₹135.00`) = **`₹620.00`**.
3. **Direct Run Overheads (`ProductionOverhead`, `DIRECT_RUN`):** Labour (`₹1,200.00`) + Gas/Power (`₹600.00`) = **`₹1,800.00`**.
4. **Monthly Shared Overheads (`MONTHLY_POOL`, optional Tier 2):** If monthly factory overheads (e.g., supervisor salary/rent) are recorded for a month without a `production_run_id`, allocated deterministically across completed runs in that period proportional to **good packets produced** (or batch weight kg).

### 4.2 Unit Cost & Margin Output
$$\text{total\_cost\_paisa} = \text{raw\_material\_cost\_paisa} + \text{packaging\_cost\_paisa} + \text{direct\_overhead\_paisa} + \text{allocated\_overhead\_paisa}$$
$$\text{cost\_per\_packet\_paisa} = \text{round\_half\_up}\left(\frac{\text{total\_cost\_paisa}}{\text{actual\_good\_output\_qty}}\right)$$
$$\text{gross\_margin\_paisa} = \text{selling\_price\_before\_tax\_paisa} - \text{cost\_per\_packet\_paisa}$$

- **Benchmark Output (FIFO):** `581,000 paise / 188 = 3,090 paise` (**`₹30.90 / packet`**), yielding gross margin `₹50.00 - ₹30.90` = **`₹19.10 / packet` (`38.20%`)**.
- **Finished Goods Valuation Link:** Upon `COMPLETED`/`POSTED`, `PRD-001` creates a Finished Goods `CostLot` for `188 packets` valued at `cost_per_packet_paisa` (updated cleanly when `Step 8` finalizes overheads before month-end COGS close!).
