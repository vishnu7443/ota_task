# BOM & Multi-Pack Management (`docs/phase7/bom-management.md`)

## Domain Separation (`RecipeTemplate` + `PackSize` + `BomHeader` + `BomVersion` + `BomComponent`)
- **Base Product (`sales.products`):** Product family carrying HSN (`21069099`) and GST rate (`5%`), e.g., `PROD-MRK` (`Murukku`).
- **Pack Size Variants (`sales.pack_sizes`):** Concrete sellable SKUs specifying `pack_weight_g`, `packets_per_carton`, and `sku_code` (e.g., `MRK-200G`: `200 g`, `20 pkts/carton`; extensible live via `POST /api/v1/production/catalog/pack-sizes` to `MRK-500G`: `500 g`, `10 pkts/carton`).
- **Shared Bulk Recipe Template (`production.recipe_templates`):** Captures bulk base mix (`RCP-MRK-BASE`: `Murukku Base Mix`, `40,000 g` base yield weight) so alternate pack weights share one cooking base without duplicating kitchen math.
- **BOM Header & Versioned Components:** `production.bom_headers` holds a `1:1` anchor per `pack_size_id`, while `production.bom_components` binds each `BomVersion` to materials (`COOKING_RAW` vs `PACKAGING`), validated against `Material.material_category` and `unit_dimension` (`MASS`, `VOLUME`, `COUNT`).

## Official Benchmark Seed (`Murukku 200 g` BOM v1)
Seeded idempotently in `app/seeds/benchmark_seed.py` (`expected_yield_pkts = 200`, `status = 'ACTIVE'`):
| Material Code | Material | Input Role | Standard Qty / Batch | Canonical Base Qty |
|---|---|---|---|---|
| `MAT-FLR` | Flour | `COOKING_RAW` | `40 kg` | `40,000.000 g` |
| `MAT-OIL` | Cooking oil | `COOKING_RAW` | `10 L` | `10,000.000 ml` |
| `MAT-SPC` | Salt and spice mix | `COOKING_RAW` | `1.2 kg` | `1,200.000 g` |
| `MAT-PCH-200` | 200 g pouch | `PACKAGING` | `200 piece` | `200.000 piece` |
| `MAT-CTN-20` | Carton (20 pkts) | `PACKAGING` | `10 piece` | `10.000 piece` |
