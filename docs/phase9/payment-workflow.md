# Phase 9 — Customer Payment Lifecycle & Controls

## Payment Recording (`POST /api/v1/finance/payments`)

Authorised (`FACTORY_ADMIN`) users record incoming customer remittances (`RecordPaymentRequest`):
- **Supported Modes:** `CASH`, `UPI`, `BANK_TRANSFER`, `NEFT`, `RTGS`, `IMPS`, `CHEQUE`, `CARD`, `OTHER`.
- **Mandatory Controls:**
  - Positive integer paise (`amount_paisa > 0`).
  - Unique `client_payment_id` (UUID) guaranteeing safe idempotent replay on network retries without duplicating financial rows.
  - Partial unique database index `uq_payments_customer_dup_ref` preventing accidental duplicate active receipts matching `(customer_id, payment_date, amount_paisa, reference_no)` when `reference_no` is non-null and `status <> 'REVERSED'`.
- **FY Numbering:** Uses `billing.fiscal_sequences` (`doc_type = 'PAYMENT'`) with April 1 Indian FY rollover (`PMT/2026-27/0001`).

## Payment Status State Machine

Allowed database check constraint values (`chk_payments_pmt_status_enum`):
- `RECORDED`: Stored with zero allocations and zero refunds (treated as `is_advance = true` until allocated).
- `PARTIALLY_ALLOCATED`: Part of `amount_paisa` is allocated to active invoice lines; remaining `unallocated_paisa > 0`.
- `ALLOCATED`: `allocated_paisa == amount_paisa` (`unallocated_paisa == 0`).
- `PARTIALLY_REFUNDED`: Unallocated balance partially returned (`refunded_paisa > 0`, remaining unallocated or allocated balance still positive).
- `REFUNDED`: Entire remaining cash returned (`refunded_paisa == amount_paisa`, `unallocated_paisa == 0`).
- `REVERSED`: Full payment cancellation due to cheque bounce, failed settlement, or entry error; all active allocations are atomically marked `REVERSED`, linked invoices recalculate `paid_paisa` & `payment_status`, and `unallocated_paisa` becomes `0`.

## Payment Receipt PDF (`GET /api/v1/finance/payments/{id}/receipt-pdf`)

Generates a pure-Python deterministic `%PDF-1.4` customer payment receipt displaying:
- Company legal details (`Kaveri Traditional Snacks Pvt. Ltd.`, GSTIN, address)
- Receipt Number (`PMT/...`), Receipt Date, Payment Mode, Reference Number
- Customer Name, Customer Code, GSTIN
- Amount Received (formatted in INR and Indian words), Allocated Amount, Advance/Unallocated Balance, and Table of Settled Invoices.

## Payment Refunds (`POST /api/v1/finance/payments/{id}/refund`)

- Only the **unallocated advance portion** (`amount_paisa - allocated_paisa - refunded_paisa`) may be refunded (`409` if refund exceeds unallocated balance).
- Emits an immutable row in `finance.payment_refunds` numbered `RFD/YYYY-YY/NNNN` (`billing.fiscal_sequences`, `doc_type = 'REFUND'`).

## Payment Reversal (`POST /api/v1/finance/payments/{id}/reverse`)

- Requires non-empty audit `reason` (`min_length=5`).
- Blocked (`409`) if refunds already exist against the payment or if already `REVERSED`.
- Locks payment row, linked allocations, customer invoices, and `customer_receivables` in ascending ID order (`FOR UPDATE`), marks every `ACTIVE` allocation as `REVERSED`, recalculates `billing.invoices.paid_paisa` & `payment_status`, and records an `audit.audit_logs` entry.
- Silent `DELETE` on `finance.payments`, `finance.payment_allocations`, or `finance.payment_refunds` is strictly blocked at the PostgreSQL trigger layer (`42501`).
