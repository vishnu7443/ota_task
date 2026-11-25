# Phase 8 — GST Billing, Invoicing & Dispatch Overview

## Architecture Summary

Phase 8 introduces the `billing` module (`d:\mac\ota\backend\app\modules\billing\`) and PostgreSQL `billing` schema (`alembic\versions\0005_phase8_gst_billing_and_dispatch.py`), connecting approved Phase 5 `sales.sales_orders` directly to statutory GST invoicing, downloadable Tax Invoice PDFs, immutable Credit Notes, partial/full Dispatches, delivery exception tracking, and operational GST/Dispatch reports while reusing the existing Phase 6/7 `inventory.inventory_movements` ledger and `CostLot` layer.

---

## Core Modules & Responsibilities

| Component | Path | Responsibility |
| --- | --- | --- |
| GST Engine | [`gst_engine.py`](file:///d:/mac/ota/backend/app/modules/billing/gst_engine.py) | Indian FY math, `Decimal` `ROUND_HALF_UP` tax computation, Place-of-Supply validation, round-off, Indian currency words |
| PDF Renderer | [`pdf_generator.py`](file:///d:/mac/ota/backend/app/modules/billing/pdf_generator.py) | Deterministic pure-Python PDF 1.4 Tax Invoice output rendered from persisted DB columns |
| Billing Models | [`models.py`](file:///d:/mac/ota/backend/app/modules/billing/models.py) | `FiscalSequence`, `Invoice`, `InvoiceItem`, `InvoiceTaxComponent`, `CreditNote`, `CreditNoteItem`, `Dispatch`, `DispatchItem`, `DispatchStatusHistory` |
| Billing Repository | [`repository.py`](file:///d:/mac/ota/backend/app/modules/billing/repository.py) | `SELECT ... FOR UPDATE` sequence allocation, lock helpers, cumulative dispatch sums, FEFO FG lot queries |
| Billing Service | [`service.py`](file:///d:/mac/ota/backend/app/modules/billing/service.py) | Invoice generation/verification/issuance, Credit Note issuance/restocking, Dispatch posting, Delivery updates, Reports |
| Billing API Router | [`router.py`](file:///d:/mac/ota/backend/app/modules/billing/router.py) | RBAC-scoped endpoints under `/api/v1/billing/*` |
| Order / Inventory Links | [`orders/service.py`](file:///d:/mac/ota/backend/app/modules/orders/service.py), [`inventory/service.py`](file:///d:/mac/ota/backend/app/modules/inventory/service.py) | Order lifecycle guards (`APPROVED -> INVOICED -> PARTIALLY_DISPATCHED -> DISPATCHED`) and ledger drill-downs |
| Frontend Billing & Dispatch UI | [`App.tsx`](file:///d:/mac/ota/frontend/src/App.tsx) | Billing Desk, Invoice Detail & PDF Preview, Credit Notes, Dispatch Desk, Delivery Tracking & GST Reports |

---

## Key Guarantees

- **Zero Inventory Ledger Duplication:** Dispatch issues (`DISPATCH_OUT`) and sellable Credit Note returns (`CREDIT_RETURN_IN`) write directly to `inventory.inventory_movements` (`dispatch_item_id`, `credit_note_item_id`), letting Phase 6 `fn_sync_balance_from_movement()` keep `inventory.inventory_balances` 100% consistent.
- **Immutability Enforced in PostgreSQL:** Database triggers prevent mutating or deleting issued GST Invoices, Invoice lines, Tax Components, issued Credit Notes, and Dispatch status history rows.
- **Role Preservation:** Enforces Phase 1–3 canonical roles (`FACTORY_ADMIN` executes operations; `ACCOUNTANT_AUDITOR` & `OWNER` hold read-only financial oversight; `SALESMAN` views own order invoices/PDF/dispatch status; `PRODUCTION_SUPERVISOR` is blocked `403`).
- **Scope Boundary:** Payment allocation (`paid_paisa`), production overheads, and financial reconciliation remain cleanly out of scope (`known-limitations.md`).
