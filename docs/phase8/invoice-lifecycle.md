# Phase 8 — Invoice Lifecycle & Immutability

## Document State Machine

Implemented via PostgreSQL constraints (`chk_invoices_inv_doc_status_enum`), immutability triggers (`trg_invoice_immutability`, `trg_invoice_items_immutability`, `trg_invoice_tax_components_immutability`), and [`service.py`](file:///d:/mac/ota/backend/app/modules/billing/service.py):

```text
  [Order APPROVED]
         │
         ▼
      (DRAFT)  ──[POST /verify]──► Verification metadata recorded (optional explicit review step)
         │
         │  [POST /issue]  (Allocates INV/YYYY-YY/NNNN, locks snapshot, sets Order -> INVOICED)
         ▼
     (ISSUED)  ──[POST /credit-notes (full cancellation)]──► (CANCELLED_BY_CN)
         │                                                          │
         │                                              [Un-dispatched order -> Order CANCELLED + FG reservation released]
         ▼
  [Partial/Full Credit Notes update credited_paisa; outstanding_paisa updates dynamically]
```

---

## Lifecycle Rules & Database Protections

1. **Draft Stage (`DRAFT`):**
   - Identified by non-statutory `draft_ref` (`DRF-INV-...`); `invoice_number IS NULL` (`inv_issued_number_required`).
   - Cannot be dispatched (`409 INVOICE_NOT_ISSUED`).
   - Blocked from Salesman PDF downloads (`403 AuthorizationError`).
2. **Verification & Issuance (`verify_invoice` / `issue_invoice`):**
   - `verify_invoice` stamps `verified_by`, `verified_at`, and `verification_remarks`, logging `INVOICE_VERIFIED` audit trail with optimistic `version` check (`409 VERSION_CONFLICT`).
   - `issue_invoice` (`_perform_issue_invoice`) checks `doc_status == 'DRAFT'` (`409 DUPLICATE_INVOICE_ISSUE`), allocates a gap-free `INV/YYYY-YY/NNNN` number via `allocate_fiscal_sequence`, sets `doc_status = 'ISSUED'`, stamps `issued_by`/`issued_at`, transitions linked `SalesOrder` from `APPROVED -> INVOICED` with `SalesOrderStatusHistory`, and logs `INVOICE_ISSUED`.
3. **Database-Level Immutability Triggers (`0005`):**
   - `trg_invoice_immutability` (`BEFORE UPDATE OR DELETE ON billing.invoices`): Forbids `DELETE` on any non-draft invoice and blocks changing financial totals (`taxable_total_paisa`, `cgst_total_paisa`, `sgst_total_paisa`, `igst_total_paisa`, `round_off_paisa`), parties/GSTIN/POS, `invoice_number`, `financial_year`, `invoice_date`, `issued_by`, `issued_at`, or reverting to `DRAFT` (SQLSTATE `42501`). Allows only operational status/settlement fields (`doc_status -> CANCELLED_BY_CN`, `payment_status`, `dispatch_status`, `paid_paisa`, `credited_paisa`, `version`).
   - `trg_invoice_items_immutability` & `trg_invoice_tax_components_immutability`: Block any `INSERT`, `UPDATE`, or `DELETE` on child lines/tax rows once parent `doc_status <> 'DRAFT'`.
4. **Invoiced Order Lock:**
   - Once an order enters `INVOICED`, direct cancellation via `/orders/{id}/cancel` is blocked (`orders/service.py`); an authorized Credit Note (`CANCELLED_BY_CN`) must be issued instead.
