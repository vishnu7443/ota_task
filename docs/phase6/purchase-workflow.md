# Purchase Order Workflow (`docs/phase6/purchase-workflow.md`)

## Lifecycle State Machine
Purchase Orders (`purchasing.purchase_orders`) manage raw material and packaging procurement cleanly before physical receipt:

```
DRAFT ──submit──► SUBMITTED ──approve──► APPROVED ──partial receipt──► PARTIALLY_RECEIVED
  │                   │                     │                                 │
  │                   └──reject──► REJECTED │                                 │
  └──cancel──────────────────────► CANCELLED ◄──cancel (0 received)──────────┘
                                            └──final receipt posted────────► RECEIVED
```

## Critical Invariant: POs Do Not Mutate Stock
- Creating, submitting, approving, rejecting, or cancelling a Purchase Order **never** inserts into `inventory.inventory_movements`, `inventory.cost_lots`, or modifies `inventory.inventory_balances`.
- Physical stock increases **only** when a Goods Receipt is verified and posted (`PURCHASE_IN`).

## Pricing, GST & UOM Calculation
- Line items (`purchasing.purchase_order_items`) reference `production.materials.id` (Raw Materials or Packaging Materials — duplicate materials within the same PO are rejected).
- Quantities are entered in any dimension-compatible unit (`kg`/`g` for `MASS`, `L`/`ml` for `VOLUME`, `piece` for `COUNT`) and converted server-side via `convert_to_base_qty` to `ordered_qty_base`.
- Monetary values use exact integer paise (`unit_rate_paisa`, `line_subtotal_paisa`, `line_tax_paisa`, `line_total_paisa`) with standard GST basis points (`gst_rate_bps`, `0..2800`).

## Role Matrix & Guards
- `FACTORY_ADMIN` & `PRODUCTION_SUPERVISOR` can create DRAFT/SUBMITTED POs (`POST /api/v1/purchasing/orders`) and submit DRAFT POs (`POST /api/v1/purchasing/orders/{id}/submit`).
- Only `FACTORY_ADMIN` can `approve`, `reject` (mandatory reason min 5 chars), or `cancel` (blocked if any accepted receipts exist).
- Invalid state transitions (e.g., approving an already approved or rejected PO) return `409 Conflict`.
