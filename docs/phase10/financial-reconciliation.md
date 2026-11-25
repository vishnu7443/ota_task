# Financial, Sales, GST & Dispatch Reconciliation

Phase 10 verifies all commercial and accounting links end-to-end across `sales`, `billing`, `finance`, and `inventory` using pure integer-paisa and integer-packet comparisons (`reconciliation/engine.py`).

---

## 1. Sales-to-Invoice Reconciliation (`evaluate_sales_reconciliation`)
Inspects non-DRAFT `sales.sales_orders` vs `billing.invoices`:
- `DUPLICATE_ACTIVE_INVOICE` (`CRITICAL`): Order linked to `> 1` active invoice (`doc_status != 'CANCELLED_BY_CN'`).
- `APPROVED_ORDER_UNINVOICED` (`MEDIUM`): Approved order awaiting GST invoice generation.
- `ORDER_STATUS_INV_MISMATCH` (`MEDIUM`): Order marked `INVOICED` / `PARTIALLY_DISPATCHED` / `DISPATCHED` without an active `ISSUED` invoice.
- `CANCELLED_ORDER_ACTIVE_INVOICE` (`CRITICAL`): Cancelled/rejected order still has an uncancelled `ISSUED` invoice.
- `ORDER_INV_QTY_MISMATCH` (`CRITICAL`): Approved packet sum differs from issued invoice packet sum.

---

## 2. Invoice, GST & Credit Note Reconciliation (`evaluate_invoice_reconciliation`)
Inspects every non-DRAFT `billing.invoices` row:
- `INV_LINE_SUM_MISMATCH` (`CRITICAL`, Domain `INVOICE`): Recomputes $\sum \text{taxable\_paisa}$, $\sum (\text{cgst} + \text{sgst} + \text{igst})$, and $\text{grand\_total\_paisa} = \text{taxable} + \text{tax} + \text{round\_off\_paisa}$ against header totals.
- `INV_GST_SPLIT_MISMATCH` (`CRITICAL`, Domain `GST`): Enforces statutory GST split integrity — `INTRA_STATE` must satisfy `igst == 0` and `cgst == sgst`; `INTER_STATE` must satisfy `cgst == 0` and `sgst == 0`.
- `INV_CN_CREDITED_MISMATCH` (`CRITICAL`, Domain `INVOICE`): Verifies `invoice.credited_paisa` equals $\sum \text{total\_reversed\_paisa}$ across `ISSUED` `CreditNote` rows.
- `CANCELLED_INV_CREDITED_INCOMPLETE` (`CRITICAL`, Domain `INVOICE`): `CANCELLED_BY_CN` invoices must be 100% credited (`credited_paisa == grand_total_paisa`).

---

## 3. Payment, Allocation, Refund & AR Parity (`evaluate_payment_reconciliation`)
Cross-checks `finance.payments`, `finance.payment_allocations`, `finance.payment_refunds`, `billing.invoices`, and `finance.customer_receivables`:
- `REVERSED_PMT_HAS_ACTIVE_ALLOC` (`CRITICAL`): Reversed payment cannot retain `ACTIVE` allocations.
- `PMT_ALLOC_SUM_MISMATCH` (`CRITICAL`): Payment header `allocated_paisa` and `refunded_paisa` must match live sums of `ACTIVE` allocations and `POSTED` refunds.
- `PMT_OVER_ALLOCATED` (`CRITICAL`): Active allocations + posted refunds cannot exceed `payment.amount_paisa`.
- `MISSING_CUSTOMER_RECEIVABLE` (`HIGH`): Every issued invoice must maintain a corresponding `finance.customer_receivables` row.
- `INV_AR_OUTSTANDING_MISMATCH` (`CRITICAL`): `CustomerReceivable` (`original`, `credited`, `paid`, `outstanding`) must match `Invoice` identically to the exact paisa.

---

## 4. Invoice-to-Dispatch & Inventory Ledger Parity (`evaluate_dispatch_reconciliation`)
Verifies issued `billing.invoices` against posted `billing.dispatches` (`DISPATCHED`, `IN_TRANSIT`, `DELIVERED`, `DELIVERY_EXCEPTION`) and `DISPATCH_OUT` ledger rows:
- `DISPATCH_EXCEEDS_INVOICE` (`HIGH`): Dispatched packet total exceeds invoiced packets.
- `DISPATCH_VS_LEDGER_MISMATCH` (`HIGH`): Sum of posted `DispatchItem.dispatched_qty_pkts` differs from deduplicated `DISPATCH_OUT` ledger quantities.
- `INV_DISPATCH_FLAG_MISMATCH` (`HIGH`): Invoice `dispatch_status` (`PENDING` / `PARTIAL` / `DISPATCHED`) inconsistent with dispatched packet totals.
