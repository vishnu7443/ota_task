# Edge Cases & Failure Scenarios Catalogue

Each edge case specifies the trigger, business/technical risk, exact expected system behavior, user experience, and data/ledger invariant.

---

## 1. Sales & Mobile Connectivity Edge Cases

### `EC-01` — Weak Network During Order Submission
- **Trigger:** Salesman taps **Submit Order** in a rural/retail area; HTTP request stalls, times out, or drops mid-flight before the mobile UI receives `200/201 OK`.
- **Risk:** Salesman loses order data or retries blindly, creating duplicate orders or giving up and reverting to WhatsApp.
- **Expected System Behavior:**
  1. Mobile app generates a stable `client_order_id` (`UUID v4`) when the draft is prepared for submission and persists the full draft payload locally (`IndexedDB`/`localStorage`) *before* issuing the network call.
  2. Request uses a sane timeout (e.g., `10s`). On network failure/timeout, local draft transitions to `PENDING_RETRY` retaining the **exact same `client_order_id`**.
  3. Automatic exponential retry (or manual 1-tap *"Retry Sync"*) replays the exact payload with the same `client_order_id`.
- **Data Invariant:** Either `0` orders exist before server receipt or `1` exact `SUBMITTED` order exists once reached; salesman never re-types the order.

### `EC-02` — Duplicate Order Submission (Double-Tap or Retry Replay)
- **Trigger:** Salesman double-taps **Submit Order** quickly, or retries after an ambiguous timeout when the first server request actually succeeded.
- **Risk:** Factory receives two identical `150`-packet orders for Retailer A, causing duplicate invoicing and stock exhaustion.
- **Expected System Behavior:**
  1. UI immediately disables the submit button upon first tap until response/timeout resolves.
  2. Backend enforces a **unique constraint on `(salesman_id, client_order_id)`** (idempotency key).
  3. On duplicate arrival, backend detects existing order with matching `client_order_id` and returns `200 OK` with the existing order ID and `"Order already submitted"` confirmation rather than inserting a second row.
- **Data Invariant:** Strictly one `SalesOrder` record created per unique `client_order_id`.

### `EC-03` — Two Salesmen Ordering the Same Limited Stock Concurrently
- **Trigger:** Finished goods On-Hand = `100` packets. Salesman A submits Order 1 for `80` packets; 10 seconds later Salesman B submits Order 2 for `70` packets. Both appeared "in stock" while on the road. Then two admin tabs (or rapid clicks) try to approve both.
- **Risk:** Combined approvals (`150`) exceed physical stock (`100`), causing negative inventory at dispatch.
- **Expected System Behavior:**
  1. Submitting orders (`SUBMITTED`) is allowed for both so customer demand is recorded.
  2. Approval executes inside a **database transaction with row-level lock (`SELECT ... FOR UPDATE` on SKU stock/reservation state)**.
  3. Order 1 approves (`80 <= 100`), increasing `Reserved = 80` (`Available = 20`).
  4. Order 2 approval checks `Available = 20 < 70` and **fails atomically** with HTTP `409 Conflict`: `"Insufficient available stock: 20 available (100 on hand, 80 reserved), short by 50 packets."`
- **Data Invariant:** `Reserved Stock <= On-Hand Stock` always holds under concurrent approvals.

### `EC-04` — Insufficient Stock (Benchmark Step 6: Distributor B Orders 120 vs 88 Available)
- **Trigger:** Admin opens `ORD-002` (Distributor B, Karnataka, `120 packets`) while `Available FG Stock = 88 packets`.
- **Risk:** System allows approval/invoicing/dispatch into negative `-32 packets`, breaking stock ledger physics.
- **Expected System Behavior:**
  1. Admin queue & order detail highlight **`Shortage: 32 packets`** prominently.
  2. **Approve** action for full `120` is disabled/blocked (`409 Conflict` server-side too).
  3. Admin can: **(a) Hold / Await Production** (order remains pending until next production run finishes), **(b) Edit Qty to `<= 88`** (audit-logged with reason), **(c) Partial Fulfillment** (if enabled), or **(d) Reject Order** with shortage reason.
  4. Place-of-supply preview accurately calculates `IGST 5%` (`Karnataka != Tamil Nadu`) so Admin/Salesman see tax implications if/when invoiced.
- **Data Invariant:** Finished Goods balance stays `>= 0` (`88 packets` preserved).

---

## 2. Production & Inventory Edge Cases

### `EC-05` — Material Shortage During Production Issue
- **Trigger:** Supervisor tries to issue `35 L` Cooking Oil to a production run when Oil balance is only `19.5 L` (e.g., forgotten purchase receipt or typo `105 L` instead of `10.5 L`).
- **Risk:** Raw material balance turns negative (`-15.5 L`), corrupting FIFO cost layers / weighted average costing.
- **Expected System Behavior:**
  1. Server validates `issued_qty <= available_on_hand` in canonical base units (`ml`) inside a transaction lock before posting `PROD_ISSUE_OUT`.
  2. Blocks save with clear error: `"Insufficient stock for Cooking oil: requested 35 L, available 19.5 L (short 15.5 L). Record pending purchase or verify quantity."`
- **Data Invariant:** Raw material and packaging balances never go negative via production issue.

### `EC-06` — Production Run Failure / Aborted Batch (`IN_PROGRESS` -> `CANCELLED`)
- **Trigger:** Supervisor starts `PRD-002` and issues `40 kg` flour + `10 L` oil (`PROD_ISSUE_OUT` already deducted stock), but power fails or batch burns completely before packing (`0` good packets).
- **Risk:** Raw materials remain stuck in limbo (`IN_PROGRESS`), or deleting the run leaves stock permanently missing without explanation.
- **Expected System Behavior:**
  1. Deleting an `IN_PROGRESS` run that already issued stock is **forbidden**.
  2. Supervisor transitions run to `CANCELLED / SCRAPPED` (or completes with `0` good packets + mandatory failure reason):
     - **Unspoiled returned raw materials** (e.g., unused oil/flour returned to store) create `PROD_RETURN_IN` ledger entries restoring stock.
     - **Ruined/spoiled raw materials** remain deducted and are flagged as `100%` process scrap / loss in Production Variance & Scrap Report (`-100% yield`, reason logged in Audit Log).
- **Data Invariant:** Every gram/ml issued is either converted to good output, returned via `PROD_RETURN_IN`, or accounted for as logged scrap.

### `EC-07` — Damaged Packaging During Production (Benchmark Step 3: 6 Pouches Damaged)
- **Trigger:** Heat sealer jams and damages `6` empty `200 g` pouches while `188` pouches carry good snack packets.
- **Risk:** If system deducts only `188` pouches (`1 per good packet`), physical pouch shelf (`306`) disagrees with software (`312`).
- **Expected System Behavior:**
  1. Run completion form includes explicit `Damaged / Wasted Packaging` input alongside `Good Output`.
  2. System creates ledger entries deducting `188` (`PROD_ISSUE_OUT`) and `6` (`PACKAGING_DAMAGE_OUT`) -> `500 - 194 = 306`.
  3. Both good (`₹470`) and damaged (`₹15`) pouch costs are itemized on the run costing sheet (`₹485` total).
- **Data Invariant:** Physical pouch count reconciles exactly with `StockLedger`; scrap reason/count is visible to Auditor & Owner.

### `EC-11` — Incorrect Unit Conversion or Incompatible Unit Entry
- **Trigger:** User selects `litre` for a solid item measured in `kg` (e.g., trying to record Flour in `litres`), or enters `0.5 kg` where BOM expects `g`, or mixes `cartons` with `packets` without knowing pack size (`20 pkts/carton`).
- **Risk:** `1.2 kg` added to `500 g` as `501.2` (`1000x` error!), destroying stock balances and costing.
- **Expected System Behavior:**
  1. UI dropdown restricts unit selection strictly to compatible units in the item's unit family (`Mass: kg, g`; `Volume: L, ml`; `Count: piece, packet, carton`).
  2. Backend independently re-validates unit compatibility (`400 Bad Request` on cross-dimension mismatch) and converts to canonical base units (`g`, `ml`, `piece`) via exact deterministic multipliers (`1000`, `1`, `pack_size`).
  3. Converting `carton -> packet` verifies the specific SKU defines `packets_per_carton > 0`.
- **Data Invariant:** Zero `1000x` unit bugs and zero cross-dimension contamination.

---

## 3. Billing, Dispatch, Financial & Security Edge Cases

### `EC-08` — Posted Invoice Cancellation (Before or After Dispatch)
- **Trigger:** Admin discovers wrong customer or customer cancels order *after* GST Invoice `INV/2026-27/0001` was posted.
- **Risk:** Deleting or overwriting the invoice breaks FY GST sequential numbering and violates Indian tax audit rules.
- **Expected System Behavior:**
  1. `DELETE` / direct amount editing on `POSTED` invoices is strictly blocked (`409 Conflict`).
  2. Admin clicks **Cancel via Credit Note**, provides mandatory reason, and generates `CN/2026-27/0001` linked to `INV/2026-27/0001`.
  3. **If not yet dispatched:** Credit Note reverses AR (`-₹7,875`) and GST liability (`-₹187.50 CGST`, `-₹187.50 SGST`), and releases `150` reserved FG packets.
  4. **If already dispatched:** Credit Note reverses AR & GST, and prompts Admin to record **Goods Return**: sellable returned stock posts `CREDIT_RETURN_IN` (`+150` FG), while spoiled/opened food returns post to `RETURN_SCRAP` (never returned to sellable FG!).
  5. Original invoice status changes to `CANCELLED_BY_CN`; if payments were already allocated (`₹4,000`), overpayment becomes `UNALLOCATED_CUSTOMER_CREDIT` (refundable/re-allocatable).
- **Data Invariant:** FY sequence remains gap-free; GSTR report shows both original invoice and offsetting credit note.

### `EC-09` — Duplicate Payment Entry or Over-Allocation
- **Trigger:** Admin accidentally submits Retailer A's `₹4,000` UPI receipt twice, or enters `₹9,000` against a `₹7,875` invoice.
- **Risk:** Customer owes `-₹125` silently or receives fake double credit (`₹8,000` paid instead of `₹4,000`).
- **Expected System Behavior:**
  1. Payment form uses client `idempotency_key` (blocks identical replay) AND runs duplicate heuristic check (`same customer + same amount + same date + same payment ref` -> returns warning/requires explicit override or blocks).
  2. Allocating more than `invoice_outstanding` (`₹7,875`) is blocked unless Admin explicitly selects *"Record excess as Customer Advance Credit"*.
- **Data Invariant:** `Allocated Payments <= Invoice Grand Total - Credit Notes`.

### `EC-10` — Partial Dispatch & Undispatched Remainder
- **Trigger:** Admin invoices `150` packets (`INV-001`), van only holds `100` packets today (`DSP-001` = `100`), remaining `50` packets go tomorrow (`DSP-002` = `50`). *(If Partial Dispatch is enabled under Should-Have `FR-S-08`.)*
- **Risk:** System deducts all `150` on first trip or allows dispatching `100 + 80 = 180 > 150`.
- **Expected System Behavior:**
  1. Each dispatch note validates `dispatch_qty <= (invoiced_qty - already_dispatched_qty)` AND `dispatch_qty <= on_hand_fg_stock`.
  2. `DSP-001` deducts `-100` (`238 -> 138`) and releases `100` of `150` reserved (`Reserved = 50`), setting order status to `PARTIALLY_DISPATCHED`.
  3. `DSP-002` deducts `-50` (`138 -> 88`), releases remaining `50` (`Reserved = 0`), setting order status to `DISPATCHED`.
- **Data Invariant:** `Sum(Dispatched) <= Invoiced Qty` and `Reserved Stock` tracks exact unshipped commitment.

### `EC-12` — Unauthorized Role Access / Privilege Escalation
- **Trigger:** Salesman alters URL/API call to `/api/invoices/1/approve` or `/api/reports/costing`, or Accountant/Auditor calls `POST /api/payments` or `PATCH /api/orders/1`.
- **Risk:** Salesman self-approves orders, views factory costs/margins, or read-only Auditor alters books.
- **Expected System Behavior:**
  1. Backend middleware verifies JWT/session signature, active user status, and explicit RBAC permission map on **every** endpoint.
  2. Record-level scoping checks ownership (`salesman_id == current_user.id` for Salesman).
  3. Unauthorized attempts return `403 Forbidden`, perform zero state mutation, and log a security warning in the Audit Log.
- **Data Invariant:** Zero privilege bypasses via client manipulation.

---

## 4. Additional Critical Edge Cases (`EC-13` – `EC-16`)

### `EC-13` — Odd-Paisa Tax Rounding & CGST/SGST Symmetry
- **Trigger:** Line taxable value is `₹51.00` (`5100 paise`) at `5%` GST (`2.5% CGST + 2.5% SGST`). Raw `2.5% = ₹1.275`.
- **Expected Behavior:** Round CGST (`ROUND_HALF_UP` -> `₹1.28`) and SGST (`₹1.28`) identically from exact `250 bps` (`(5100 * 250 + 5000) // 10000 = 128` paise each, total tax `₹2.56`), using integer paise so `CGST == SGST` always holds and invoice totals never mismatch GSTR-1 line sums by 1 paisa.

### `EC-14` — Financial Year Rollover on April 1
- **Trigger:** Invoice posted on `2027-03-31` is `INV/2026-27/0142`; next invoice posted on `2027-04-01` enters Indian FY `2027-28`.
- **Expected Behavior:** Sequence generator keys off `indian_fy(invoice_date)` (`month >= 4 ? YYYY-(YY+1) : (YYYY-1)-YY`), resetting cleanly to `INV/2027-28/0001` without overwriting or colliding with `2026-27`.

### `EC-15` — Master Data Mutation After Historical Transactions (BOM or Price Edit)
- **Trigger:** Admin increases selling price of Murukku 200 g from `₹50` to `₹55`, or Supervisor edits BOM flour from `40 kg` to `42 kg`.
- **Expected Behavior:** Existing submitted/approved orders, posted invoices, and completed production runs **retain their frozen snapshot** (`₹50`, `40 kg`) and `bom_version_id`; edits create a new BOM version / effective price without altering historical invoices, tax reports, or past variance numbers.

### `EC-16` — Correcting a Typo in a Completed Production Run
- **Trigger:** Supervisor accidentally typed `180` good packets instead of `188` and clicked Complete Run (`PRD-001` is already `COMPLETED` and stock added).
- **Expected Behavior:** Raw completed numbers are **not** silently overwritten. System offers a logged **Production Run Correction / Stock Adjustment** workflow (Supervisor/Admin enters correction + mandatory reason) that posts offsetting `StockLedger` delta (`+8 pkts`), recalculates run yield variance & cost per packet, and records full `before/after` diff in `AuditLog` (Section 7: *"Edits to invoices and production runs are logged with user and time"*).
