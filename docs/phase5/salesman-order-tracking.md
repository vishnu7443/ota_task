# Salesman Order Tracking & Correction Experience

Implemented in [SalesmanOrdersPage.tsx](file:///d:/mac/ota/frontend/src/pages/salesman/SalesmanOrdersPage.tsx) and [SalesmanOrderDetailPage.tsx](file:///d:/mac/ota/frontend/src/pages/salesman/SalesmanOrderDetailPage.tsx).

---

## 1. Mobile Order Tracking Capabilities (`PART 5 & PART 6`)

- **My Orders (`/salesman/orders`):**
  - Filter chips covering the entire lifecycle: `All`, `Submitted`, `Under Review`, `Correction`, `Approved`, `Rejected`, `Cancelled`.
  - Text search by order number or customer name.
  - Displays quantity revisions (`verified vs ordered`), status badge, submitted IST timestamp, estimated grand total, and Admin remarks / rejection reason previews directly on mobile cards.
  - Lightweight synchronization via **10-second polling** (`refetchInterval: 10_000`), window-focus refetch, and manual Refresh button — no WebSockets or brokers added.
- **Order Details (`/salesman/orders/:orderId`):**
  - Displays authoritative status banner (`SUBMITTED`, `UNDER_REVIEW`, `CORRECTION_REQUESTED`, `APPROVED`, `REJECTED`, `CANCELLED`).
  - Highlights contextual Admin decision details: approval actor & timestamp, rejection reason, cancellation reason, and `admin_remarks`.
  - Shows **ordered vs verified quantities** (`Originally submitted: 150 pkts -> Revised to 50 pkts`), unit price adjustment notice (with original rate preserved), taxable subtotal, GST estimate, and full **Order Status History Timeline**.

---

## 2. Salesman Correction & Pre-Approval Withdraw Loop

- **Inline Correction Resubmission (`PUT /api/v1/orders/{orderId}`):**
  - Available **only** when the order belongs to the logged-in salesman (`salesman_id == actor.user_id`) and `status == 'CORRECTION_REQUESTED'`.
  - Salesman adjusts packet quantities and delivery notes and resubmits; server ignores any client prices, resolves current `PriceList` rates, resets `approved_qty_pkts = NULL`, recomputes `has_shortage`, and transitions `CORRECTION_REQUESTED -> SUBMITTED`.
- **Pre-Approval Withdraw (`POST /api/v1/orders/{orderId}/cancel`):**
  - Permitted **only** for own orders in `SUBMITTED` or `CORRECTION_REQUESTED` status with a mandatory reason (`>= 5` chars). Blocked (`409`) once Factory Admin places the order under verification (`UNDER_REVIEW`) or approves/rejects it.

---

## 3. Data Privacy & Ownership Isolation (`PART 8`)

- Salesmen can never access another salesman's customers (`sales_service.validate_customer_access`), orders (`get_order_detail` returns `403`), or internal Admin audit/reservation payloads (`reservations` and `audit_trail` are stripped `[]` for `SALESMAN` responses).
