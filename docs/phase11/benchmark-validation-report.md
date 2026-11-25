# Official Section 5 Benchmark Validation Report — Phase 11

This report documents automated verification of every scenario step (Steps 1–9) and **all 11 official expected check values** defined in Section 5 of [`Problem Statement - Winter Internship Application - 2026.docx`](file:///d:/mac/ota/Problem%20Statement%20-%20Winter%20Internship%20Application%20-%202026.docx).

**Test Authority:** `tests/test_phase11_integration_benchmark_security.py::test_2_official_section5_benchmark_all_11_checks_exact` (executed against isolated PostgreSQL `ota_test`, `PASSED` in full `62`-test run).

---

## 1. Benchmark Master & Opening State (`app.seeds.benchmark_seed`)

- **Supplier / Company:** `Kaveri Traditional Snacks Pvt. Ltd.`, State Code `33` (`Tamil Nadu`), GSTIN `33AABCK1234F1Z5`.
- **Finished Product:** `Murukku 200 g` (`MRK-200G`), HSN `21069099`, GST `5%` (`500` bps), Selling Price `₹50.00/pkt`, Opening FG Stock = `50 pkts` (`@ ₹28.85/pkt` FIFO lot).
- **Opening RM & Packaging:**
  - `MAT-FLR` (Rice & Dal Flour): `100 kg` (`100,000.000 g`) @ `₹42.00/kg`
  - `MAT-OIL` (Cooking Oil): `30 L` (`30,000.000 ml`) @ `₹140.00/L`
  - `MAT-SPC` (Spices): `5 kg` (`5,000.000 g`) @ `₹200.00/kg`
  - `MAT-PCH-200` (200g Pouches): `500 pcs` @ `₹2.50/pc`
  - `MAT-CTN-20` (20-pkt Cartons): `30 pcs` @ `₹15.00/pc`
- **BOM v1 (200-pkt Batch Standard):** `40 kg` Flour, `10 L` Oil, `1.2 kg` Spice, `200` Pouches, `10` Cartons.
- **Customers:** `CUST-RET-A` (`Retailer A`, State `33`, TN GSTIN `33AAACR9999K1Z2`) and `CUST-DIST-B` (`Distributor B`, State `29`, KA GSTIN `29AAACD8888M1Z9`).

---

## 2. Official 11 Expected Benchmark Checks — Observed Validation Matrix

| Check # | Benchmark Requirement | Transaction Input / Trigger | Expected Official Value | Observed Test Value | Status |
| --- | --- | --- | --- | --- | --- |
| **Check 1** | Closing Rice & Dal Flour | Opening `100 kg` + GRN `60 kg` (`@ ₹45/kg`, 0% benchmark input tax) − Batch issue `40 kg` | **`120 kg`** | `120000.000` g (`120.000 kg`) | **PASSED** |
| **Check 2** | Closing Cooking Oil | Opening `30 L` − Batch issue `10.5 L` | **`19.5 L`** | `19500.000` ml (`19.500 L`) | **PASSED** |
| **Check 3** | Closing Packaging & Spice | Pouches: `500 - 188 - 6`; Cartons: `30 - 9`; Spice: `5 kg - 1.2 kg` | **`306 pouches`**, `21 cartons`, `3.8 kg spice` | `306.000` pcs (`MAT-PCH-200`), `21.000` pcs (`MAT-CTN-20`), `3800.000` g (`MAT-SPC`) | **PASSED** |
| **Check 4** | Finished Goods (`MRK-200G`) Physical & Net | Post `188` pkts (`50 + 188`) -> Approve/Dispatch `150` pkts (`Retailer A`) | **`238 pkts`** post-prod -> **`88 pkts`** closing | `238.000` pkts post-production; `88.000` pkts after dispatch | **PASSED** |
| **Check 5** | Production Yield Variance | `188` actual good pkts vs `200` expected pkts (`> 3%` tolerance) | **`-6.00%` (FLAGGED)** | `-6.00%` (`is_flagged = True` in `YIELD` scope) | **PASSED** |
| **Check 6** | Oil & Packaging Consumption Variance | `10.5 L` actual vs `10.0 L` standard Oil (`> 3%`) | **`+5.00%` (FLAGGED)** | `+5.00%` Oil (`is_flagged = True`), `+3.19%` Output-scaled Pouches (`is_flagged = True`) | **PASSED** |
| **Check 7** | Retailer A Tax Invoice Total (`INTRA_STATE`) | `150 pkts * ₹50.00 = ₹7,500.00` (`TN 33 -> TN 33`, `CGST 2.5% + SGST 2.5%`) | **`₹7,875.00`** (`₹7,500 + ₹187.50 + ₹187.50`) | `taxable=750000`, `cgst=18750`, `sgst=18750`, `igst=0`, `grand_total=787500` paise (`₹7,875.00`) | **PASSED** |
| **Check 8** | Receivable Outstanding After Partial Payment | Record `₹4,000.00` (`400000` paise) UPI payment against `₹7,875.00` INV-1 | **`₹3,875.00` (`PARTIALLY_PAID`)** | `outstanding_paisa = 387500`, `payment_status = "PARTIALLY_PAID"`, AR table matches `387500` | **PASSED** |
| **Check 9** | Distributor B Stock Shortage Guard | Attempt `120 pkts` order when available FG = `88 pkts` | **`32 pkts shortage`** (approval blocked) | `has_shortage = True`, `shortage_pkts = 32`, approval returns `409 Conflict` | **PASSED** |
| **Check 10** | Distributor B Interstate Tax Rule (`INTER_STATE`) | State `33` (`Tamil Nadu`) supplying State `29` (`Karnataka`) | **IGST 5%** (`CGST = ₹0`, `SGST = ₹0`) | Order estimate `IGST = ₹300.00` on `120` pkts; adjusted `88`-pkt invoice `INV/2026-27/0002` `IGST = ₹220.00`, `CGST = 0`, `SGST = 0` | **PASSED** |
| **Check 11** | Production Batch Unit Cost (FIFO + Overheads) | `40 kg @ ₹42` (`₹1,680`) + `10.5 L @ ₹140` (`₹1,470`) + `1.2 kg @ ₹200` (`₹240`) + `194 pcs @ ₹2.50` (`₹485`) + `9 ctn @ ₹15` (`₹135`) + `₹1,200` Labour + `₹600` Power = `₹5,810 / 188 pkts` | **`₹30.90/pkt`** (`ROUND_HALF_UP`) | `total_cost_paisa = 581000`, `cost_per_packet_paisa = 3090`, `gross_margin_per_pkt_paisa = 1910` (`38.20%`) | **PASSED** |

---

## 3. Cross-Module Reconciliation Outcome on Benchmark Data

- `POST /api/v1/reconciliation/runs` with `{"domain": "INVENTORY"}`: returned **`RECONCILED`** with `0` balance or CostLot drift (`_assert_inventory_ledger_invariants` confirmed `on_hand_qty_base == SUM(signed_qty_base)` across every material & pack size).
- `POST /api/v1/reconciliation/runs` with `{"domain": "FULL_SYSTEM"}`: confirmed zero billing, GST split, payment, receivable, or dispatch ledger discrepancies, surfacing strictly `BOM_CONSUMPTION_VARIANCE` (`severity: LOW`) for PRD-001's `-6.00%` Yield and `+5.00%` Oil variance per design.
- Resolving ambiguous design interpretations (`AMB-01`–`AMB-07`, detailed in [`docs/phase1/benchmark-analysis.md`](file:///d:/mac/ota/docs/phase1/benchmark-analysis.md)): FIFO batch cost default (`₹30.90/pkt`), soft reserve on `APPROVED` / physical deduct on `DISPATCH_OUT`, output-scaled packaging variance vs batch BOM variance, damaged pouch absorption into good unit cost, seeded opening `50` pkts at `₹28.85/pkt`, and `0%` input GST benchmark PO assumption all remained 100% consistent across Phases 6–11.
