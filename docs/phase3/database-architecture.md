# Phase 3 — PostgreSQL Database Architecture

**Phase:** Physical Database Engineering (PostgreSQL 16+)  
**Source Baseline:** Approved [Phase 1](file:///d:/mac/ota/docs/phase1) and [Phase 2](file:///d:/mac/ota/docs/phase2) deliverables  
**Scope Notice:** Complete physical PostgreSQL architecture and design specifications. No SQL migration files or backend/frontend code are generated until Phase 3 approval.

---

## 1. Why PostgreSQL Is Appropriate

1. **Strict ACID & Pessimistic Concurrency (`SELECT ... FOR UPDATE`):** Concurrent salesmen approvals, inventory reservations, FIFO cost-lot depletions, and FY invoice sequence generation require row-level pessimistic locking (`NOWAIT` / deterministic lock order) inside ACID transactions to mathematically eliminate overselling and sequence gaps.
2. **Expressive Database-Enforced Integrity:** PostgreSQL natively supports `CHECK` constraints (including `num_nonnulls(...) = 1` for exclusive-arc FKs), partial `UNIQUE` indexes (`WHERE is_default IS TRUE`), `GENERATED ALWAYS AS (...) STORED` derived invariants, and `ON DELETE RESTRICT` across ledger/invoice records.
3. **Exact Numeric & Integer-Paisa Arithmetic:** Native `BIGINT` (`64-bit` signed integers) for exact integer paise plus arbitrary-precision base-10 `NUMERIC(18, 6)` for metric base-unit conversions and sub-paisa unit costs (`₹42/kg = 4.200000 paise/g`) guarantee zero IEEE-754 floating-point drift.
4. **Native Immutability & Audit Infrastructure:** Row triggers (`BEFORE UPDATE OR DELETE`) combined with PostgreSQL role privileges (`REVOKE UPDATE, DELETE`) protect `inventory_movements` and `audit_logs` even against misbehaving SQL clients; `JSONB` stores structured `before_state` / `after_state` audit snapshots cleanly.
5. **Timezone-Correct Financial Boundaries (`TIMESTAMPTZ`):** Instantaneous UTC storage with deterministic `AT TIME ZONE 'Asia/Kolkata'` conversion ensures Indian Financial Year (`April 1 – March 31`) boundaries and daily KPI rollups never break near midnight IST.

---

## 2. Database Schemas & Logical Module Separation

Mapping Phase 2's 10 bounded modules onto 9 PostgreSQL schemas enforces clear ownership inside a single ACID database:

| PostgreSQL Schema | Bounded Module Owner | Tables / Objects Owned | Access Pattern |
| --- | --- | --- | --- |
| **`iam`** | Identity & Access Management | `company_profiles`, `roles`, `users` | Foundation read across modules; admin-managed |
| **`sales`** | Customer & Sales + Orders | `salesman_profiles`, `customers`, `customer_addresses`, `products`, `pack_sizes`, `price_lists`, `price_list_items`, `sales_orders`, `sales_order_items`, `sales_order_status_history`, `sales_order_approvals` | Salesman mobile + Admin verification |
| **`purchasing`** | Purchasing & Suppliers | `suppliers`, `purchase_orders`, `purchase_order_items`, `purchase_receipts`, `purchase_receipt_items` | Supervisor & Admin intake |
| **`production`** | Production & BOM | `materials`, `unit_conversions`, `recipe_templates`, `bom_headers`, `bom_versions`, `bom_components`, `production_runs`, `production_material_issues`, `production_outputs`, `production_wastages`, `production_variances` | Floor Supervisor + BOM masters |
| **`costing`** | Production Costing | `production_overheads`, `production_cost_summaries` | Costing engine + Owner/Auditor |
| **`inventory`** | Inventory Ledger & Lots | `opening_balances`, `inventory_balances`, `cost_lots`, `cost_lot_consumptions`, `stock_adjustments`, `inventory_movements` | **Single stock writer**; atomic lock target |
| **`billing`** | Billing, GST & Dispatch | `fiscal_sequences`, `invoices`, `invoice_items`, `invoice_tax_components`, `credit_notes`, `credit_note_items`, `dispatches`, `dispatch_items` | Admin billing & dispatch desk |
| **`finance`** | Payments & Receivables | `payments`, `payment_allocations`, `customer_receivables` | Admin collections & AR tracking |
| **`audit`** | Audit & Alert Governance | `variance_alerts`, `audit_logs` | Append-only audit & alert queue |
| **`reporting`** | Reporting Read Models | Read-only SQL `VIEW`s (`v_sales_register`, `v_gst_outward_summary`, `v_purchase_register`, `v_stock_reconciliation`, `v_production_summary`, `v_ar_ageing`) | Strictly read-only for `ACCOUNTANT_AUDITOR` & `OWNER` |

---

## 3. Naming Conventions

- **Schemas & Tables:** Lowercase `snake_case`, plural nouns for entity tables (`sales_orders`, `inventory_movements`).
- **Columns:** Lowercase `snake_case`; booleans prefixed `is_` or `has_` (`is_active`, `is_flagged`); money columns suffixed `_paisa`; basis-point tax/rate columns suffixed `_bps`; base-unit quantities suffixed `_base` (or explicit unit suffix like `_g`, `_pkts`); timestamps suffixed `_at`.
- **Constraints & Indexes:**
  - Primary Key: `pk_<table>`
  - Foreign Key: `fk_<table_short>_<ref_short>`
  - Unique: `uq_<table_short>_<cols>`
  - Check: `chk_<table_short>_<rule>`
  - Index: `idx_<table_short>_<cols>`

---

## 4. Primary & Foreign Key Strategy: `BIGINT` vs `UUID` Trade-Offs

| Dimension | `BIGINT GENERATED ALWAYS AS IDENTITY` *(Chosen Internal PK)* | `UUID` (`gen_random_uuid()` / v7) |
| --- | --- | --- |
| **Storage & Index Density** | **8 bytes**; keeps B-tree indexes compact (`~2×` more keys per 8 KB page than 16-byte UUID). | **16 bytes**; larger indexes on high-write ledger/audit tables. |
| **Insert Locality** | Strictly monotonic (`+1`), zero B-tree page fragmentation on `inventory_movements` & `audit_logs`. | Random UUID v4 causes B-tree page splits and cache churn. |
| **Deadlock-Free Lock Ordering** | Deterministic `ORDER BY id ASC` across `inventory_balances` & `cost_lots`. | Harder to eyeball in debugging / logs. |
| **External Exposure & Idempotency** | Sequential IDs must **never** be trusted for authorization or guessed directly as mobile idempotency tokens. | **Essential** for mobile offline/retry idempotency (`client_order_id`, `idempotency_key`) and optional external `public_uid` exposure. |

**Hybrid Strategy Adopted:**
- Every table uses **`id BIGINT GENERATED ALWAYS AS IDENTITY`** as its internal `PRIMARY KEY` and relational `FOREIGN KEY` target.
- Mobile/payment idempotency columns (`sales_orders.client_order_id`, `payments.idempotency_key`) and optional external document UUIDs use **`UUID NOT NULL`** with `UNIQUE` constraints.
- Strict `ON DELETE RESTRICT` on all transactional FKs prevents accidental cascade deletion of financial, production, or stock history; `ON DELETE CASCADE` is permitted *only* on pure draft line children prior to posting (e.g., draft order items if a draft is discarded — blocked once submitted/posted!).

---

## 5. Timestamp & Timezone Strategy

- **All event/audit timestamps:** `TIMESTAMPTZ NOT NULL DEFAULT NOW()` (stored in UTC; prevents DST/server-locale shifts).
- **Business dates (Invoice Date, Receipt Date, Order Date, Expiry Date):** `DATE NOT NULL` representing calendar factory date in `Asia/Kolkata` (`IST`), used deterministically for Indian FY calculation (`EXTRACT(MONTH FROM invoice_date) >= 4`) and AR ageing (`CURRENT_DATE - invoice_date`).
- **Mutation tracking:** Master tables carry `created_at` and `updated_at` (`TIMESTAMPTZ`); immutable tables (`inventory_movements`, `audit_logs`, `sales_order_status_history`) carry only `occurred_at` / `created_at`.

---

## 6. Decimal Precision & Integer-Paisa Money Strategy

1. **Monetary Totals, Prices, Taxes & Overheads (`BIGINT` Paise):**
   - `1 INR = 100 paise` (`₹7,875.00 = 787500`). Stored as `BIGINT` (`±9.22 × 10^16` paise = `₹9.22 × 10^14` — vastly exceeds SME limits).
   - Tax rates stored as integer **basis points (`INTEGER` `_bps`)**: `5.00% = 500 bps`, `2.50% = 250 bps`.
   - Tax calculation formula in integer math (`ROUND_HALF_UP`):
     `tax_paisa = ((taxable_paisa * rate_bps) + 5000) / 10000` (for non-negative taxable amounts).
2. **Base-Unit Quantities (`NUMERIC(18, 3)`):**
   - Canonical base units (`g`, `ml`, `piece`, `packet`) stored as `NUMERIC(18, 3)` so `40 kg` = `40000.000`, `1.2 kg` = `1200.000`, `10.5 L` = `10500.000`, and fractional grams never lose precision.
3. **Sub-Paisa Unit Cost Rates (`NUMERIC(18, 6)`):**
   - **Critical Edge Catch:** `₹42.00 / kg` equals `4.200000 paise / gram` — **not** an integer number of paise per gram! Storing `unit_cost` per base gram as an integer `BIGINT` would truncate `4.2 -> 4`, creating a `4.76%` costing error!
   - Therefore:
     - `entered_unit_rate_paisa` (`BIGINT`) stores exact entered rate per display unit (e.g., `4200` paise/kg).
     - `unit_cost_paisa_per_base` (`NUMERIC(18, 6)`) stores exact cost per canonical base unit (`4.200000` paise/g; `4.500000` paise/g; `4.312500` paise/g if WAvg is ever chosen).
     - When consuming `40000.000 g × 4.200000 paise/g`, exact multiplication gives `168000` paise (`₹1,680.00`) rounded (`ROUND_HALF_UP`) to `BIGINT` `total_cost_paisa`!
4. **Percentages & Variances (`NUMERIC(8, 2)`):**
   - Tolerance (`3.00`), yield variance (`-6.00`), consumption variance (`+5.00`, `+3.19`).

---

## 7. Enum vs `VARCHAR` + `CHECK` Strategy

Use **`VARCHAR(32)` + explicit `CHECK (col IN (...))` constraints** rather than PostgreSQL `CREATE TYPE ... AS ENUM` for lifecycle statuses and categories. *Justification:* Adding a new status or movement type later in PostgreSQL with `CHECK` constraints uses safe transactional `ALTER TABLE ... DROP CONSTRAINT / ADD CONSTRAINT`, avoiding `ALTER TYPE ... ADD VALUE` migration lock/rollback limitations.
