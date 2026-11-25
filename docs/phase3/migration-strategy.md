# PostgreSQL Migration Strategy & Lifecycle Governance

Migrations will be managed through versioned, linear, transactionally wrapped forward migrations (generated only after Phase 3 approval).

---

## 1. Dependency-Ordered Migration Sequence (`V001` – `V012`)

| Migration | Scope | Dependencies | Rollback Strategy (Dev vs Live) |
| --- | --- | --- | --- |
| **`V001`** | Create Schemas (`iam`, `sales`, `purchasing`, `production`, `costing`, `inventory`, `billing`, `finance`, `audit`, `reporting`) & Extensions (`pgcrypto`, optional `pg_trgm`) | None | Drop empty schemas (dev only) |
| **`V002`** | `iam` tables (`company_profiles`, `roles`, `users`) | `V001` | Drop `iam` tables (pre-prod only) |
| **`V003`** | Commercial Masters (`sales.salesman_profiles`, `customers`, `customer_addresses`, `products`, `pack_sizes`, `price_lists`, `price_list_items`) | `V002` | Reverse drop (pre-prod) |
| **`V004`** | Production Masters (`production.materials`, `unit_conversions`, `recipe_templates`, `bom_headers`, `bom_versions`, `bom_components`) & `purchasing.suppliers` | `V002`, `V003` | Reverse drop (pre-prod) |
| **`V005`** | Purchasing Transactions (`purchase_orders`, `purchase_order_items`, `purchase_receipts`, `purchase_receipt_items`) | `V004` | Reverse drop (pre-prod) |
| **`V006`** | Production Execution & Costing (`production_runs`, `production_material_issues`, `production_outputs`, `production_wastages`, `production_variances`, `costing.production_overheads`, `costing.production_cost_summaries`) | `V003`, `V004` | Reverse drop (pre-prod) |
| **`V007`** | Sales Orders (`sales_orders`, `sales_order_items`, `sales_order_status_history`, `sales_order_approvals`) | `V003` | Reverse drop (pre-prod) |
| **`V008`** | Billing & Dispatch (`fiscal_sequences`, `invoices`, `invoice_items`, `invoice_tax_components`, `credit_notes`, `credit_note_items`, `dispatches`, `dispatch_items`) | `V007` | Reverse drop (pre-prod) |
| **`V009`** | Finance & AR (`payments`, `payment_allocations`, `customer_receivables`) | `V008` | Reverse drop (pre-prod) |
| **`V010`** | Inventory Ledger (`opening_balances`, `inventory_balances`, `cost_lots`, `cost_lot_consumptions`, `stock_adjustments`, `inventory_movements`) | `V004`, `V005`, `V006`, `V008` | Reverse drop (pre-prod) |
| **`V011`** | Audit, Triggers & Integrity Guards (`audit.variance_alerts`, `audit.audit_logs`, append-only triggers, `inventory_balances` auto-update trigger, dispatch over-qty guard, `bom_versions` immutability trigger, performance indexes) | `V002`–`V010` | Drop triggers/views safely; **never** disable immutability in prod |
| **`V012`** | Reporting Views (`reporting.*`), DB Roles (`ota_app_rw`, `ota_auditor_ro`), Privileges & RLS Policies (`security-design.md`) | `V011` | `CREATE OR REPLACE VIEW` / revoke & re-grant |
| **`SEED`** | Idempotent Benchmark Seed Loader (`seed-data-design.md` Step 0) | `V012` | Truncate/reset **only** in isolated test/demo environments |

---

## 2. Production Safety & Rollback Rules

1. **Transactional DDL:** Every migration script runs inside a single PostgreSQL `BEGIN ... COMMIT` transaction so a failed constraint or index aborts cleanly without leaving half-applied tables.
2. **No Destructive Rollbacks on Live Data:** Once financial, invoice, or ledger rows exist in production, downgrading via `DROP TABLE` / `DROP COLUMN` is strictly forbidden. Schema evolution uses **Expand-and-Contract**:
   - *Step A (Expand):* Add nullable columns/new tables (`V013`) while keeping old columns populated.
   - *Step B (Backfill & Dual-Write):* Populate new structures inside batched transactions and verify zero drift.
   - *Step C (Contract):* Switch application reads and retire legacy columns only after verified release stability.
3. **Zero-Downtime Index Creation:** Any post-launch index on large ledger/invoice tables uses `CREATE INDEX CONCURRENTLY` outside the migration transaction block so active salesman orders and admin invoicing are never blocked.
4. **Pre-Release Verification Gate:** Every migration run executes automated checks verifying: (a) `reporting.v_stock_reconciliation` returns `0` drift, (b) `num_nonnulls` & GST `CHECK` constraints validate cleanly, and (c) benchmark seed + end-to-end test passes 100%.
