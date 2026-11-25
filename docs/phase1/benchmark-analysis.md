# Benchmark Scenario Analysis (Section 5 — Mandatory)

**Source Basis:** `Problem Statement - Winter Internship Application - 2026.docx`, Section 5 (lines 94–131)  
**Golden Rule:** Official benchmark master data and check expectations are preserved verbatim. Where the specification leaves accounting choices or minor ambiguities open, all alternatives are calculated exactly and our proposed rule is explicitly marked for user approval.

---

## 1. Official Master Data & Opening State

**Factory Location:** Tamil Nadu (State Code `33`)  
**Product SKU:** `Murukku 200 g`  
**Standard Selling Price:** `₹50.00` per packet before tax  
**Applicable GST Rate (for exercise):** `5%` (`2.5% CGST + 2.5% SGST` intra-state; `5.0% IGST` inter-state)  
**Variance Alert Tolerance:** `3.0%` (per Section 4.3 example)

### 1.1 Bill of Materials (BOM) — `Murukku 200 g` (1 Batch = 200 Packets Expected)

| Item | Category | Qty per Batch | Unit | Opening Stock | Rate (₹) | Opening Valuation (₹) |
| --- | --- | --- | --- | --- | --- | --- |
| Flour | Raw Material | `40` | `kg` | `100 kg` | `₹42.00` (opening) / `₹45.00` (new purchase) | `₹4,200.00` |
| Cooking oil | Raw Material | `10` | `litre` | `30 L` | `₹140.00` | `₹4,200.00` |
| Salt and spice mix | Raw Material | `1.2` | `kg` | `5 kg` | `₹200.00` | `₹1,000.00` |
| 200 g pouch | Packaging | `200` | `piece` | `500 pieces` | `₹2.50` | `₹1,250.00` |
| Carton (holds 20 packets) | Packaging | `10` | `piece` | `30 pieces` | `₹15.00` | `₹450.00` |
| **Murukku 200 g** | **Finished Goods** | *(Output: 200)* | `packet` | **`50 packets`** | *Not specified in Section 5 (`AMB-05`)* | *Depends on `DEC-03`* |

---

## 2. Step-by-Step Benchmark Execution Trace

### Step 1: Record a purchase of 60 kg flour at ₹45/kg
- **Initiating Action:** Production Supervisor (or Admin) records `PUR-001` for `60 kg` Flour @ `₹45.00/kg`.
- **Financial Total:** `60 × ₹45.00 = ₹2,700.00` (`270,000 paise`). *(Ambiguity `AMB-06`: No supplier input GST % specified in Section 5; default 0% input tax for benchmark purchase.)*
- **Stock Ledger Impact:** `PURCHASE_IN` `+60.000 kg` Flour (`60,000 g`).
- **Flour Closing Balance after Step 1:** `100 + 60 = 160 kg`.
- **Valuation State after Step 1:**
  - **Under FIFO:** Lot 1 = `100 kg @ ₹42.00` (`₹4,200.00`), Lot 2 = `60 kg @ ₹45.00` (`₹2,700.00`). Total = `160 kg`, `₹6,900.00`.
  - **Under Weighted Average:** `(₹4,200.00 + ₹2,700.00) / 160 kg = ₹6,900.00 / 160 = ₹43.125/kg` (`4312.5 paise/kg`).
  - **Under Last Price:** Latest purchase rate = `₹45.00/kg`.

---

### Step 2: Start one production run of Murukku 200 g; Issue 40 kg flour, 10.5 L oil, 1.2 kg spice mix
- **Initiating Action:** Production Supervisor creates `PRD-001` for `1 batch` (`expected_yield = 200 packets`) and issues raw materials:
  - Flour: Planned `40.0 kg`, Actual `40.0 kg` -> **Variance = `0.0 kg` (`0.00%`)** -> OK.
  - Cooking oil: Planned `10.0 L`, Actual `10.5 L` -> **Variance = `+0.5 L` (`+5.00%`)** -> **FLAGGED (`> 3%` tolerance)**.
  - Salt & spice mix: Planned `1.2 kg`, Actual `1.2 kg` -> **Variance = `0.0 kg` (`0.00%`)** -> OK.
- **Stock Ledger Impact (`PROD_ISSUE_OUT` linked to `PRD-001`):**
  - Flour: `160.0 - 40.0 = 120.0 kg`
  - Cooking oil: `30.0 - 10.5 = 19.5 L`
  - Salt & spice mix: `5.0 - 1.2 = 3.8 kg`
- **Raw Material Cost Issued (per method):**
  - **FIFO:** Flour (`40 × ₹42.00 = ₹1,680.00`) + Oil (`10.5 × ₹140.00 = ₹1,470.00`) + Spice (`1.2 × ₹200.00 = ₹240.00`) = **`₹3,390.00`**.
    *(Remaining Flour Lots: `60 kg @ ₹42.00` + `60 kg @ ₹45.00` = `120 kg`, value `₹5,220.00`.)*
  - **Weighted Average:** Flour (`40 × ₹43.125 = ₹1,725.00`) + Oil (`₹1,470.00`) + Spice (`₹240.00`) = **`₹3,435.00`**.
    *(Remaining Flour: `120 kg @ ₹43.125 = ₹5,175.00`.)*
  - **Last Price:** Flour (`40 × ₹45.00 = ₹1,800.00`) + Oil (`₹1,470.00`) + Spice (`₹240.00`) = **`₹3,510.00`**.

---

### Step 3: Record actual output of 188 good packets, 6 pouches damaged, and 9 cartons used
- **Initiating Action:** Production Supervisor completes `PRD-001`:
  - Actual good output: `188 packets` (vs `200 expected`).
  - **Yield Variance:** `(188 - 200) / 200 × 100 = -12 / 200 = -6.00%` -> **FLAGGED (`abs(-6%) > 3%` tolerance)**.
  - Damaged packaging: `6 pouches` damaged during packing; `188 pouches` used for good packets -> **Total pouches deducted = `188 + 6 = 194 pieces`**.
  - Cartons used: `9 pieces` (`9 × 20 = 180 packets` packed in cartons; `8 packets` remain loose / un-cartoned — see `AMB-03`).
- **Stock Ledger Impact (linked to `PRD-001`):**
  - 200 g Pouches (`PROD_ISSUE_OUT` / `PACKAGING_DAMAGE_OUT`): `500 - 188 - 6 = 306 pieces`.
  - Cartons (`PROD_ISSUE_OUT`): `30 - 9 = 21 pieces`.
  - Finished Murukku 200 g (`PROD_OUTPUT_IN`): `50 + 188 = 238 packets`.
- **Packaging Variance Note (`AMB-03`):**
  - Against **batch BOM** (`200 pouches`, `10 cartons`): pouches `194 vs 200 (-3.0%)`, cartons `9 vs 10 (-10.0%)`.
  - Against **output-scaled standard** (`188 pouches` needed for `188` packets; `floor(188/20) = 9` whole cartons): pouches `194 vs 188 = +6 damaged (+3.19% wastage -> FLAGGED!)`, cartons `9 vs 9 = 0%`.
- **Packaging Cost Consumed:**
  - Pouches: `194 × ₹2.50 = ₹485.00` (`₹470.00` good + `₹15.00` damaged — see `AMB-04`).
  - Cartons: `9 × ₹15.00 = ₹135.00`.
  - **Total Packaging Cost = `₹620.00`**.

---

### Step 4: Salesman A, on mobile, places an order for Retailer A (Tamil Nadu): 150 packets
- **Initiating Action:** Salesman A creates & submits `ORD-001` for `Retailer A` (`Tamil Nadu`): `150 packets × ₹50.00 = ₹7,500.00` before tax.
- **State:** `SUBMITTED`.
- **Stock Impact:** Finished goods remains `238 packets` (On-Hand = `238`, Reserved = `0`, Available = `238`).

---

### Step 5: Admin approves order, raises GST invoice (CGST + SGST), and records dispatch
- **Stock Check before Approval:** Ordered `150` <= Available `238` -> **Sufficient stock (surplus 88)**.
- **Approval:** `ORD-001` -> `APPROVED`. Soft reservation = `150 packets` (`Available = 238 - 150 = 88`).
- **GST Invoice (`INV/2026-27/0001`):**
  - Place of Supply: Factory = Tamil Nadu (`33`), Retailer A = Tamil Nadu (`33`) -> **Intra-state (CGST + SGST)**.
  - Taxable Value: `150 × ₹50.00 = ₹7,500.00` (`750,000 paise`).
  - CGST (`2.5%`): `₹7,500.00 × 0.025 = ₹187.50` (`18,750 paise`).
  - SGST (`2.5%`): `₹7,500.00 × 0.025 = ₹187.50` (`18,750 paise`).
  - **Invoice Grand Total:** `₹7,500.00 + ₹187.50 + ₹187.50 = ₹7,875.00` (`787,500 paise`).
  - **Receivable Created:** Retailer A AR = `₹7,875.00` (`UNPAID`).
- **Dispatch (`DSP-001`):**
  - Stock Ledger (`DISPATCH_OUT` linked to `DSP-001` / `INV/2026-27/0001`): `-150 packets`.
  - **Finished Goods Closing Balance:** `238 - 150 = 88 packets` (Reserved releases to `0`; Available = `88`).

---

### Step 6: Salesman B places an order for Distributor B (Karnataka): 120 packets
- **Initiating Action:** Salesman B submits `ORD-002` for `Distributor B` (`Karnataka`): `120 packets × ₹50.00 = ₹6,000.00` before tax.
- **System Behaviour at Order Entry:** Order is accepted as `SUBMITTED` so demand is not lost. (Mobile optionally shows soft advisory if online, without blocking customer order capture.)
- **System Behaviour on Admin Verification Screen:**
  - Available Finished Goods = `88 packets`; Ordered = `120 packets`.
  - **Shortage Flag:** **`Shortage of 32 packets`** (`120 - 88 = 32`).
  - **Guardrail:** Full approval/dispatch of `120 packets` is **blocked** (negative stock prohibited). Order stays pending/on-hold awaiting production, OR Admin may reduce/partially fulfill `<= 88` with customer consent.
  - **Tax Preview ("IGST applies if invoiced"):** Factory = Tamil Nadu (`33`), Distributor B = Karnataka (`29`) -> **Inter-state (`IGST 5%`)**:
    - *If invoiced for full `120` pkts (after producing another batch):* Taxable `₹6,000.00` + `5% IGST ₹300.00` = **`₹6,300.00`**.
    - *If qty reduced & invoiced for available `88` pkts:* Taxable `₹4,400.00` + `5% IGST ₹220.00` = **`₹4,620.00`**.
- **Stock Impact (Benchmark Baseline where order is held at shortage flag):** Finished Goods remains **`88 packets`**.

---

### Step 7: Record a payment of ₹4,000 from Retailer A
- **Initiating Action:** Factory Admin records `PMT-001` of `₹4,000.00` (`400,000 paise`) from Retailer A, allocated to `INV/2026-27/0001`.
- **Result:**
  - Invoice Status: `UNPAID` -> `PARTIALLY_PAID`.
  - Paid Amount: `₹4,000.00`.
  - **Retailer A Outstanding Balance:** `₹7,875.00 - ₹4,000.00 = ₹3,875.00` (`387,500 paise`).

---

### Step 8: Add labour of ₹1,200 and gas/power of ₹600 for the run, then show cost per packet
- **Direct Run Overheads:** Labour `₹1,200.00` + Gas/Power `₹600.00` = **`₹1,800.00`**.
- **Complete Costing Comparison across Valuation Methods (for `188 good packets`):**

| Cost Component | FIFO *(Recommended)* | Moving Weighted Average | Last Purchase Price |
| --- | --- | --- | --- |
| Flour (`40 kg`) | `₹1,680.00` (`@ ₹42.00`) | `₹1,725.00` (`@ ₹43.125`) | `₹1,800.00` (`@ ₹45.00`) |
| Cooking Oil (`10.5 L`) | `₹1,470.00` (`@ ₹140.00`) | `₹1,470.00` (`@ ₹140.00`) | `₹1,470.00` (`@ ₹140.00`) |
| Salt & Spice Mix (`1.2 kg`) | `₹240.00` (`@ ₹200.00`) | `₹240.00` (`@ ₹200.00`) | `₹240.00` (`@ ₹200.00`) |
| **Raw Materials Subtotal** | **`₹3,390.00`** | **`₹3,435.00`** | **`₹3,510.00`** |
| 200 g Pouches (`188 + 6 = 194 pcs`) | `₹485.00` (`@ ₹2.50`) | `₹485.00` (`@ ₹2.50`) | `₹485.00` (`@ ₹2.50`) |
| Cartons (`9 pcs`) | `₹135.00` (`@ ₹15.00`) | `₹135.00` (`@ ₹15.00`) | `₹135.00` (`@ ₹15.00`) |
| **Packaging Subtotal** | **`₹620.00`** | **`₹620.00`** | **`₹620.00`** |
| Direct Labour | `₹1,200.00` | `₹1,200.00` | `₹1,200.00` |
| Gas & Power | `₹600.00` | `₹600.00` | `₹600.00` |
| **Total Run Cost** | **`₹5,810.00`** | **`₹5,855.00`** | **`₹5,930.00`** |
| Good Packets Produced | `188` | `188` | `188` |
| **Exact Unrounded Cost / Packet** | `₹30.904255...` | `₹31.143617...` | `₹31.542553...` |
| **Cost per Good Packet (Nearest Paisa)** | **`₹30.90`** | **`₹31.14`** | **`₹31.54`** |
| Selling Price Before Tax | `₹50.00` | `₹50.00` | `₹50.00` |
| **Gross Margin per Packet** | **`₹19.10` (`38.20%`)** | **`₹18.86` (`37.72%`)** | **`₹18.46` (`36.92%`)** |

*Note on Alternative Damaged-Pouch Accounting (`AMB-04`):* If the `6` damaged pouches (`₹15.00`) were excluded from unit cost and booked as separate scrap loss (`Total Run Cost = ₹5,795.00` FIFO / `₹5,840.00` WAvg), cost per packet would be `₹30.82` (FIFO) or `₹31.06` (WAvg). Including them (`₹30.90` / `₹31.14`) ensures wastage is truthfully absorbed into packet unit cost.

*Note on Standard Planned Cost Benchmark (200 expected packets, FIFO rates + ₹1,800 overhead):*
Planned RM (`40×42 + 10×140 + 1.2×200 = ₹3,320`) + Planned Pkg (`200×2.50 + 10×15 = ₹650`) + Overheads (`₹1,800`) = `₹5,770 / 200` = **`₹28.85/packet`**. Actual run (`₹30.90`) increased cost by **`+₹2.05/packet` (`+7.11%`)**, directly quantifying the financial cost of the `0.5 L` excess oil (`+₹70`), `6` damaged pouches (`+₹15`), and `12` missing packets (`6%` yield loss)!

---

### Step 9: Generate Monthly Reports (Section 4.6)
Expected contents verified from Steps 1–8:
1. **Sales Register:** `1` posted invoice (`INV/2026-27/0001`, Retailer A, `150 pkts`, Taxable `₹7,500.00`, Tax `₹375.00`, Total `₹7,875.00`). Pending order `ORD-002` (Distributor B, `120 pkts`) excluded from posted sales until invoiced.
2. **GST Outward Summary (GSTR-1 / 3B):** Intra-state TN (`₹7,500.00` taxable, `₹187.50` CGST, `₹187.50` SGST, `₹0.00` IGST); Inter-state (`₹0.00` until Distributor B invoiced).
3. **Purchase Register:** `1` purchase (`PUR-001`, `60 kg` Flour @ `₹45.00`, `₹2,700.00`).
4. **Stock Summary & Ledger:**
   - Flour: `100 + 60 - 40 = 120 kg` (`₹5,220.00` FIFO / `₹5,175.00` WAvg)
   - Cooking Oil: `30 - 10.5 = 19.5 L` (`₹2,730.00`)
   - Salt & Spice Mix: `5 - 1.2 = 3.8 kg` (`₹760.00`)
   - 200 g Pouches: `500 - 194 = 306 pcs` (`₹765.00`)
   - Cartons: `30 - 9 = 21 pcs` (`₹315.00`)
   - Finished Murukku 200 g: `50 + 188 - 150 = 88 packets`
5. **Production & Variance Report:** `PRD-001`, `1` batch planned `200`, actual `188` (`-6.0%` FLAGGED), Oil `10.5 vs 10.0` (`+5.0%` FLAGGED), Pouches `194 vs 188 output-req` (`+3.19%` FLAGGED), Total Cost `₹5,810.00` (FIFO), Cost/Packet `₹30.90`.
6. **Payments & AR Ageing:** Retailer A collected `₹4,000.00`, outstanding `₹3,875.00` (`0–30 days` bucket).

---

## 3. Official Results Verification Table

| Official Check (Section 5) | Official Expected Value | Our Verified Calculation | Status / Notes |
| --- | --- | --- | --- |
| Flour closing balance | `120 kg (100 + 60 − 40)` | `120.000 kg` | Exact Match |
| Oil closing balance | `19.5 L` | `19.500 L` | Exact Match |
| Pouches closing balance | `306 (188 used + 6 damaged)` | `306 pieces` (`500 − 194`) | Exact Match |
| Finished goods after run | `238 packets (50 + 188)` | `238 packets` | Exact Match |
| Finished goods after Retailer A dispatch | `88 packets` | `88 packets` (`238 − 150`) | Exact Match |
| Yield variance | `188 vs 200 expected, −6%, flagged` | `−6.00%`, Flagged (`> 3%`) | Exact Match |
| Oil consumption variance | `+5%, flagged` | `+5.00%`, Flagged (`> 3%`) | Exact Match |
| Retailer A invoice | `₹7,500 taxable + ₹187.50 CGST + ₹187.50 SGST = ₹7,875` | `₹7,500.00 + ₹187.50 + ₹187.50 = ₹7,875.00` | Exact Match |
| Retailer A outstanding | `₹3,875` | `₹3,875.00` (`₹7,875 − ₹4,000`) | Exact Match |
| Distributor B order | `Shortage of 32 packets flagged; IGST applies if invoiced` | `120 − 88 = 32` shortage flagged; `IGST 5%` applies | Exact Match |
| Cost per packet | `Your figure, with valuation method & overhead rule stated` | `₹30.90` (FIFO, recommended) / `₹31.14` (WAvg) / `₹31.54` (Last Price) | Exact & Explains All Rules |
| *(Additional checked item)* Cartons closing | *(Not listed in official check table)* | `21 pieces` (`30 − 9`) | Tracked completely |
| *(Additional checked item)* Spice mix closing | *(Not listed in official check table)* | `3.800 kg` (`5.0 − 1.2`) | Tracked completely |

---

## 4. Documented Ambiguities Requiring Approval (`AMB-01` – `AMB-07`)

1. **`AMB-01` (Valuation Method Choice):** Section 4.5 requires choosing one of FIFO, Weighted Average, or Last Price (`₹30.90` vs `₹31.14` vs `₹31.54`). **Proposal:** Default to **FIFO** (natural fit for perishable food batch lots and clean exact-paisa math on ₹42/₹45 layers), with clear documentation of Weighted Average alternative.
2. **`AMB-02` (Timing of Stock Check & Reservation):** Stock is deducted at Dispatch (`Section 4.2`), yet checked before Approval. **Proposal:** Soft-reserve stock upon Order Approval (`Available = On-Hand - Reserved`) and convert reservation to actual `DISPATCH_OUT` ledger deduction upon Dispatch.
3. **`AMB-03` (Packaging Variance Baseline & Loose Packets):** `188` packets fill `9` cartons (`180` pkts) leaving `8` loose packets; and `194` pouches vs `200` batch BOM appears `-3%` while vs `188` good packets it is `+3.19%` wastage. **Proposal:** Measure packaging consumption variance against **output-scaled standard** (`188` pouches needed; `floor(188/20) = 9` whole cartons), while showing batch BOM qty (`200`, `10`) alongside for audit clarity.
4. **`AMB-04` (Damaged Packaging Cost Treatment):** Whether `6 × ₹2.50 = ₹15.00` damaged pouches stay inside run unit cost (`₹30.90`) or move to separate scrap expense (`₹30.82`). **Proposal:** Include inside run cost (`₹30.90`) so packet unit cost reflects real process waste.
5. **`AMB-05` (Opening Finished Goods Valuation):** Section 5 provides `50 packets` opening stock of Murukku 200 g without a unit cost rate. **Proposal:** Seed opening finished goods at standard opening BOM cost + standard overhead (`₹28.85/packet` -> `₹1,442.50`), OR explicitly seed `₹28.85` (or `₹20.00` material-only) and disclose in `README` / Stock Valuation report.
6. **`AMB-06` (Input GST on Purchases):** Step 1 gives `₹45/kg` flat. **Proposal:** Support optional Input Tax GST on Purchase Receipts (`0%` default in benchmark seed so `₹45/kg` maps 1:1 to inventory rate).
7. **`AMB-07` (Distributor B Shortage Handling Policy):** When `88 < 120`, should Admin be restricted to Hold/Edit/Reject, or also allowed Split/Partial Dispatch? **Proposal:** Block full approval (`120`); show shortage `32`; support Hold (`AWAITING_STOCK`, default in benchmark) + Admin Edit Qty (`<= 88`) + Reject.
