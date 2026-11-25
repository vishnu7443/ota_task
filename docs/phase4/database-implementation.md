# Database Implementation (Phase 3 -> Phase 4 Alembic & SQLAlchemy)

## 1. Alignment with Phase 3 Schema

Migration `0001_phase4_foundation` ([0001_phase4_foundation_and_orders.py](file:///d:/mac/ota/backend/alembic/versions/0001_phase4_foundation_and_orders.py)) creates the approved PostgreSQL schemas and tables needed for Phase 4 while honoring every Phase 3 integrity constraint:

| Schema | Tables Implemented in `0001` | Key PostgreSQL Constraints & Features |
| --- | --- | --- |
| `iam` | `company_profiles`, `roles`, `users` | Singleton `is_singleton` unique check, GSTIN regex check, `ON DELETE RESTRICT` role FK |
| `sales` | `salesman_profiles`, `customers`, `customer_addresses`, `products`, `pack_sizes`, `price_lists`, `price_list_items`, `sales_orders`, `sales_order_items`, `sales_order_status_history`, `sales_order_approvals` | GSTIN state-prefix check, `UNIQUE (salesman_id, client_order_id)` idempotency, `GENERATED ALWAYS AS` `line_taxable_paisa`, partial unique indexes (`is_default`) |
| `inventory` | `opening_balances`, `inventory_balances`, `inventory_movements` | `NUMERIC(18,3)` base quantities, `NUMERIC(18,6)` unit cost per base unit, `GENERATED ALWAYS AS (on_hand - reserved)` `available_qty_base`, `CHECK (reserved <= on_hand)` |
| `audit` | `audit_logs` | `JSONB` `before_state` / `after_state`, composite entity & actor indexes |

## 2. Database Triggers Implemented in Migration `0001`

1. **`audit.fn_prevent_mutation()` (`BEFORE UPDATE OR DELETE`):** Attached to `inventory.inventory_movements`, `audit.audit_logs`, and `sales.sales_order_status_history`. Unconditionally raises `SQLSTATE '42501'` if any SQL update or delete is attempted.
2. **`inventory.fn_sync_balance_from_movement()` (`AFTER INSERT`):** Attached to `inventory.inventory_movements`. Inserts or increments `inventory.inventory_balances.on_hand_qty_base` atomically whenever a movement row is appended, ensuring stock balances stay strictly ledger-derived.

## 3. Incremental Phase 5+ Migration Path

In Phase 5/6, new Alembic revisions (`0002+`) will cleanly add `purchasing.*`, `production.*`, `costing.*`, `billing.*`, `finance.*`, `audit.variance_alerts`, and expand `inventory.inventory_movements` nullable source FKs + the full `num_nonnulls(...) = 1` check constraint without breaking or dropping any Phase 4 table or order history.
