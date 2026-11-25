# Phase 5 — Order Management Overview

**Project:** Order-to-Audit Management System (`Kaveri Traditional Snacks Pvt. Ltd.`, NIT Tiruchirappalli CDI Winter Internship 2026)  
**Scope:** Complete Sales Order Lifecycle, Admin Order Verification, Stock Availability & Reservations, Salesman Order Tracking, Server-Side Pricing & Recalculation, and Immutable Audit Trail.

---

## 1. Summary of Changes Over Phase 4

Phase 4 established authentication, master data, mobile order submission (`SUBMITTED`), and read-only Admin visibility. Phase 5 turns that initial vertical slice into a complete pre-billing Sales Order Management and Verification system while preserving every Phase 4 contract cleanly:

| Capability | Phase 4 Baseline | Phase 5 Enhancement |
| --- | --- | --- |
| **Database Schema** | `0001_phase4_foundation` | Additive migration `0002_phase5_order_lifecycle`: admin/rejection/cancellation columns + `version` on `sales_orders`, `original_unit_price_paisa` on `sales_order_items`, `CHECK (from_status IS DISTINCT FROM to_status)` on `sales_order_status_history`, and `inventory.stock_reservations` |
| **Order Lifecycle** | Creation only (`SUBMITTED`) | Explicit state machine (`SUBMITTED`, `UNDER_REVIEW`, `CORRECTION_REQUESTED`, `APPROVED`, `REJECTED`, `CANCELLED`) with row locks (`FOR UPDATE`) and terminal transition guards |
| **Stock Verification** | Read-only shortage flag | Concurrent-safe pessimistic locking (`ORDER BY id ASC FOR UPDATE`) on `inventory.inventory_balances`, per-item `inventory.stock_reservations`, and `409 INSUFFICIENT_STOCK` enforcement preventing overselling or negative stock |
| **Admin Interface** | Incoming table + read-only inspect | Dashboard summary KPIs, 5 lifecycle tabs (`Pending Verification`, `Incoming`, `Approved`, `Rejected`, `All`), multi-criteria filters (order #, customer, salesman, date range, status, shortage), interactive qty/price override editor, Hold/Correction/Approve/Reject/Cancel actions, reservation view, and full audit log table |
| **Salesman Mobile UI** | Order submit + basic list | Rich order detail view showing live status, Admin remarks, rejection/cancellation reasons, original vs verified qty/price diffs, status timeline, 10s polling sync, inline correction resubmission (`PUT /orders/{id}`), and pre-approval withdrawal |

---

## 2. Preserved Scope Boundaries

Per Phase 5 specifications, **GST Invoice generation, Dispatch/Finished Goods physical deduction, Customer Payments & Receivables, Production Runs, BOMs, and Costing** remain excluded in this phase and will be added cleanly via Phase 6+ migrations on top of `0002_phase5_order_lifecycle`.

---

## 3. Architecture Principles Preserved

1. **Modular Monolith Boundaries:** Logic remains cleanly separated across [state_machine.py](file:///d:/mac/ota/backend/app/modules/orders/state_machine.py), [service.py](file:///d:/mac/ota/backend/app/modules/orders/service.py), [repository.py](file:///d:/mac/ota/backend/app/modules/orders/repository.py), [router.py](file:///d:/mac/ota/backend/app/modules/orders/router.py), and [inventory/service.py](file:///d:/mac/ota/backend/app/modules/inventory/service.py).
2. **ACID Atomicity:** Every order revision, approval + stock reservation, cancellation + reservation release, rejection, and correction resubmission runs inside a single PostgreSQL transaction with deterministic rollback on failure.
3. **Zero Float Arithmetic:** All monetary values, overrides, and CGST/SGST/IGST recalculations use integer paise and `ROUND_HALF_UP` basis-point arithmetic (`((taxable_paisa * rate_bps) + 5000) // 10000`).
