# Known Limitations & Deferred Phase Scope

Intentionally deferred outside Phase 4 per strict incremental vertical-slice boundaries:

1. **Order Approval, Editing, Rejection & Correction Loop:** Admin order review screen currently inspects persisted orders and stock coverage without mutating order status (`APPROVED`, `REJECTED`, `CORRECTION_REQUESTED`) or reserving `inventory_balances.reserved_qty_base`.
2. **GST Invoicing, Credit Notes & Dispatch:** `billing.*` tables (`invoices`, `fiscal_sequences`, `credit_notes`, `dispatches`) and PDF generation are deferred to the Sales Loop completion phase.
3. **Payments & Receivables:** `finance.*` tables (`payments`, `payment_allocations`, `customer_receivables`) and AR ageing reports are deferred.
4. **Purchasing, BOMs, Production Runs, Variances & Costing:** `purchasing.*`, `production.*`, and `costing.*` tables (including Flour/Oil/Spice/Pouch/Carton opening balances, BOM `v1`, and `PRD-001` variance/costing) are deferred to the Production Loop phase. *(Only `Murukku 200 g` opening FG stock of `50` packets is seeded in Phase 4 to support live order stock checks.)*
5. **Full Offline Catalog Sync:** Weak-network draft persistence and `client_order_id` idempotency retry work today; full offline IndexedDB catalog caching + background sync queue remains a Stretch Goal (`FR-G-01`).
6. **PostgreSQL `ota_app_rw` / `ota_auditor_ro` DB Role Hardening & RLS DDL:** Session context (`app.current_user_id`, `app.current_role`) is already set per request; final DB role splits and RLS policies (`security-design.md`) will apply alongside `reporting` views in the next phase migration.
