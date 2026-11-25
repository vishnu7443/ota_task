# Phase 9 — Invoice Allocation, Partial Settlement & Credit Note Unwind

## Allocation Rules (`finance.payment_allocations`)

1. **Same Customer & Issued Status Only:** Allocations may target only `ISSUED` invoices belonging to the same `customer_id` as the payment (drafts, cancelled invoices, and other customers' invoices are rejected).
2. **Double-Side Balance Bounds (App + DB Trigger):**
   - Sum of `ACTIVE` allocations for a payment can never exceed `payment.amount_paisa - payment.refunded_paisa`.
   - Sum of `ACTIVE` allocations + `invoice.credited_paisa` on an invoice can never exceed `invoice.grand_total_paisa` (`chk_invoices_inv_paid_credited_cap` + `trg_payment_allocation_integrity`).
3. **Derived Status Transition on `billing.invoices`:**
   - Clients cannot directly submit `payment_status`. After every allocation, allocation reversal, payment reversal, or credit note posting, the backend deterministically recomputes:
     - `effective_due = grand_total_paisa - credited_paisa`
     - `paid_paisa = SUM(ACTIVE payment_allocations.allocated_paisa)`
     - `outstanding_paisa = effective_due - paid_paisa`
     - `payment_status = "PAID"` if `outstanding_paisa == 0`, `"PARTIALLY_PAID"` if `paid_paisa > 0`, else `"UNPAID"`.
4. **Concurrency Safety (`FOR UPDATE` Lock Ordering):**
   - Concurrent `POST /finance/payments` and `POST /finance/payments/{id}/allocate` acquire row locks on the payment and target invoices (sorted deterministically by `invoice_id ASC` to prevent deadlocks) prior to inserting `payment_allocations`. Simultaneous full-settlement requests against the same invoice cleanly yield `[201, 409]` with zero negative balance.

## Supported Real-World Patterns

- **Partial Settlement (`Retailer A` benchmark):** Invoice `₹7,875.00` (`787500` paise) receives `₹4,000.00` (`400000` paise) -> Invoice moves `UNPAID -> PARTIALLY_PAID` with `outstanding_paisa = 387500` (`₹3,875.00`).
- **Multiple Payments on One Invoice:** Subsequent payment of `₹3,875.00` allocates to the same invoice -> `paid_paisa = 787500`, `outstanding_paisa = 0`, status `PAID`.
- **Single Payment Split Across Multiple Invoices:** One `₹6,000.00` remittance settles `INV-1` (`₹5,250.00` -> `PAID`) and partially settles `INV-2` (`₹750.00` allocated out of `₹3,150.00` -> `PARTIALLY_PAID`, remaining `₹2,400.00`).
- **Advance & Late Allocation:** Unallocated advance (`allocations = []`) holds `unallocated_paisa == amount_paisa`; once a future invoice is issued, `POST /finance/payments/{id}/allocate` applies funds directly against that invoice.

## Credit Note Automatic Unwind (`billing/service.py`)

When a Credit Note (`SALES_RETURN` or `INVOICE_CANCELLATION`) is issued on a partially or fully paid invoice:
- If `new_credited_paisa + current_paid_paisa > grand_total_paisa`, the excess paid amount (`excess = current_paid_paisa - (grand_total_paisa - new_credited_paisa)`) is **never left as negative AR**:
  - The backend automatically releases/reduces active allocations cleanly by reversing excess allocations (re-allocating residual balance if partially affected so `SUM(ACTIVE)` remains exact) back onto the source `Payment`'s `unallocated_paisa` (customer advance balance).
  - Both `billing.invoices` (`credited_paisa`, `paid_paisa`, `payment_status`) and `finance.customer_receivables` remain synchronized inside the same ACID database transaction.
