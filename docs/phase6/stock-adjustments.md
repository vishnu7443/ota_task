# Controlled Stock Adjustments (`docs/phase6/stock-adjustments.md`)

## Purpose & Voucher Table (`inventory.stock_adjustments`)
Manual stock adjustments record shrinkage, spoilage, breakage, supplier returns, and audited physical count variances without breaking ledger immutability. Direct mutations to `inventory.inventory_balances` are never exposed via API.

## Adjustment Categories
- **Negative-Only Stock Reductions (`delta_qty_base < 0`):**
  - `DAMAGED` -> posts ledger `movement_type = DAMAGE_WASTAGE` (`source_doc_type = STOCK_ADJUSTMENT`)
  - `EXPIRED` -> posts ledger `movement_type = DAMAGE_WASTAGE` (`source_doc_type = STOCK_ADJUSTMENT`)
  - `MISSING` -> posts ledger `movement_type = ADJUSTMENT` (`source_doc_type = STOCK_ADJUSTMENT`)
  - `SUPPLIER_RETURN` -> posts ledger `movement_type = SUPPLIER_RETURN` (`source_doc_type = SUPPLIER_RETURN`)
- **Bidirectional Count Adjustments (`delta_qty_base <> 0`):**
  - `COUNT_CORRECTION`, `OTHER` -> posts ledger `movement_type = ADJUSTMENT` (`source_doc_type = STOCK_ADJUSTMENT`)

## Approval Separation & Reservation Safety
- **Role Governance:**
  - `PRODUCTION_SUPERVISOR`: may create requests in `PENDING_APPROVAL` (`403 Forbidden` if attempting `post_immediately: true`, or calling `/approve` or `/reject`).
  - `FACTORY_ADMIN`: may approve & post pending requests, reject pending requests (mandatory reason min 5 chars), or create & immediately post urgent adjustments.
  - `ACCOUNTANT_AUDITOR`, `OWNER`, `SALESMAN`: strictly read-only (`AUDITOR`/`OWNER`) or blocked (`SALESMAN`).
- **Safety Interlocks:**
  - Reductions cannot drop `on_hand_qty_base` below `0` (`409 INSUFFICIENT_STOCK`).
  - Finished-good reductions cannot push `on_hand_qty_base` below active Sales Order `reserved_qty_base` (`409 INSUFFICIENT_AVAILABLE_STOCK`).
  - Open FIFO `inventory.cost_lots` are created cleanly for positive adjustments or depleted in FIFO order for negative adjustments.
  - Every request, approval, posting, and rejection records a permanent row in `audit.audit_logs`.
