# Phase 9 — Payment Management, Accounts Receivable & Product Costing Overview

## Purpose

Phase 9 extends the NIT Tiruchirappalli CDI Winter Internship 2026 Order-to-Audit Management System (`Kaveri Traditional Snacks Pvt. Ltd.`) into complete financial settlement, receivables governance, batch-level manufacturing costing, and contribution/gross profitability reporting.

It integrates directly with the completed Phase 4–8 modules without duplicating existing billing, inventory, or costing ledgers:
- **GST Billing (`billing`):** Issued statutory invoices (`billing.invoices`), FY numbering (`billing.fiscal_sequences` extended with `PAYMENT` and `REFUND`), and Credit Notes (`billing.credit_notes`).
- **Inventory & FIFO/FEFO Cost Layers (`inventory`):** Raw material & packaging `CostLot` layers, `CostLotConsumption` records emitted during Phase 7 production execution, and FG dispatch FEFO layers consumed during Phase 8 dispatches.
- **Production Execution (`production`):** `post_production_run` emits automatic `PRELIMINARY` v1 cost snapshots cleanly within the transaction boundary.
- **Orders (`orders`):** Sales orders reflect live `invoice_paid_paisa`, `invoice_outstanding_paisa`, and `invoice_payment_status` read-only status derived from issued invoices and allocations.

---

## Key Capabilities Delivered

1. **Customer Payment Desk & Statutory Receipts (`finance.payments`):**
   - Multiple payment methods (`CASH`, `UPI`, `BANK_TRANSFER`, `NEFT`, `RTGS`, `IMPS`, `CHEQUE`, `CARD`, `OTHER`), `client_payment_id` UUID idempotency, active duplicate reference protection, advance deposit handling (`is_advance`), and pure-Python `%PDF-1.4` receipt export (`PMT/YYYY-YY/NNNN`).
   - Non-destructive `REVERSED` workflow & unallocated advance `REFUNDED` (`RFD/YYYY-YY/NNNN`) workflow with immutable audit history and PostgreSQL trigger protection against deletion or retroactive amount edits.
2. **Multi-Invoice & Split Allocations (`finance.payment_allocations`):**
   - One payment split across multiple customer invoices, multiple partial payments settling one invoice (`UNPAID -> PARTIALLY_PAID -> PAID`), late allocation from advance balances, individual allocation reversal, and automatic Credit Note over-payment unwinding back into Customer Advance.
3. **Accounts Receivable, Due-Date Ageing & Customer Ledger Statements (`finance.customer_receivables`):**
   - Automatic `CustomerReceivable` projection created on `ISSUE_INVOICE` and synchronized on every allocation, reversal, or Credit Note.
   - Invoice ageing strictly evaluated from **`due_date` vs reporting `as_of_date`** across `NOT_DUE`, `0_30` (1–30 days), `31_60`, `61_90`, and `90_PLUS` days.
   - Running-balance chronological Customer Statements & Salesman-scoped own customer AR view (`/finance/my-customers/receivables`).
4. **FIFO Production Batch Costing (`costing.production_overheads`, `costing.production_cost_summaries`):**
   - Automatic `v1 PRELIMINARY` batch costing upon production post using exact FIFO `CostLotConsumption` costs (`raw_material_cost_paisa`, `good_packaging_cost_paisa`, `damaged_packaging_cost_paisa`, `raw_wastage_cost_paisa`, `rejected_output_cost_impact_paisa`).
   - Direct shift overheads (`DIRECT_LABOUR`, `GAS_POWER`, `PACKAGING_LABOUR`, etc.) + monthly factory pool allocation distributed strictly by `good_packets` with largest-remainder integer-paisa distribution.
   - Immutable versioned snapshots (`v1 -> v2 -> ...`) preserving planned standard vs actual cost variances and unit selling margin.
5. **Profitability Analytics (`/finance/profitability`):**
   - Segregated metrics across Net Revenue (excluding GST & net of Credit Notes), GST Liability, Dispatched FEFO + Estimated Pending COGS, Gross Profit & Margin %, Cash Received, and Open Receivables — explicitly disclaiming that non-factory SG&A/opex expenses are excluded (not statutory Net Profit).

---

## Role-Based Access Boundaries Preserved

- **`SALESMAN`:** Reads own customer AR summaries (`GET /finance/my-customers/receivables`) and invoice payment/balance snapshot on own orders; blocked (`403`) from other customers, all admin `/finance/*` reports/mutations, and ALL `/costing/*` and `/profitability` endpoints.
- **`PRODUCTION_SUPERVISOR`:** Views batch/product costing and records direct overheads / finalizes batch costing (`/costing/runs/{id}/overheads`, `/costing/runs/{id}/finalize`); blocked (`403`) from voiding overheads and ALL customer `/finance/*` endpoints.
- **`FACTORY_ADMIN`:** Full operational authority across Payments, Allocations, Refunds, Reversals, Overhead Voiding, Costing Finalization, AR, and Profitability.
- **`ACCOUNTANT_AUDITOR` & `OWNER`:** Read-only oversight across Finance, AR, Statements, Costing, and Profitability; blocked (`403`) from all state-changing mutations.
