# Phase 8 — GST Billing, Credit Notes, Dispatch & Reports API Documentation

All endpoints are mounted under `/api/v1/billing` in [`router.py`](file:///d:/mac/ota/backend/app/modules/billing/router.py) with Pydantic contracts defined in [`schemas.py`](file:///d:/mac/ota/backend/app/modules/billing/schemas.py).

---

## Role Access Matrix

- `_BillingOperator`: `FACTORY_ADMIN` only (all POST mutations).
- `_BillingViewer`: `FACTORY_ADMIN`, `ACCOUNTANT_AUDITOR`, `OWNER` (dashboards, lists, credit notes, reports).
- `_InvoiceReader`: `SALESMAN` (strictly scoped to own Sales Orders; blocked `403` on DRAFT PDF downloads), `FACTORY_ADMIN`, `ACCOUNTANT_AUDITOR`, `OWNER`.
- `PRODUCTION_SUPERVISOR`: Blocked `403` across all billing endpoints.

---

## Endpoints Summary

| Method & Path | Access | Status | Description |
| --- | --- | --- | --- |
| `GET /api/v1/billing/dashboard` | Viewer | `200` | KPI totals (`total_taxable_paisa`, `cgst`, `sgst`, `igst`, `grand_total`, `credited`, `outstanding`), ready approved orders with backend GST estimates, and filtered invoices (`doc_status`, `dispatch_status`, `search`) |
| `GET /api/v1/billing/invoices` | Viewer | `200` | List invoices with status/search filters |
| `POST /api/v1/billing/invoices` | Operator | `201` | Generate `DRAFT` or immediately `ISSUED` invoice from an `APPROVED` sales order (`CreateInvoiceRequest`) |
| `GET /api/v1/billing/invoices/{invoice_id}` | Reader | `200` | Full `InvoiceDetailOut` including seller/buyer snapshots, items, `tax_components`, `credit_notes`, `dispatches`, and `audit_trail` (omitted for `SALESMAN`) |
| `POST /api/v1/billing/invoices/{invoice_id}/verify` | Operator | `200` | Record explicit verification review on `DRAFT` invoice (`VerifyInvoiceRequest`) |
| `POST /api/v1/billing/invoices/{invoice_id}/issue` | Operator | `200` | Issue `DRAFT -> ISSUED`, allocate `INV/YYYY-YY/NNNN`, transition Order `APPROVED -> INVOICED` (`IssueInvoiceRequest`) |
| `GET /api/v1/billing/invoices/{invoice_id}/pdf` | Reader | `200` | Stream deterministic `application/pdf` Tax Invoice binary rendered strictly from persisted DB state |
| `GET /api/v1/billing/credit-notes` | Viewer | `200` | List all GST Credit Notes (`CreditNoteOut[]`) |
| `POST /api/v1/billing/credit-notes` | Operator | `201` | Create (`DRAFT` or immediate `ISSUED`) `INVOICE_CANCELLATION`, `SALES_RETURN`, or `VALUE_ADJUSTMENT` credit note |
| `POST /api/v1/billing/credit-notes/{cn_id}/issue` | Operator | `200` | Issue `DRAFT` Credit Note, allocate `CN/YYYY-YY/NNNN`, reverse balance & process optional FG restock |
| `GET /api/v1/billing/dispatches/dashboard` | Viewer | `200` | Ready-for-dispatch issued invoices (with `fg_on_hand_sufficient` indicator) and dispatch status counts/list (`status` filter) |
| `POST /api/v1/billing/dispatches` | Operator | `201` | Create Dispatch note (`DSP/YYYY-YY/NNNN`) bound to an `ISSUED` invoice (`post_immediately` optional) |
| `GET /api/v1/billing/dispatches/{dispatch_id}` | Reader | `200` | Full `DispatchOut` with line discrepancies & append-only `status_history` |
| `POST /api/v1/billing/dispatches/{dispatch_id}/ready` | Operator | `200` | Mark `CREATED -> READY_FOR_DISPATCH`, record packing verification & vehicle/LR metadata |
| `POST /api/v1/billing/dispatches/{dispatch_id}/post` | Operator | `200` | Atomically deplete FEFO FG `CostLot`s, emit `DISPATCH_OUT`, fulfill reservation, sync Invoice & Order statuses |
| `POST /api/v1/billing/dispatches/{dispatch_id}/delivery` | Operator | `200` | Transition to `IN_TRANSIT`, `DELIVERED`, or `DELIVERY_EXCEPTION` (with required reason & per-item `received_qty_pkts`) |
| `GET /api/v1/billing/reports` | Viewer | `200` | Operational `BillingReportsBundleOut`: `sales_register`, `gst_summary` (`hsn_rows` + disclaimer), `credit_notes`, `dispatch_register`, `customer_sales`, `product_sales`, `outstanding_invoices` |

---

## Domain Conflict & Validation Error Codes

| HTTP Status | `error.code` | Trigger Condition |
| --- | --- | --- |
| `403` | `AUTHORIZATION_ERROR` | Non-admin write, `PRODUCTION_SUPERVISOR` access, cross-salesman inspection, or salesman `DRAFT` PDF request |
| `409` | `INVALID_STATE_TRANSITION` | Billing unapproved order, verifying non-draft invoice, crediting draft invoice, or invalid delivery state jump |
| `409` | `DUPLICATE_INVOICE` | Active non-cancelled invoice already exists for `sales_order_id` |
| `409` | `DUPLICATE_INVOICE_ISSUE` | Re-issuing an already issued/cancelled invoice |
| `409` | `INVOICE_NOT_ISSUED` | Dispatch creation or posting attempted against `DRAFT` or `CANCELLED_BY_CN` invoice |
| `409` | `DISPATCH_EXCEEDS_ORDER` | Dispatch quantity exceeds remaining undispatched quantity on invoice line |
| `409` | `DUPLICATE_DISPATCH_POST` | Re-posting an already dispatched record |
| `409` | `INSUFFICIENT_STOCK` | Physical FG `on_hand_qty_base` below dispatched quantity at dispatch posting |
| `409` | `DUPLICATE_CREDIT_NOTE` / `EXCESS_CREDIT_NOTE` / `EXCESS_CREDIT_QUANTITY` / `RETURN_EXCEEDS_DISPATCHED` | Re-issuing CN, exceeding invoice remaining balance, exceeding invoiced qty, or returning more goods than dispatched |
| `409` | `VERSION_CONFLICT` | Stale `expected_version` optimistic lock mismatch |
| `422` | `VALIDATION_ERROR` | GSTIN state prefix mismatch, missing `exception_reason` on delivery exception, or negative/invalid quantities |
