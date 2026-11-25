# NIT Trichy Benchmark Validation (`docs/phase6/benchmark-validation.md`)

## Official Section 5 Benchmark Baseline (`app/seeds/benchmark_seed.py`)
`benchmark_seed.py` seeds strictly the official problem-statement masters and opening balances (kept cleanly separate from `app/seeds/dev_fixtures.py` and test harnesses):

| Code | Item Name | Category | Opening Qty (Display) | Opening Qty (Base) | Unit Rate / Cost |
|---|---|---|---|---|---|
| `MAT-FLR` | Flour | `RAW_MATERIAL` | `100 kg` | `100,000.000 g` | `₹42.00 / kg` (`4.200000 p/g`) |
| `MAT-OIL` | Cooking oil | `RAW_MATERIAL` | `30 L` | `30,000.000 ml` | `₹140.00 / L` (`14.000000 p/ml`) |
| `MAT-SPC` | Salt and spice mix | `RAW_MATERIAL` | `5 kg` | `5,000.000 g` | `₹200.00 / kg` (`20.000000 p/g`) |
| `MAT-PCH-200` | 200 g pouch | `PACKAGING_MATERIAL` | `500 piece` | `500.000 piece` | `₹2.50 / pc` (`250.000000 p/pc`) |
| `MAT-CTN-20` | Carton (20 pkts) | `PACKAGING_MATERIAL` | `30 piece` | `30.000 piece` | `₹15.00 / pc` (`1500.000000 p/pc`) |
| `MRK-200G` | Murukku 200 g | `FINISHED_GOOD` | `50 packet` | `50.000 packet` | `₹28.85 / pkt` (`2885.000000 p/pkt`) |
| `SUP-001` | Cauvery Agro Mills | Supplier (`TN 33`) | GSTIN `33AAACS7777P1Z1` | — | Active |

## Verified 10-Step Phase 6 Final Acceptance Calculation
Executed end-to-end through FastAPI HTTP routes & real PostgreSQL 16 in `test_benchmark_final_acceptance_scenario_60kg_flour_and_exact_balances`:
1. Verified exact Section 5 opening balances above (`100 kg` Flour -> `100,000.000 g`).
2. Created & approved Purchase Order for `SUP-001`: `60 kg Flour @ ₹45.00 / kg` (`5%` GST) — physical Flour remained unchanged at `100 kg`.
3. Created, submitted, verified, and posted Goods Receipt (`60 kg` accepted, `0 kg` rejected, batch `FLR-LOT-202611`).
4. Verified closing Flour stock = **`160 kg` (`160,000.000 g`)**, `received_qty_base = 60,000.000`, `open_lot_value_paisa = 690,000` (`₹6,900.00`: `₹4,200 + ₹2,700`).
5. Verified `InventoryLedger` entries for `MAT-FLR`: `OPENING (+100,000.000 g)` and `PURCHASE_IN (+60,000.000 g, 270,000 paisa)`.
6. Verified Oil (`30 L`), Spice (`5 kg`), Pouches (`500 piece`), Cartons (`30 piece`), and Finished Murukku (`50 packet`) remained untouched at their exact opening balances.
