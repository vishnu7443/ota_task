# Production and Bill of Materials (BOM) Domain Design

**Evaluation Context:** Section 4.3 & Section 9 explicitly rank BOM, unit conversion, planned-vs-actual variance, and multi-pack extensibility as the **highest-weight technical design area**.

---

## 1. Multi-Pack BOM Architecture (Solving the 200 g vs 500 g Interview Problem)

### The Naive Trap vs Clean Domain Separation
- **Naive Model:** Attaching all raw ingredients directly and solely to `Murukku 200 g` forces copying the entire cooking recipe (`40 kg` flour, `10 L` oil, `1.2 kg` spice) when adding `Murukku 500 g`, risking silent formula drift if spice or oil ratios change.
- **Our Independent Design (`RecipeTemplate` + `BillOfMaterials` + `BomVersion`):**
  1. **`RecipeTemplate` (Bulk Cooking Base):** Captures the shared cooking mix for a snack family — e.g., `Murukku Base Mix` (`base_yield_weight_g = 40,000 g` = `40 kg` cooked murukku using `40 kg` flour, `10 L` oil, `1.2 kg` spice mix).
  2. **`BillOfMaterials` & `BomVersion` (Product-Specific Packaging & Yield):** Attached to a concrete sellable `Product` SKU (`Murukku 200 g`), pinning:
     - Optional link to `RecipeTemplate` (`batch_scale = 1.0` for `40 kg`).
     - `expected_yield_packets` (`40,000 g / 200 g = 200 packets`).
     - `BomItem` lines capturing both **Cooking Inputs** (`input_role = COOKING_RAW`, inherited/synced from template or defined directly) and **Packaging Inputs** (`input_role = PACKAGING`: `200` × `200 g pouch`, `10` × `Carton (20 pkts)`).
  3. **Adding `Murukku 500 g` Live in Interview:**
     - Create `Product`: `Murukku 500 g` (`pack_weight_g = 500`, `packets_per_carton = 10` or as needed).
     - Link new `BillOfMaterials` -> `BomVersion v1` to the **existing `RecipeTemplate` (`Murukku Base Mix`)**: `expected_yield_packets = 40,000 / 500 = 80 packets`, plus `80` × `500 g pouch` and corresponding cartons!
     - Zero duplicated cooking math, zero code rewrites, and `Murukku 200 g` benchmark stays 100% untouched.

---

## 2. BOM Versioning & Historical Immutability

```
BillOfMaterials (Product: Murukku 200 g)
   ├── BomVersion v1 (Status: SUPERSEDED) ◄── Pinned by ProductionRun PRD-001 (40 kg flour, 200 pkts)
   └── BomVersion v2 (Status: ACTIVE)     ◄── Used by future runs (e.g., 42 kg flour, 205 pkts)
```

- **Rule:** An active `BomVersion` referenced by any `ProductionRun` is **strictly immutable**.
- **Recipe Update:** Editing ingredients or expected yield creates a new `BomVersion (v_n+1)`, marks `v_n` as `SUPERSEDED`, and updates `BillOfMaterials.active_version_id`.
- **Audit Guarantee:** Re-opening `PRD-001` months later always displays exact `v1` planned quantities (`40 kg`, `10 L`, `1.2 kg`, `200 pkts`), variances (`+5%`, `-6%`), and cost baselines — historical variance reports never retroactively warp!

---

## 3. Canonical Unit Conversion Algebra

Every `Material` belongs to exactly one `unit_dimension`:

| `unit_dimension` | Canonical `base_uom` | Supported Entry UOMs & Exact Rational Multiplier | Invalid Example (Blocked) |
| --- | --- | --- | --- |
| `MASS` | `g` (grams) | `g` (`× 1`), `kg` (`× 1000`) | Entering `litre` for Flour -> `400 DomainError` |
| `VOLUME` | `ml` (millilitres) | `ml` (`× 1`), `L` / `litre` (`× 1000`) | Entering `kg` for Cooking Oil -> `400 DomainError` |
| `COUNT` | `piece` | `piece` (`× 1`), `packet` (`× 1`), `carton` (`× product.packets_per_carton`) | Entering `kg` for Pouches -> `400 DomainError` |

- **Zero Drift Rule:** All `InventoryMovement` and `InventoryBalance` quantities are stored in canonical `base_uom` (`40 kg` = `40000`, `1.2 kg` = `1200`, `10.5 L` = `10500`) using exact fixed-point decimal arithmetic, formatted back to `display_uom` (`kg`, `L`) in UI/reports.

---

## 4. Production Run Execution, Packaging, Wastage & Scrap

1. **Batch Scaling (`batch_multiplier` $B$):**
   $$\text{planned\_qty\_base}(m) = \text{bom\_item.std\_qty\_base}(m) \times B$$
   $$\text{expected\_output\_qty} = \text{bom\_version.expected\_yield\_packets} \times B$$
   For Benchmark `PRD-001`, $B = 1.0 \implies \text{Expected} = 200\text{ packets}$.
2. **Raw Material Issue (`Step 2 -> IN_PROGRESS`):**
   - Supervisor confirms/adjusts actual issues: Flour `40 kg`, Oil `10.5 L`, Spice `1.2 kg`.
   - `Inventory` validates stock availability, posts `PROD_ISSUE_OUT`, and returns exact FIFO consumed cost (`₹3,390.00`).
3. **Output, Damaged Packaging & Scrap (`Step 3 -> COMPLETED`):**
   - Supervisor enters `actual_good_output_qty` (`188` packets), `process_scrap_qty` / notes (optional dough/burnt waste), plus packaging usage:
     - `200 g pouches`: `good_used = 188`, `damaged_qty = 6` -> total ledger deduction = `194` (`188` `PROD_ISSUE_OUT` + `6` `PACKAGING_DAMAGE_OUT`).
     - `Cartons`: `good_used = 9`, `damaged_qty = 0` (`9 × 20 = 180` cartoned + `8` loose packets).
   - Finished Goods increases by `+188 packets` (`PROD_OUTPUT_IN`, `50 -> 238`).

---

## 5. Planned vs Actual Variance & Tolerance Alert Logic

### 5.1 Formulas
1. **Raw Material Consumption Variance (%):**
   $$\text{ConsumptionVar\%}(m) = \frac{\text{actual\_issued\_base}(m) - \text{planned\_qty\_base}(m)}{\text{planned\_qty\_base}(m)} \times 100$$
   - *Benchmark Oil:* $\frac{10.5 - 10.0}{10.0} \times 100 = \mathbf{+5.00\%}$ (`> 3.0%` -> **FLAGGED**).
2. **Yield Variance (%):**
   $$\text{YieldVar\%} = \frac{\text{actual\_good\_output\_qty} - \text{expected\_output\_qty}}{\text{expected\_output\_qty}} \times 100$$
   - *Benchmark Packets:* $\frac{188 - 200}{200} \times 100 = \mathbf{-6.00\%}$ (`|-6.00%| > 3.0%` -> **FLAGGED**).
3. **Packaging Consumption Variance (%) — Output-Scaled Rule (`BR-VAR-03`):**
   - Compare total pouches consumed (`194`) against **packets actually packed** (`188`):
     $$\frac{194 - 188}{188} \times 100 = \mathbf{+3.19\%}\text{ wastage } (> 3.0\% \rightarrow \textbf{FLAGGED})$$
   - *(Batch BOM planned `200` is displayed alongside in audit columns for full transparency.)*
   - For cartons: `9` used vs `floor(188 / 20) = 9` whole cartons expected = `0.00%` (`8` loose packets noted).

### 5.2 Alert Generation
Whenever $|\text{Variance\%}| > \text{CompanyProfile.variance\_tolerance\_pct}$ (`3.0%`), the domain automatically persists a `VarianceAlert` record (`OPEN`) visible immediately to the Production Supervisor and Owner.
