# Controlled Reconciliation & Discrepancy Resolution Workflow

## 1. Run Lifecycle State Machine (`audit.reconciliation_runs`)

- `NOT_STARTED` / `IN_PROGRESS`: Initial state allocated under fiscal sequence `REC/YYYY-YY/NNNN`.
- `RECONCILED`: Automated scan detected zero discrepancies (`discrepancy_count == 0`).
- `DISCREPANCY_FOUND`: Scan detected one or more discrepancies requiring review.
- `UNDER_REVIEW`: Investigation or proposed corrective action logged on any discrepancy.
- `RESOLVED`: All discrepancies in the run are `RESOLVED` or `DISMISSED` (manually or via `rerun` auto-verification).
- `CLOSED`: Formally signed off by `FACTORY_ADMIN` or `OWNER` with mandatory `closure_notes`. Database trigger `trg_reconciliation_run_immutability` forbids any subsequent modification or deletion once `CLOSED`.

### Duplicate Run Prevention
Partial unique index `uq_recon_active_fingerprint` enforces that only one active (`NOT_STARTED`, `IN_PROGRESS`, `DISCREPANCY_FOUND`, `UNDER_REVIEW`) run may exist for the exact `(domain, period_start, period_end, scope_filter)` SHA-256 fingerprint, preventing duplicate conflicting investigation threads (`409 DUPLICATE_RECONCILIATION_RUN`).

---

## 2. Discrepancy Resolution State Machine (`audit.reconciliation_discrepancies`)

```text
OPEN
  ├──[POST /investigate]──────────▶ UNDER_REVIEW
  ├──[POST /propose]──────────────▶ ACTION_PROPOSED
  │                                   └──[POST /approve (Admin/Owner)]──▶ APPROVED
  │                                                                         └──[POST /resolve (Admin only)]──▶ RESOLVED
  └──[POST /resolve dismiss=true (Admin only)]─────────────────────────────────────────────────────────────────▶ DISMISSED
```

### Supported Corrective Action Categories
1. `STOCK_ADJUSTMENT`: Requires `APPROVED` status. When executed by `FACTORY_ADMIN` via `POST /resolve`, invokes `inventory_service.create_stock_adjustment(post_immediately=True, adjustment_type=...)` inside PostgreSQL, posting a genuine `InventoryMovement` ledger entry and storing `resolution_ref_table = 'inventory.stock_adjustments'` + `resolution_ref_id`. Never silently edits `inventory_balances` in place.
2. `ISSUE_INVOICE`, `AR_RECALC_NOTE`, `MANUAL_JOURNAL_NOTE`, `DISPATCH_FOLLOWUP`, `NO_OP_EXPLAINED`: Tracks formal administrative resolution / explanation alongside `resolution_notes`, and can be verified on subsequent `POST /runs/{id}/rerun`.

---

## 3. Re-Run Verification (`POST /runs/{id}/rerun`)

When operational fixes are performed directly through standard modules (such as raising a missing GST invoice on an approved order, or posting a Goods Receipt):
- Re-running scans the same domain, period, and scope as of current UTC timestamp.
- Any open/under-review discrepancy whose `(discrepancy_code, entity_table, entity_id)` key no longer triggers in the fresh scan automatically transitions to `RESOLVED` with append-only `AUTO_VERIFIED_RESOLVED` event history.
- Any newly discovered discrepancy is inserted as `OPEN`.
- Only when zero open discrepancies remain can `close_reconciliation_run` seal the run.
