# Inventory Ledger & Stock Physical Schema (`inventory` Schema)

**Mandate:** Every stock change is stored as an immutable `inventory.inventory_movements` row linked by genuine PostgreSQL foreign keys to its exact source document. Direct overwriting of stock balances is architecturally and technically blocked.

---

## 1. Tables in `inventory` Schema

### 1.1 `inventory.opening_balances`
*Purpose:* Anchors seeded/opening inventory quantities (`100 kg` Flour, `50` Murukku 200 g packets) as real source documents so `OPENING` ledger movements have strict FK traceability without dummy exceptions.
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `batch_ref VARCHAR(40) NOT NULL` (e.g., `'SEED-BENCHMARK-2026'`)
- `item_category VARCHAR(20) NOT NULL CHECK (item_category IN ('RAW_MATERIAL','PACKAGING_MATERIAL','FINISHED_GOOD'))`
- `material_id BIGINT NULL REFERENCES production.materials(id) ON DELETE RESTRICT`
- `pack_size_id BIGINT NULL REFERENCES sales.pack_sizes(id) ON DELETE RESTRICT`
- `opening_qty_base NUMERIC(18,3) NOT NULL CHECK (opening_qty_base > 0)`
- `unit_cost_paisa_per_base NUMERIC(18,6) NOT NULL CHECK (unit_cost_paisa_per_base >= 0)`
- `as_of_date DATE NOT NULL`
- `created_by BIGINT NOT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **Constraint (`chk_ob_one_item`):** Exclusive arc ensuring `material_id` is set for raw/packaging and `pack_size_id` for finished goods.
- **Unique:** `UNIQUE (batch_ref, material_id)` partial `WHERE material_id IS NOT NULL`; `UNIQUE (batch_ref, pack_size_id)` partial `WHERE pack_size_id IS NOT NULL`.

### 1.2 `inventory.inventory_balances` *(Concurrency Lock Anchor & Materialized Projection)*
*Purpose:* Stores `(on_hand_qty_base, reserved_qty_base)` per item purely as a row-lock target (`SELECT ... FOR UPDATE`) and reconciled read cache. **Never** updated outside the `Inventory` transactional service alongside an `inventory_movements` append.
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `item_category VARCHAR(20) NOT NULL CHECK (item_category IN ('RAW_MATERIAL','PACKAGING_MATERIAL','FINISHED_GOOD'))`
- `material_id BIGINT NULL REFERENCES production.materials(id) ON DELETE RESTRICT`
- `pack_size_id BIGINT NULL REFERENCES sales.pack_sizes(id) ON DELETE RESTRICT`
- `on_hand_qty_base NUMERIC(18,3) NOT NULL DEFAULT 0 CHECK (on_hand_qty_base >= 0)`
- `reserved_qty_base NUMERIC(18,3) NOT NULL DEFAULT 0 CHECK (reserved_qty_base >= 0)`
- `available_qty_base NUMERIC(18,3) GENERATED ALWAYS AS (on_hand_qty_base - reserved_qty_base) STORED`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **Constraints:**
  - `chk_bal_one_item`: Exclusive arc between `material_id` and `pack_size_id`.
  - `chk_bal_reserved_cap`: `CHECK (reserved_qty_base <= on_hand_qty_base)` — **Hard database guarantee** preventing overselling even under concurrent admin tabs (`EC-03`)!
- **Partial Unique Indexes:** `uq_bal_material (material_id) WHERE material_id IS NOT NULL`, `uq_bal_pack_size (pack_size_id) WHERE pack_size_id IS NOT NULL`.

### 1.3 `inventory.cost_lots` *(FIFO Cost Layers & Optional Batch/Expiry FEFO)*
*Purpose:* Tracks open valuation layers created by `OPENING`, `PURCHASE_IN`, `PROD_OUTPUT_IN`, or `CREDIT_RETURN_IN`.
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `item_category VARCHAR(20) NOT NULL CHECK (item_category IN ('RAW_MATERIAL','PACKAGING_MATERIAL','FINISHED_GOOD'))`
- `material_id BIGINT NULL REFERENCES production.materials(id) ON DELETE RESTRICT`
- `pack_size_id BIGINT NULL REFERENCES sales.pack_sizes(id) ON DELETE RESTRICT`
- `source_doc_type VARCHAR(24) NOT NULL CHECK (source_doc_type IN ('OPENING_BALANCE','PURCHASE_RECEIPT','PRODUCTION_RUN','CREDIT_NOTE','STOCK_ADJUSTMENT'))`
- `source_doc_id BIGINT NOT NULL`
- `batch_code VARCHAR(40) NULL`
- `expiry_date DATE NULL`
- `original_qty_base NUMERIC(18,3) NOT NULL CHECK (original_qty_base > 0)`
- `remaining_qty_base NUMERIC(18,3) NOT NULL CHECK (remaining_qty_base >= 0 AND remaining_qty_base <= original_qty_base)`
- `unit_cost_paisa_per_base NUMERIC(18,6) NOT NULL CHECK (unit_cost_paisa_per_base >= 0)`
- `received_at TIMESTAMPTZ NOT NULL`
- **Indexes:** `idx_lots_fifo_open (material_id, received_at, id) WHERE remaining_qty_base > 0`, `idx_lots_fg_fefo (pack_size_id, expiry_date NULLS LAST, received_at, id) WHERE remaining_qty_base > 0`.

### 1.4 `inventory.stock_adjustments`
*Purpose:* Controlled, reason-logged adjustment voucher for physical count variance or non-run floor spoilage (`ADJ`).
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `adjustment_number VARCHAR(32) NOT NULL UNIQUE`
- `item_category VARCHAR(20) NOT NULL CHECK (item_category IN ('RAW_MATERIAL','PACKAGING_MATERIAL','FINISHED_GOOD'))`
- `material_id BIGINT NULL REFERENCES production.materials(id) ON DELETE RESTRICT`
- `pack_size_id BIGINT NULL REFERENCES sales.pack_sizes(id) ON DELETE RESTRICT`
- `delta_qty_base NUMERIC(18,3) NOT NULL CHECK (delta_qty_base <> 0)`
- `unit_cost_paisa_per_base NUMERIC(18,6) NOT NULL CHECK (unit_cost_paisa_per_base >= 0)`
- `reason TEXT NOT NULL CHECK (length(trim(reason)) >= 5)`
- `status VARCHAR(16) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','POSTED','REJECTED'))`
- `requested_by BIGINT NOT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `approved_by BIGINT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- `posted_at TIMESTAMPTZ NULL`

### 1.5 `inventory.inventory_movements` *(The Authoritative Append-Only Stock Ledger)*
*Purpose:* Immutable passbook of every physical stock change across the factory.
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `item_category VARCHAR(20) NOT NULL CHECK (item_category IN ('RAW_MATERIAL','PACKAGING_MATERIAL','FINISHED_GOOD'))`
- `material_id BIGINT NULL REFERENCES production.materials(id) ON DELETE RESTRICT`
- `pack_size_id BIGINT NULL REFERENCES sales.pack_sizes(id) ON DELETE RESTRICT`
- `movement_type VARCHAR(28) NOT NULL CHECK (movement_type IN ('OPENING','PURCHASE_IN','PROD_ISSUE_OUT','PACKAGING_DAMAGE_OUT','PROD_OUTPUT_IN','PROD_RETURN_IN','DISPATCH_OUT','CREDIT_RETURN_IN','ADJUSTMENT'))`
- `signed_qty_base NUMERIC(18,3) NOT NULL CHECK (signed_qty_base <> 0)`
- `unit_cost_paisa_per_base NUMERIC(18,6) NOT NULL CHECK (unit_cost_paisa_per_base >= 0)`
- `total_cost_paisa BIGINT NOT NULL CHECK (total_cost_paisa >= 0)`
- **Strict Source Document Foreign Keys (Exclusive-Arc Traceability):**
  - `source_doc_type VARCHAR(24) NOT NULL CHECK (source_doc_type IN ('OPENING_BALANCE','PURCHASE_RECEIPT','PRODUCTION_RUN','DISPATCH','CREDIT_NOTE','STOCK_ADJUSTMENT'))`
  - `opening_balance_id BIGINT NULL REFERENCES inventory.opening_balances(id) ON DELETE RESTRICT`
  - `purchase_receipt_item_id BIGINT NULL REFERENCES purchasing.purchase_receipt_items(id) ON DELETE RESTRICT`
  - `production_run_id BIGINT NULL REFERENCES production.production_runs(id) ON DELETE RESTRICT`
  - `dispatch_item_id BIGINT NULL REFERENCES billing.dispatch_items(id) ON DELETE RESTRICT`
  - `credit_note_item_id BIGINT NULL REFERENCES billing.credit_note_items(id) ON DELETE RESTRICT`
  - `stock_adjustment_id BIGINT NULL REFERENCES inventory.stock_adjustments(id) ON DELETE RESTRICT`
  - **PostgreSQL `num_nonnulls` Constraint (`chk_mov_single_source`):**
    `CHECK (num_nonnulls(opening_balance_id, purchase_receipt_item_id, production_run_id, dispatch_item_id, credit_note_item_id, stock_adjustment_id) = 1)`
- `occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `created_by BIGINT NOT NULL REFERENCES iam.users(id) ON DELETE RESTRICT`
- **Sign Semantics CHECK (`chk_mov_sign_direction`):** Asserts `OPENING`, `PURCHASE_IN`, `PROD_OUTPUT_IN`, `PROD_RETURN_IN`, `CREDIT_RETURN_IN` have `signed_qty_base > 0`, while `PROD_ISSUE_OUT`, `PACKAGING_DAMAGE_OUT`, `DISPATCH_OUT` have `signed_qty_base < 0`.

### 1.6 `inventory.cost_lot_consumptions`
*Purpose:* Records exact M:N attribution between outbound movements (`PROD_ISSUE_OUT`, `PACKAGING_DAMAGE_OUT`, `DISPATCH_OUT`) and the FIFO `CostLot`s they consumed.
- `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `inventory_movement_id BIGINT NOT NULL REFERENCES inventory.inventory_movements(id) ON DELETE RESTRICT`
- `cost_lot_id BIGINT NOT NULL REFERENCES inventory.cost_lots(id) ON DELETE RESTRICT`
- `consumed_qty_base NUMERIC(18,3) NOT NULL CHECK (consumed_qty_base > 0)`
- `unit_cost_paisa_per_base NUMERIC(18,6) NOT NULL`
- `cost_paisa BIGINT NOT NULL CHECK (cost_paisa >= 0)`
- **Unique:** `UNIQUE (inventory_movement_id, cost_lot_id)`

---

## 2. How Cached Balances Stay 100% Honest Without Compromising the Ledger

1. **Single Atomic Write Gate:** Only the `Inventory` service writes to `inventory_balances`, and **only** inside the same transaction (`TX-04`, `TX-07`, `TX-08`, `TX-09`) that inserts `inventory_movements` — OR via an `AFTER INSERT` PostgreSQL trigger on `inventory_movements` that applies `on_hand_qty_base = on_hand_qty_base + NEW.signed_qty_base`!
   - *Design choice:* Using a PostgreSQL `AFTER INSERT` trigger on `inventory_movements` to update `inventory_balances.on_hand_qty_base` makes it **mathematically impossible** for any query or future script to append a ledger row without updating `inventory_balances` (and `CHECK (on_hand_qty_base >= 0)` + `CHECK (reserved_qty_base <= on_hand_qty_base)` reject any negative or over-reserved state inside the database itself!).
   - Meanwhile, `reserved_qty_base` is explicitly managed under `SELECT ... FOR UPDATE` during Order Approval (`TX-02`) and released on Dispatch (`TX-04`) or Cancellation (`TX-05`).
2. **Append-Only Enforcement:** `BEFORE UPDATE OR DELETE` trigger on `inventory_movements` raises an exception unconditionally (`INV-STK-03` / `NFR-03`).
3. **Continuous Reconciliation View (`reporting.v_stock_reconciliation`):** Compares `inventory_balances.on_hand_qty_base` against `COALESCE(SUM(inventory_movements.signed_qty_base), 0)`; auditors verify `drift_qty_base = 0.000` for every SKU and material.
