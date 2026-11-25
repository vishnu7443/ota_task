# Inventory Domain Design

**Core Mandate (Section 4.4 & Section 7):** Stock balances must never be manually overwritten numbers. Every inventory change across Raw Materials, Packaging Materials, and Finished Goods is an immutable, source-linked `InventoryMovement` entry.

---

## 1. Stock Categories & WIP Modeling

| Inventory Bucket | Entity Reference | Base Unit Examples | How Entered | How Consumed |
| --- | --- | --- | --- | --- |
| **Raw Materials** | `Material` (`RAW_MATERIAL`) | Flour (`g`/`kg`), Oil (`ml`/`L`), Spice (`g`/`kg`) | `OPENING`, `PURCHASE_IN`, `PROD_RETURN_IN`, `ADJUSTMENT` | `PROD_ISSUE_OUT`, `ADJUSTMENT` |
| **Packaging Materials** | `Material` (`PACKAGING_MATERIAL`) | 200 g Pouches (`piece`), Cartons (`piece`) | `OPENING`, `PURCHASE_IN`, `ADJUSTMENT` | `PROD_ISSUE_OUT` (good), `PACKAGING_DAMAGE_OUT` (damaged), `ADJUSTMENT` |
| **Work In Progress (WIP)** *(Optional)* | Represented by `ProductionRun` (`IN_PROGRESS`) | Issued RM value + qty bound to open batch | `ProductionRun` enters `IN_PROGRESS` (Step 2) | Converts to FG + Scrap on `COMPLETED` (Step 3) or returns via `PROD_RETURN_IN` on `CANCELLED` |
| **Finished Goods** | `Product` SKU (`Murukku 200 g`) | Packets (`packet`) | `OPENING`, `PROD_OUTPUT_IN`, `CREDIT_RETURN_IN`, `ADJUSTMENT` | `DISPATCH_OUT`, `ADJUSTMENT` |

> **Why Implicit WIP via `ProductionRun` is Optimal:** Creating a separate WIP virtual warehouse adds double ledger entries for a 1-day snack cooking cycle without business value, yet Step 2 (`IN_PROGRESS`) already deducts raw materials cleanly so another batch cannot consume the same oil/flour while batch 1 is frying!

---

## 2. Authoritative Ledger Movement Taxonomy & Sign Convention

Every `InventoryMovement` stores a **signed quantity in canonical base units** (`+` increases balance, `-` decreases balance) and a **mandatory non-null `(source_doc_type, source_doc_id)`**:

| `movement_type` | Sign | Target Bucket | Source Document | Business Meaning |
| --- | --- | --- | --- | --- |
| `OPENING` | `+` | RM, Packaging, FG | `SEED / OPENING_BALANCE` | Initial benchmark or go-live opening stock (`100 kg` flour, `50` Murukku pkts). |
| `PURCHASE_IN` | `+` | RM, Packaging | `PurchaseReceipt` (`PUR`) | Supplier goods received into factory store (`+60 kg` flour @ `₹45`). |
| `PROD_ISSUE_OUT` | `-` | RM, Packaging | `ProductionRun` (`PRD`) | Raw ingredients issued (`-40 kg`, `-10.5 L`, `-1.2 kg`) + good packaging used (`-188` pouches, `-9` cartons). |
| `PACKAGING_DAMAGE_OUT` | `-` | Packaging | `ProductionRun` (`PRD`) | Packaging destroyed/damaged on packing line (`-6` pouches). Separated from good usage for waste analytics! |
| `PROD_OUTPUT_IN` | `+` | Finished Goods | `ProductionRun` (`PRD`) | Good saleable packets produced by run (`+188` Murukku 200 g packets). |
| `PROD_RETURN_IN` | `+` | RM | `ProductionRun` (`PRD`) | Unspoiled materials returned from an aborted (`CANCELLED`) production run. |
| `DISPATCH_OUT` | `-` | Finished Goods | `Dispatch` (`DSP`) | Physical packets shipped against a posted `Invoice` (`-150` pkts Retailer A). |
| `CREDIT_RETURN_IN` | `+` | Finished Goods | `CreditNote` (`CN`) | Good/unopened returned packets restocked upon Credit Note sales return. *(Damaged food returns log to scrap and do NOT re-enter sellable FG.)* |
| `ADJUSTMENT` | `+` / `-` | RM, Packaging, FG | `StockAdjustment` (`ADJ`) | Physical stock-count discrepancy or floor spoilage outside a run; requires reason + Admin/Owner approval. |

### Closing Balance Reconciliation Formula
For any item $i$ and date range $[t_1, t_2]$:
$$\text{Opening}(t_1) = \sum_{\tau < t_1} \text{signed\_qty\_base}(i, \tau)$$
$$\text{Closing}(t_2) = \text{Opening}(t_1) + \text{Receipts} - \text{Issues/Dispatches} \pm \text{Adjustments} = \sum_{\tau \le t_2} \text{signed\_qty\_base}(i, \tau)$$

---

## 3. Why Mutable Balance Overwrites Are Unacceptable vs Ledger Authority

1. **Zero Traceability:** Overwriting `flour_stock = 120` hides whether 40 kg went to Murukku Batch #1, spilled on the floor, or was mistakenly typed twice.
2. **Silent Corruption & Concurrency Loss:** Two concurrent saves overwriting `stock = 238 - 150` and `stock = 238 - 50` exhibit classic *lost update* anomalies.
3. **Audit Non-Compliance:** External auditors verify opening + purchases − consumption − sales = closing. An append-only `InventoryMovement` ledger guarantees mathematical closure (`Opening + Δ = Closing`) and point-in-time historical reconstruction ("what was flour stock on Nov 15?").
4. **Role of `InventoryBalance` Cache:** `InventoryBalance` holds `(on_hand_qty_base, reserved_qty_base)` strictly as a **transactional lock anchor and fast read projection** updated exclusively by the `Inventory` module inside the exact same ACID transaction that appends `InventoryMovement`. A verification audit job/check asserts `InventoryBalance.on_hand_qty_base == SUM(InventoryMovement.signed_qty_base)` with zero tolerance.

---

## 4. Concurrency & Race-Condition Protection

### 4.1 Protecting Finished Goods Across Concurrent Orders (`EC-03`)
- **Problem:** Salesmen A and B both submit orders while `On-Hand = 100`. Physical stock only drops at **Dispatch**, leaving a danger window between Approval and Dispatch.
- **Solution — Two-Tier Reservation Model:**
  1. `InventoryBalance` tracks `on_hand_qty_base` and `reserved_qty_base`.
  2. `available_to_promise = on_hand_qty_base - reserved_qty_base`.
  3. On `SalesOrder` **Approval**, `Inventory` acquires an exclusive transactional lock on the SKU's `InventoryBalance` row, verifies `available_to_promise >= approved_qty`, and increments `reserved_qty_base`.
  4. On **Dispatch**, `Inventory` atomically appends `DISPATCH_OUT` (`-dispatched_qty`), decrements `on_hand_qty_base`, and decrements `reserved_qty_base`.
  5. Result: Two concurrent approvals competing for the last packets strictly serialize; the second gets `409 Conflict` with exact shortage (`EC-03`).

### 4.2 Protecting Raw Materials Across Concurrent Production Runs (`EC-05`)
- When Supervisor 1 starts a run (`PLANNED -> IN_PROGRESS`), `Inventory` acquires row locks on all required `Material` `InventoryBalance` rows (ordered deterministically by `item_id` to prevent deadlocks!) and locks oldest `CostLot` layers before posting `PROD_ISSUE_OUT`. Supervisor 2 cannot double-spend the same oil or flour lot.

---

## 5. Valuation & Cost-Lot Mechanics (`FIFO` Primary + Stretch `FEFO` Ready)

Each `OPENING`, `PURCHASE_IN`, or `PROD_OUTPUT_IN` creates an immutable `CostLot`:
- `original_qty_base`, `remaining_qty_base`, `unit_cost_paisa`, `received_at`, plus optional `batch_code` & `expiry_date`.
- **Material Issue Depletion (FIFO):** Consumes open lots (`remaining_qty_base > 0`) ordered oldest `received_at` first.
  - *Example:* Flour has Lot 1 (`100 kg @ ₹42`) + Lot 2 (`60 kg @ ₹45`). Issuing `40 kg` consumes `40 kg` from Lot 1 (`40 × ₹42 = ₹1,680.00`), leaving Lot 1 (`60 kg @ ₹42`) + Lot 2 (`60 kg @ ₹45`) = `₹5,220.00` closing stock.
- **Stretch Readiness:** Adding `expiry_date` sorting (`ORDER BY expiry_date ASC, received_at ASC`) switches Finished Goods dispatch seamlessly to **FEFO (First-Expiry-First-Out)** (`FR-G-02`) without altering the core ledger model!
