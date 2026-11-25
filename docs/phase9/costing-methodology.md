# Phase 9 — Product Costing Methodology & Monthly Overhead Pools

## Valuation Rule

Manufacturing cost uses **strict FIFO (`CostLotConsumption`) lot-layer costing** already posted into `inventory.cost_lot_consumptions` by Phase 7 (`production/service.py`), avoiding approximate averages or floating-point rounding drift. Every currency calculation uses PostgreSQL `BIGINT` paise and Python `Decimal` with `ROUND_HALF_UP`.

## Cost Components Captured per Production Run

For every `COMPLETED` or `POSTED` production run:
1. **Raw Material Cost (`raw_material_cost_paisa`):** Sum of FIFO `CostLotConsumption.total_cost_paisa` where `consumption_purpose IN ('PRODUCTION_CONSUMED', 'WASTAGE')` for `RAW_MATERIAL` items. `RETURNED_UNUSED` reversal rows reduce net batch material cost cleanly.
2. **Raw Wastage Cost (`raw_wastage_cost_paisa`):** Extracted explicitly from `WASTAGE` consumption records so excessive process losses remain visible instead of silently hidden.
3. **Packaging Cost (`packaging_cost_paisa`):**
   - `good_packaging_cost_paisa`: Pouches & cartons consumed on sellable output (`PRODUCTION_CONSUMED`).
   - `damaged_packaging_cost_paisa`: Damaged pouches/cartons recorded during packing (`DAMAGED_PACKAGING`, e.g., 6 damaged pouches @ ₹2.50 = `₹15.00` = `1500` paise).
   - `packaging_cost_paisa = good_packaging_cost_paisa + damaged_packaging_cost_paisa`.
4. **Rejected Output Cost Impact (`rejected_output_cost_impact_paisa`):** Proportional share of raw + packaging + direct cost attributable to `rejected_output_pkts`, reported explicitly while spreading full net batch cost over saleable `good_packets` to compute true unit landed cost.
5. **Direct Run Overheads (`direct_overhead_paisa`):** Active (non-voided) `costing.production_overheads` entries linked to `production_run_id` (`allocation_scope = 'DIRECT_RUN'`), broken down into `direct_labour_paisa`, `gas_power_paisa`, and `other_direct_overhead_paisa`.
6. **Monthly Pool Allocated Overheads (`allocated_overhead_paisa`):** Active `MONTHLY_POOL` factory expenses (e.g., `FACTORY_RENT`, `MACHINE_DEPRECIATION`) for `run_date`'s `YYYY-MM`, allocated deterministically across all `COMPLETED`/`POSTED` runs in that month in proportion to `actual_good_output_pkts` using largest-remainder integer-paisa allocation so `SUM(run_shares) == total_pool` to the single paisa.
7. **Unit Cost & Planned Variance:**
   - `exact_cost_per_packet_paisa = Decimal(total_cost_paisa) / Decimal(good_packets)` (`NUMERIC(18,6)`)
   - `cost_per_packet_paisa = int(exact_cost_per_packet_paisa.quantize(Decimal(1), rounding=ROUND_HALF_UP))`
   - Compares actual FIFO batch cost against pinned `BomVersion` standard quantities rated at FIFO lot/standard unit costs (`planned_total_cost_paisa`, `planned_cost_per_packet_paisa`), exposing `material_variance_paisa` and `cost_per_pkt_variance_paisa`.
   - Computes unit gross margin against active selling price (`selling_price_snapshot_paisa`).

## Official Benchmark Verification (`PRD-001` — `MRK-200G`, `188` Good Packets)

- **Raw Materials (FIFO):** `40 kg` Flour (`₹1,680.00`) + `10.5 L` Oil (`₹1,470.00`) + `1.2 kg` Spice (`₹240.00`) = **`₹3,390.00`** (`339000` paise)
- **Packaging:** `188` good pouches + `6` damaged pouches (`194 × ₹2.50 = ₹485.00`, of which `₹15.00` damaged) + `9` cartons (`₹135.00`) = **`₹620.00`** (`62000` paise)
- **Direct Overheads:** `₹1,200.00` Direct Labour + `₹600.00` Gas/Power = **`₹1,800.00`** (`180000` paise)
- **Total Batch Cost:** **`₹5,810.00`** (`581000` paise)
- **Actual Unit Cost:** `581000 / 188 = 3090.425532...` paise -> **`₹30.90 / packet`** (`3090` paise)
- **Planned Standard Cost:** `₹5,770.00 / 200` = **`₹28.85 / packet`** (`2885.00` paise)
- **Selling Price & Margin:** `₹50.00 - ₹30.90` = **`₹19.10 / packet`** (**`38.20%`** gross margin)

## Versioned Snapshot History

Every cost computation creates an immutable sequential `snapshot_version` (`1 = PRELIMINARY` on `post_production_run`, `2+ = FINALIZED` or recalculated on overhead addition/void/monthly pool reallocation). Previous versions toggle strictly `is_current = true -> false`, enforced by PostgreSQL trigger `trg_cost_summary_immutability`.
