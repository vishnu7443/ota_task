# Phase 7 Benchmark Validation (`docs/phase7/benchmark-validation.md`)

Verified end-to-end against Section 5 benchmark figures in `test_3_benchmark_end_to_end_purchase_production_posting_variance_and_ledger`:

## Initial Benchmark & Step 1 (Purchasing)
- **Active Seeded BOM (`MRK-200G` v1):** `40 kg` Flour (`40,000 g`), `10 L` Oil (`10,000 ml`), `1.2 kg` Salt & Spice Mix (`1,200 g`), `200 piece` 200 g Pouches, `10 piece` 20-pkt Cartons -> `200` expected packets (`batch_multiplier = 1.0000`).
- **Purchase Receipt Step 1 (`60 kg` Flour @ ₹45/kg):** `MAT-FLR` increases from opening `100 kg` to `160 kg` (`160,000 g`).

## Step 2 & Step 3 (Production Issue, Completion & Atomic Posting)
- **Inputs Issued/Consumed:** `40 kg` Flour (`40,000 g`), `10.5 L` Cooking Oil (`10,500 ml`), `1,200 g` (`1.2 kg`) Salt & Spice Mix, `188 + 6 = 194 piece` 200 g Pouches (`6` torn during sealing), `9 piece` 20-pkt Cartons (`180` cartoned + `8` loose packets).
- **Outputs:** `188` good packets (`rejected_output_pkts = 0`), batch code `MRK-20261125-01`.

## Verified Closing Balances (`GET /api/v1/inventory/overview`)
| Item Code | Item | Opening + Received | Issued / Consumed | Expected & Verified Closing |
|---|---|---|---|---|
| `MAT-FLR` | Gram & Rice Flour | `100 kg + 60 kg = 160 kg` | `40 kg` | **`120.000 kg` (`120000.000 g`)** |
| `MAT-OIL` | Cooking Oil | `30 L` | `10.5 L` | **`19.500 L` (`19500.000 ml`)** |
| `MAT-SPC` | Salt & Spice Mix | `5 kg` | `1.2 kg` | **`3.800 kg` (`3800.000 g`)** |
| `MAT-PCH-200` | 200 g Pouches | `500 piece` | `188 + 6 = 194 piece` | **`306.000 piece`** |
| `MAT-CTN-20` | 20-pkt Cartons | `30 piece` | `9 piece` | **`21.000 piece`** |
| `MRK-200G` | Murukku 200 g (FG) | `50 pkt` | `+188 good pkts` | **`238.000 packet`** |

## Verified FIFO Costing & Variances (`tolerance = ±2.00%`)
- **FIFO Flour Valuation:** Opening lot (`100 kg @ ₹42/kg`) is depleted first by `40 kg`, leaving `60 kg @ ₹42/kg + 60 kg @ ₹45/kg = ₹5,220` (`522,000 paisa`).
- **Yield Variance (`YIELD`):** `(188 - 200) / 200 × 100 = -6.00%` (**Flagged** -> `YIELD_LOSS` alert).
- **Cooking Oil Variance (`RAW_CONSUMPTION`):** `(10.5 - 10) / 10 × 100 = +5.00%` (**Flagged** -> `MATERIAL_OVERUSE` alert).
- **Flour & Spice Variances (`RAW_CONSUMPTION`):** `0.00%` (Unflagged).
- **200 g Pouches (`PACKAGING_OUTPUT_SCALED`):** `(194 - 188) / 188 × 100 = +3.19%` (**Flagged** -> `PACKAGING_WASTAGE` alert).
- **Cartons (`PACKAGING_OUTPUT_SCALED` vs `PACKAGING_BATCH_BOM`):** `0.00%` output-scaled (`9` used vs `floor(188/20) = 9`, `8` loose packets, unflagged) alongside `-10.00%` informational batch-BOM comparison.
