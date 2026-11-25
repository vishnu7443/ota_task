# Phase 8 — Delivery Tracking & Exception Handling

## Status Flow & Allowed Transitions

Once a Dispatch reaches `DISPATCHED`, Factory Admin records logistics & customer delivery confirmation via `POST /api/v1/billing/dispatches/{dispatch_id}/delivery`:

- `DISPATCHED` -> `IN_TRANSIT`, `DELIVERED`, or `DELIVERY_EXCEPTION`
- `IN_TRANSIT` -> `DELIVERED` or `DELIVERY_EXCEPTION`
- `DELIVERY_EXCEPTION` -> `IN_TRANSIT` or `DELIVERED`

Invalid jumps (e.g., updating delivery before `DISPATCHED` or regressing `DELIVERED`) are rejected with `409 INVALID_STATE_TRANSITION`.

---

## Line-Level Delivery Reconciliation

- Each `DispatchItem` stores `received_qty_pkts` and computed `discrepancy_qty_pkts = dispatched_qty_pkts - received_qty_pkts` (plus optional `discrepancy_remarks`).
- Database constraint `chk_dispatch_items_di_rec_bounds` ensures `0 <= received_qty_pkts <= dispatched_qty_pkts` and `discrepancy_qty_pkts >= 0`.
- Selecting `DELIVERED` without item overrides automatically sets `received_qty_pkts = dispatched_qty_pkts` and `discrepancy_qty_pkts = 0` on all lines.
- Selecting `DELIVERY_EXCEPTION` **requires** a non-empty `exception_reason` (`422 DomainValidationError`), stamps `delivery_date`, `delivery_confirmed_by`, `delivery_confirmed_at`, appends to immutable `dispatch_status_history`, and logs `DELIVERY_UPDATED` in `audit.audit_logs`.
- Example verified in tests: Dispatch of `50` pkts receiving `48` pkts records `received_qty_pkts = 48`, `discrepancy_qty_pkts = 2`, and `status = 'DELIVERY_EXCEPTION'`.

---

## Role Visibility

- `FACTORY_ADMIN`: Updates transit/delivery status and logs discrepancies.
- `ACCOUNTANT_AUDITOR` & `OWNER`: Full read-only visibility across Dispatch Desk & Dispatch Register.
- `SALESMAN`: Sees order-linked dispatch number, vehicle/transporter, status, delivery date, remarks, and exception reason directly on mobile Order Detail (`get_order_billing_dispatch_snapshot`).
