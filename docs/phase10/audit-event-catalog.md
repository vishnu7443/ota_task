# Centralized Audit Event Catalog

All event action identifiers currently emitted by backend services into `audit.audit_logs`, grouped by functional domain:

## 1. Security & IAM Governance (`iam`)
- `LOGIN_SUCCESS` — Authenticated session issued (records username & role_code; never token/password).
- `LOGIN_FAILED` — Failed credential check or inactive account login rejection.
- `ACCESS_DENIED` — Backend RBAC dependency (`require_roles`) rejected unauthorized role call (`403 Forbidden`).
- `USER_CREATED` — Admin/Owner provisioned a new user (and `SalesmanProfile` when `SALESMAN`).
- `USER_ROLE_CHANGED` — Admin/Owner reassigned a user's RBAC role with mandatory reason.
- `USER_STATUS_CHANGED` — Admin/Owner activated or deactivated a user account with mandatory reason.

## 2. Sales Orders & Reservations (`sales` / `inventory`)
- `ORDER_SUBMITTED` — Salesman created and submitted a new sales order.
- `ORDER_RESUBMITTED` — Salesman edited and resubmitted a `CORRECTION_REQUESTED` order.
- `ORDER_MARKED_UNDER_REVIEW` — Admin placed submitted order under review.
- `ORDER_QTY_MODIFIED` — Admin edited order line approved packet quantities (`before_state` / `after_state`).
- `ORDER_PRICE_MODIFIED` — Admin edited order line unit selling price in paise.
- `ORDER_REMARK_UPDATED` — Admin updated review remarks.
- `ORDER_CORRECTION_REQ` — Admin returned order to salesman for correction.
- `ORDER_APPROVED` — Admin approved order after atomic stock availability check.
- `ORDER_REJECTED` — Admin rejected pending order with reason.
- `ORDER_CANCELLED` — Salesman or Admin cancelled order prior to invoicing.
- `STOCK_RESERVED` — Atomic reservation allocated against `inventory.inventory_balances` upon approval.
- `STOCK_RESERVATION_RELEASED` — Reservation released on order cancellation or invoice cancellation credit note.

## 3. Purchasing & Inventory Ledger (`purchasing` / `inventory`)
- `SUPPLIER_CREATED`, `SUPPLIER_UPDATED` — Supplier master additions/edits.
- `PO_CREATED`, `PO_SUBMITTED`, `PO_APPROVED`, `PO_REJECTED`, `PO_CANCELLED` — Purchase Order lifecycle.
- `RECEIPT_CREATED`, `RECEIPT_SUBMITTED`, `RECEIPT_VERIFIED`, `RECEIPT_POSTED` — Goods Receipt QC verification & `PURCHASE_IN` + FIFO `CostLot` creation.
- `STOCK_ADJUSTMENT_CREATED`, `STOCK_ADJUSTMENT_POSTED`, `STOCK_ADJUSTMENT_REJECTED` — Logged manual stock adjustment workflow.

## 4. BOM, Production & Costing (`production` / `costing` / `audit`)
- `MATERIAL_CREATED`, `PACK_SIZE_CREATED` — Master catalog extensions.
- `BOM_VERSION_CREATED`, `BOM_DRAFT_UPDATED`, `BOM_DRAFT_DELETED`, `BOM_VERSION_ACTIVATED` — Immutable BOM versioning lifecycle.
- `PRODUCTION_RUN_CREATED`, `PRODUCTION_RUN_PLANNED`, `PRODUCTION_MATERIALS_ISSUED`, `PRODUCTION_RUN_COMPLETED`, `PRODUCTION_RUN_POSTED`, `PRODUCTION_RUN_CANCELLED` — Full floor batch execution lifecycle.
- `VARIANCE_ALERT_ACKNOWLEDGED` — Supervisor acknowledgement of flagged BOM/yield variance alert.
- `PRODUCTION_COST_SNAPSHOT_CREATED` — Automated `PRELIMINARY` or `FINALIZED` batch costing snapshot.
- `PRODUCTION_OVERHEAD_ADDED`, `PRODUCTION_OVERHEAD_VOIDED`, `MONTHLY_OVERHEAD_POOL_ADDED` — Factory overhead accounting & voids.

## 5. GST Billing, Credit Notes, Dispatch & Finance (`billing` / `finance`)
- `INVOICE_DRAFT_CREATED`, `INVOICE_VERIFIED`, `INVOICE_ISSUED` — Statutory GST invoice lifecycle.
- `CREDIT_NOTE_ISSUED` — Invoice cancellation (`CANCELLED_BY_CN`) or sales return / adjustment CN issuance.
- `DISPATCH_CREATED`, `DISPATCH_READY`, `DISPATCH_POSTED`, `DELIVERY_UPDATED` — Physical FG FEFO depletion (`DISPATCH_OUT`) & delivery POD tracking.
- `PAYMENT_RECORDED`, `PAYMENT_ALLOCATED`, `ALLOCATION_REVERSED`, `PAYMENT_REVERSED`, `PAYMENT_REFUNDED` — Payment receipt, multi-invoice split, refund, and reversal trail.

## 6. Reconciliation & Discrepancy Resolution (`audit`)
- `RECON_RUN_STARTED` — Formal reconciliation scan executed (`REC/YYYY-YY/NNNN`).
- `RECON_DISCREPANCY_REVIEWED` — Discrepancy placed under investigation with assignee/notes.
- `RECON_CORRECTION_PROPOSED` — Corrective action category and proposal logged.
- `RECON_ACTION_APPROVED` — Admin/Owner approved proposed correction.
- `RECON_ACTION_APPLIED` — Admin executed corrective posting (`STOCK_ADJUSTMENT`) or documented dismissal.
- `RECON_RUN_RERUN` — Verification re-scan updated cleared discrepancies (`AUTO_VERIFIED_RESOLVED`).
- `RECON_RUN_CLOSED` — Run formally sealed (`CLOSED`) once zero open items remain.
