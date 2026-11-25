# BOM Calculation Engine (`docs/phase7/bom-calculation-engine.md`)

## Exact Decimal Arithmetic & Unit Scaling
Implemented in `production.service.calculate_bom_requirements` (`GET /api/v1/production/bom/{pack_size_id}/calculate` and `POST /api/v1/production/bom/calculate`):
- Zero IEEE-754 floating-point types are used; all quantities use `decimal.Decimal` in canonical base units (`g`, `ml`, `piece`).
- Supports scaling either by **`batch_multiplier`** (e.g., `1.0`, `0.5`, `4.0`) or by **`target_output_pkts`** (`batch_multiplier = target_output_pkts / version.expected_yield_pkts`, rounded to `0.0001`).

## Indivisible Packaging Rounding Rule
- **Mass & Volume (`RAW_MATERIAL`):** Scale accurately to `3` decimal places in canonical `g`/`ml` (`ROUND_HALF_UP`), e.g. `1,200 g × 0.75 = 900.000 g` (`0.9 kg`).
- **Indivisible Packaging (`COUNT` dimension — Pouches & Cartons):** Fractional packaging quantities are rounded **up** to the next whole integer (`ROUND_CEILING`), e.g., scaling `10 cartons` by `0.75` (`7.500`) outputs `standard_qty_base = 8.000 piece`, with `was_rounded_up = true` and an explicit explanation note (`"Indivisible packaging unit rounded up from 7.500 to 8 piece"`).

## Live Stock Availability Comparison
For each required component, the calculator reads live `inventory.inventory_balances`:
- `available_qty_base = MAX(0, on_hand_qty_base - reserved_qty_base)`
- `additional_required_base = MAX(0, standard_qty_base - available_qty_base)`
- Flags `is_shortage = additional_required_base > 0` and builds a readable shortage summary.
