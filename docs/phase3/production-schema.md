# BOM, Production & Costing Schema (`production` & `costing` Schemas)

Designed to handle unit conversion integrity, historical BOM immutability, multi-pack BOM sharing (`200 g` and `500 g`), damaged packaging tracking, variance alerts, and absorption costing.

---

## 1. Material & Unit Conversion Master Tables

### `production.materials`
- **Purpose:** Unified catalog of Raw Materials (`Flour`, `Cooking oil`, `Salt and spice mix`) and Packaging Materials (`200 g pouch`, `Carton`). *(Justified over 2 separate tables so `inventory_movements`, `purchase_receipt_items`, and `bom_components` reference a single clean `material_id` FK without duplicated ledger columns.)*
- **Columns:**
  - `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
  - `code VARCHAR(32) NOT NULL UNIQUE`
  - `name VARCHAR(120) NOT NULL`
  - `material_category VARCHAR(24) NOT NULL CHECK (material_category IN ('RAW_MATERIAL','PACKAGING_MATERIAL'))`
  - `unit_dimension VARCHAR(16) NOT NULL CHECK (unit_dimension IN ('MASS','VOLUME','COUNT'))`
  - `base_uom VARCHAR(16) NOT NULL CHECK (base_uom IN ('g','ml','piece'))`
  - `display_uom VARCHAR(16) NOT NULL` (`'kg'`, `'L'`, `'piece'`)
  - `reorder_level_base NUMERIC(18,3) NOT NULL DEFAULT 0 CHECK (reorder_level_base >= 0)`
  - `is_active BOOLEAN NOT NULL DEFAULT TRUE`
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **Dimension Integrity CHECK (`chk_mat_dim_base`):**
  `CHECK ((unit_dimension='MASS' AND base_uom='g') OR (unit_dimension='VOLUME' AND base_uom='ml') OR (unit_dimension='COUNT' AND base_uom='piece'))`

### `production.unit_conversions`
- **Columns:** `id BIGINT PK`, `from_uom VARCHAR(16) NOT NULL`, `to_base_uom VARCHAR(16) NOT NULL`, `unit_dimension VARCHAR(16) NOT NULL`, `multiplier NUMERIC(18,6) NOT NULL CHECK (multiplier > 0)`
- **Unique:** `UNIQUE (from_uom, to_base_uom)`
- **Seeded Exact Multipliers:** `(kg -> g, MASS, 1000)`, `(g -> g, MASS, 1)`, `(L -> ml, VOLUME, 1000)`, `(ml -> ml, VOLUME, 1)`, `(piece -> piece, COUNT, 1)`, `(packet -> packet, COUNT, 1)`. *(Carton-to-packet conversion uses `sales.pack_sizes.packets_per_carton` per SKU!)*

---

## 2. Supporting Multi-Pack Sizes Sharing the Same BOM

Look at how `sales.products`, `sales.pack_sizes`, `production.recipe_templates`, `production.bom_headers`, `production.bom_versions`, and `production.bom_components` solve the Section 9 live interview change (*"add a second pack size of 500 g sharing the same BOM"*):

1. **`sales.products`** defines the base snack family (`Murukku`, HSN `21069099`, `5%` GST).
2. **`sales.pack_sizes`** defines concrete sellable pack variants (`Murukku 200 g`: `pack_weight_g = 200`, `packets_per_carton = 20`; `Murukku 500 g`: `pack_weight_g = 500`, `packets_per_carton = 10`).
3. **`production.recipe_templates`** defines the shared bulk cooking formula for `Murukku` (`Murukku Base Mix`, `base_yield_weight_g = 40000.000`, storing or templating `40 kg` flour, `10 L` oil, `1.2 kg` spice).
4. **`production.bom_headers`** has a `1:1` FK (`pack_size_id UNIQUE`) and `active_version_id` pointing to the currently active `production.bom_versions`.
5. **`production.bom_versions`** (`version_no INT`, `recipe_template_id BIGINT NULL`, `expected_yield_pkts INT`, `status IN ('DRAFT','ACTIVE','SUPERSEDED')`):
   - For `Murukku 200 g`: links `recipe_template_id` -> `Murukku Base Mix`, `expected_yield_pkts = 200`, and its `bom_components` hold cooking ingredients (`40 kg` flour, `10 L` oil, `1.2 kg` spice) + packaging (`200` × `200 g pouch`, `10` × `Carton`).
   - Adding `Murukku 500 g`: create new `pack_size` (`500 g`) + `bom_header` + `bom_version` referencing the **same `recipe_template_id`** (`expected_yield_pkts = 40000 / 500 = 80`), copying cooking ingredients automatically while customizing `80` × `500 g pouch` and carton ratio!
6. **Historical Immutability Guarantee:**
   - Every `production_runs` row references `bom_version_id BIGINT NOT NULL REFERENCES production.bom_versions(id) ON DELETE RESTRICT`.
   - A PostgreSQL trigger (plus application guard) **forbids updating `expected_yield_pkts` or `bom_components` once `bom_versions.status <> 'DRAFT'`** or if referenced by any `production_runs` row. Recipe edits must insert `version_no + 1` and flip the old version to `SUPERSEDED` (preserving `UNIQUE (bom_header_id) WHERE status = 'ACTIVE'`).

---

## 3. Production Execution, Output, Wastage & Variance Tables

### `production.production_runs`
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `run_number VARCHAR(32) NOT NULL UNIQUE` (`'PRD-2026-0001'`)
- `pack_size_id BIGINT NOT NULL REFERENCES sales.pack_sizes(id) ON DELETE RESTRICT`
- `bom_version_id BIGINT NOT NULL REFERENCES production.bom_versions(id) ON DELETE RESTRICT`
- `batch_multiplier NUMERIC(10,4) NOT NULL CHECK (batch_multiplier > 0)`
- `expected_output_pkts INT NOT NULL CHECK (expected_output_pkts > 0)`
- `actual_good_output_pkts INT NOT NULL DEFAULT 0 CHECK (actual_good_output_pkts >= 0)`
- `status VARCHAR(20) NOT NULL CHECK (status IN ('DRAFT','PLANNED','IN_PROGRESS','COMPLETED','POSTED','CANCELLED'))`
- `run_date DATE NOT NULL`
- `started_at TIMESTAMPTZ NULL`, `completed_at TIMESTAMPTZ NULL`, `posted_at TIMESTAMPTZ NULL`
- `supervisor_id BIGINT NOT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `notes TEXT NULL`

### `production.production_material_issues`
*Purpose:* Captures planned vs actual raw material & packaging usage per run (Phase 1 Step 2 & Step 3).
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `production_run_id BIGINT NOT NULL REFERENCES production.production_runs(id) ON DELETE RESTRICT`
- `material_id BIGINT NOT NULL REFERENCES production.materials(id) ON DELETE RESTRICT`
- `issue_phase VARCHAR(20) NOT NULL CHECK (issue_phase IN ('RAW_ISSUE','PACKAGING_PACK'))`
- `planned_qty_base NUMERIC(18,3) NOT NULL CHECK (planned_qty_base >= 0)`
- `actual_good_used_base NUMERIC(18,3) NOT NULL CHECK (actual_good_used_base >= 0)`
- `damaged_qty_base NUMERIC(18,3) NOT NULL DEFAULT 0 CHECK (damaged_qty_base >= 0)`
- `returned_qty_base NUMERIC(18,3) NOT NULL DEFAULT 0 CHECK (returned_qty_base >= 0)`
- `cost_absorbed_paisa BIGINT NOT NULL DEFAULT 0 CHECK (cost_absorbed_paisa >= 0)`
- `issued_by BIGINT NOT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **Unique:** `UNIQUE (production_run_id, material_id, issue_phase)`

### `production.production_outputs`
*Purpose:* Records finished good output batches (`188` packets) and optional `batch_code` / `expiry_date` for food safety & FEFO stretch readiness.
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `production_run_id BIGINT NOT NULL REFERENCES production.production_runs(id) ON DELETE RESTRICT`
- `pack_size_id BIGINT NOT NULL REFERENCES sales.pack_sizes(id) ON DELETE RESTRICT`
- `good_qty_pkts INT NOT NULL CHECK (good_qty_pkts > 0)`
- `batch_code VARCHAR(40) NOT NULL`
- `expiry_date DATE NULL`
- `recorded_by BIGINT NOT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

### `production.production_wastages`
*Purpose:* Records physical losses separately (`6` damaged `200 g pouches`, burnt batch dough, oil spillage) with financial impact and reason.
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `production_run_id BIGINT NOT NULL REFERENCES production.production_runs(id) ON DELETE RESTRICT`
- `material_id BIGINT NULL REFERENCES production.materials(id) ON DELETE RESTRICT`
- `wastage_type VARCHAR(28) NOT NULL CHECK (wastage_type IN ('DAMAGED_PACKAGING','COOKING_SCRAP','BURNT_BATCH','SPILLAGE'))`
- `qty_base NUMERIC(18,3) NOT NULL CHECK (qty_base > 0)`
- `cost_impact_paisa BIGINT NOT NULL DEFAULT 0 CHECK (cost_impact_paisa >= 0)`
- `reason TEXT NOT NULL`
- `recorded_by BIGINT NOT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

### `production.production_variances`
*Purpose:* Stores deterministic planned-vs-actual variance evaluations (`Oil +5.00%`, `Yield -6.00%`, `Pouches +3.19%`) and triggers `audit.variance_alerts` whenever `ABS(variance_pct) > tolerance_pct`.
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `production_run_id BIGINT NOT NULL REFERENCES production.production_runs(id) ON DELETE RESTRICT`
- `variance_scope VARCHAR(28) NOT NULL CHECK (variance_scope IN ('YIELD','RAW_CONSUMPTION','PACKAGING_CONSUMPTION'))`
- `material_id BIGINT NULL REFERENCES production.materials(id) ON DELETE RESTRICT`
- `planned_qty_base NUMERIC(18,3) NOT NULL CHECK (planned_qty_base > 0)`
- `actual_qty_base NUMERIC(18,3) NOT NULL CHECK (actual_qty_base >= 0)`
- `variance_pct NUMERIC(8,2) NOT NULL`
- `tolerance_pct NUMERIC(5,2) NOT NULL CHECK (tolerance_pct >= 0)`
- `is_flagged BOOLEAN NOT NULL`
- `computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

---

## 4. `costing` Schema Tables

### `costing.production_overheads`
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `production_run_id BIGINT NULL REFERENCES production.production_runs(id) ON DELETE RESTRICT`
- `period_month CHAR(7) NOT NULL CHECK (period_month ~ '^[0-9]{4}-[0-9]{2}$')`
- `overhead_type VARCHAR(24) NOT NULL CHECK (overhead_type IN ('LABOUR','GAS_POWER','RENT_SHARED','SUPERVISION','OTHER'))`
- `allocation_scope VARCHAR(20) NOT NULL CHECK (allocation_scope IN ('DIRECT_RUN','MONTHLY_POOL'))`
- `amount_paisa BIGINT NOT NULL CHECK (amount_paisa >= 0)`
- `notes TEXT NULL`
- `recorded_by BIGINT NOT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **Check (`chk_ovh_scope_run`):** `CHECK ((allocation_scope='DIRECT_RUN' AND production_run_id IS NOT NULL) OR (allocation_scope='MONTHLY_POOL' AND production_run_id IS NULL))`

### `costing.production_cost_summaries`
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `production_run_id BIGINT NOT NULL UNIQUE REFERENCES production.production_runs(id) ON DELETE RESTRICT`
- `valuation_method VARCHAR(24) NOT NULL CHECK (valuation_method IN ('FIFO','WEIGHTED_AVERAGE','LAST_PRICE'))`
- `raw_material_cost_paisa BIGINT NOT NULL CHECK (raw_material_cost_paisa >= 0)`
- `packaging_cost_paisa BIGINT NOT NULL CHECK (packaging_cost_paisa >= 0)`
- `direct_overhead_paisa BIGINT NOT NULL DEFAULT 0 CHECK (direct_overhead_paisa >= 0)`
- `allocated_overhead_paisa BIGINT NOT NULL DEFAULT 0 CHECK (allocated_overhead_paisa >= 0)`
- `total_cost_paisa BIGINT GENERATED ALWAYS AS (raw_material_cost_paisa + packaging_cost_paisa + direct_overhead_paisa + allocated_overhead_paisa) STORED`
- `good_packets INT NOT NULL CHECK (good_packets >= 0)`
- `cost_per_packet_paisa BIGINT NULL CHECK (cost_per_packet_paisa IS NULL OR cost_per_packet_paisa >= 0)`
- `selling_price_snapshot_paisa BIGINT NOT NULL CHECK (selling_price_snapshot_paisa >= 0)`
- `gross_margin_paisa BIGINT NULL`
- `computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **Check (`chk_pcs_nonzero_yield`):** `CHECK ((good_packets = 0 AND cost_per_packet_paisa IS NULL) OR (good_packets > 0 AND cost_per_packet_paisa IS NOT NULL))`
