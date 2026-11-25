# Architecture Decisions, Conflicts & Unresolved Questions

**Purpose:** Document every significant domain and architectural decision with alternatives considered, trade-offs, and technical interview defense — while explicitly flagging unresolved decisions and Phase 1/Task 5 conflicts for your sign-off before Phase 3 physical database design.

---

## 1. Architecture Decision Records (`ADR-01` – `ADR-09`)

### `ADR-01` — Modular Monolith Over Distributed Microservices
- **Decision:** Build a single-deployable **Modular Monolith** with strict internal module boundaries (`IAM`, `SalesCatalog`, `Orders`, `Billing`, `Purchasing`, `Inventory`, `ProductionAndBom`, `Costing`, `Payments`, `ReportingAndAudit`) sharing one ACID transactional store.
- **Alternatives Rejected:** Microservices with async message broker.
- **Interview Defense:** Production completion and dispatch require **strict atomic multi-entity updates** (raw stock down, packaging down, finished goods up, variances + costing computed together). A modular monolith guarantees zero distributed eventual-consistency stock drift and satisfies the single-command deployability requirement (Section 7/8) while keeping clean service interfaces for future extraction.

### `ADR-02` — Append-Only `InventoryMovement` Ledger + Row-Locked `InventoryBalance`
- **Decision:** Treat `InventoryMovement` as the sole authoritative stock history (`Opening + Receipts - Issues/Sales ± Adjustments`) and keep `InventoryBalance` strictly as a transactional lock anchor & reconciled projection updated solely by the `Inventory` module.
- **Alternatives Rejected:** Directly updating a mutable `stock_qty` column on `Product`/`Material` without a ledger; or running full `SUM()` table scans without a lockable balance row.
- **Interview Defense:** Full ledger gives 100% audit traceability back to `PUR`/`PRD`/`DSP`/`CN`, while `InventoryBalance` gives deterministic row locking (`EC-03`) to prevent concurrent overselling and sub-millisecond reads, continuously verifiable against `SUM(InventoryMovement)`.

### `ADR-03` — Soft Stock Reservation on Order Approval; Physical Deduction on Dispatch
- **Decision:** Keep physical `On-Hand` untouched until `Dispatch` (preserving Section 4.2: *"Dispatch reduces finished-goods stock"*), while incrementing `Reserved` upon Order `Approval` so `Available = On-Hand - Reserved`.
- **Alternatives Rejected:** Deducting stock at Order Submission (blocks real demand capture like Step 6) or only checking at Dispatch (allows two approved orders to oversell the same `88` packets).
- **Interview Defense:** Mirrors real factory operations: approved orders commit warehouse boxes to a buyer before the truck leaves, preventing double-selling while keeping physical warehouse ledger accurate to dispatch timestamps.

### `ADR-04` — Shared `RecipeTemplate` + Product-Specific Immutable `BomVersion`
- **Decision:** Separate shared bulk cooking formulation (`RecipeTemplate`: `40 kg` bulk snack mix) from product-specific `BillOfMaterials` / `BomVersion` (`Murukku 200 g`: `200` packets + pouches + cartons), pinning `ProductionRun` to an immutable `BomVersion`.
- **Alternatives Rejected:** Flat 1-to-1 SKU-only BOM without versioning or recipe sharing.
- **Interview Defense:** Directly satisfies Section 9's live interview test (*"add a second pack size of 500 g sharing the same BOM"* — `80` expected packets from the exact same `40 kg` base recipe) AND prevents historical production variance reports from breaking when recipes change (`EC-15`).

### `ADR-05` — Integer-Paisa Money (`MoneyPaisa`) & Canonical Base-Unit Quantities
- **Decision:** Represent all currency in exact integer **paise** (`1 INR = 100 paise`), tax rates in **basis points** (`5% = 500 bps`), and stock quantities converted via exact rational multipliers into canonical base units (`g`, `ml`, `piece`). Use `ROUND_HALF_UP` explicitly.
- **Alternatives Rejected:** IEEE-754 `float` numbers or mixed-unit storage (`kg` mixed with `g`).
- **Interview Defense:** Eliminates binary floating-point bugs (`10.5 - 10.0 = 0.5000000000000001`, `₹1.275` asymmetric CGST/SGST splits, and `1000x` `kg` vs `g` errors).

### `ADR-06` — Two-Axis Invoice Status + Immutable Credit Note Cancellation
- **Decision:** Once `Invoice` transitions `DRAFT -> ISSUED`, its FY sequence number, lines, and GST components are frozen. Track settlement (`UNPAID | PARTIALLY_PAID | PAID | CREDITED`) orthogonally and cancel solely via linked `CreditNote`.
- **Alternatives Rejected:** Allowing invoice deletion or in-place editing after issuance.
- **Interview Defense:** Matches statutory Indian GST compliance and Section 7 audit rules (*"posted invoices are cancelled with a credit note, not deleted"*), keeping GSTR-1/3B summaries gap-free and defensible.

### `ADR-07` — Read Models for Reports Instead of Stored Report Tables
- **Decision:** Compute Sales Register, GSTR-1/3B Summary, Purchase Register, Stock Summary/Ledger, Production Report, and AR Ageing directly via deterministic queries over immutable posted records (`Invoice`, `CreditNote`, `InventoryMovement`, `ProductionCostSummary`, `CustomerReceivable`).
- **Alternatives Rejected:** Storing materialized monthly report snapshots that can fall out of sync with credit notes or late payments.
- **Interview Defense:** Guarantees 100% parity between transactional screens and auditor CSV/Excel/PDF exports.

### `ADR-08` — Client Idempotency Keys for Weak-Network Mobile Orders & Duplicate Payments
- **Decision:** Require client-generated UUID idempotency keys (`client_order_id` on `SalesOrder`, `idempotency_key` on `Payment`) enforced via unique constraints on the server, paired with local mobile draft persistence.
- **Alternatives Rejected:** Relying only on UI button disabling (fails on network timeouts and retries).
- **Interview Defense:** Solves weak rural 3G connectivity (`EC-01` / `EC-02`) cleanly in Must-Have scope without waiting for full offline background sync (`FR-G-01`).

### `ADR-09` — Two-Stage Production Stock Posting (`IN_PROGRESS` + `COMPLETED`) Before Overhead Close (`POSTED`)
- **Decision:** Raw materials post (`PROD_ISSUE_OUT`) at `IN_PROGRESS` (Step 2), Finished Goods + Packaging post (`PROD_OUTPUT_IN` + `PROD_ISSUE_OUT` / `PACKAGING_DAMAGE_OUT`) at `COMPLETED` (Step 3), and direct overheads finalize `ProductionCostSummary` at `POSTED` (Step 8).
- **Alternatives Rejected:** Deferring all stock postings until `POSTED` (would block Step 5 dispatch before Step 8 overheads are entered!).

---

## 2. Document Conflicts & Unresolved Decisions Requiring User Approval

Per Rule 3 (*"If documents conflict, identify the conflict and ask for a decision. Do not silently change requirements"*), please confirm your decisions on the following before Phase 3 physical schema design:

### A. Identified Conflicts Between Task 5 Prompt Examples & Phase 1 / Benchmark Baseline

1. **`CONF-01` — Production Run Stock-Posting Gate (`POSTED` vs `COMPLETED`):**
   - *Conflict:* Task 5 lists `Draft → Planned → In Progress → Completed → Posted`, implying `Posted` is the final state; however, Benchmark Steps 2–3–5–8 require raw materials to deduct in Step 2 (`IN_PROGRESS`), good packets (`238`) to become sellable in Step 3 (`COMPLETED`) **before** Step 5 dispatch (`150` pkts), and overheads (`₹1,200 + ₹600`) to be added in Step 8 (`POSTED`).
   - *Proposed Resolution (`ADR-09`):* Keep all Task 5 states, post RM on `IN_PROGRESS`, post FG + packaging on `COMPLETED`, and finalize overheads/unit cost on `POSTED` (also supporting 1-click `COMPLETED -> POSTED` if overheads are entered upfront). **Approve?**

2. **`CONF-02` — Sales Order `UNDER_REVIEW` vs `CORRECTION_REQUESTED`:**
   - *Conflict:* Task 5 lists `Draft → Submitted → Under Review → Approved / Rejected → Invoiced → Partially Dispatched / Dispatched`, omitting `Correction Requested` (explicitly required in Phase 1 prompt & `BR-ORD-01`) and `Cancelled`.
   - *Proposed Resolution:* Include **both** `UNDER_REVIEW` (for shortage-flagged / held orders like Distributor B) and `CORRECTION_REQUESTED` (sent back to Salesman) + `CANCELLED`. **Approve?**

3. **`CONF-03` — Purchase Workflow Depth (`PO` vs Direct Floor Receipt):**
   - *Conflict:* Task 5 lists `Draft → Approved → Received → Closed` (PO-centric), whereas Phase 1 Benchmark Step 1 records a direct supplier purchase receipt (`60 kg` flour @ `₹45`) and Section 6 classifies Purchasing under Should-Have.
   - *Proposed Resolution:* Model `PurchaseOrder` (`Draft -> Approved -> Received -> Closed`) as an **optional** upstream document while allowing `PurchaseReceipt` (`Draft -> Received -> Closed`) directly on delivery. **Approve?**

4. **`CONF-04` — Offline Capture Priority (`Section 4.1` vs `Section 6`):**
   - *Conflict:* Section 4.1 calls offline order capture *"strongly preferred"*, whereas Section 6 places *"Offline order capture with sync"* under **Stretch goals**.
   - *Proposed Resolution:* Deliver weak-network draft persistence + idempotent retry (`client_order_id`) in **Core**, and full offline catalog cache + background sync queue as a **Stretch** enhancement once Core passes. **Approve?**

---

### B. Open Phase 1 Domain & Accounting Decisions Carried Forward

5. **`DEC-01` — Inventory Valuation Method (Section 4.5 requires choosing one):**
   - **Option A (`FIFO`, Recommended):** Uses `₹42` flour lot before `₹45` lot -> `₹30.90/packet` (`₹5,810 / 188`), exact paisa math, and aligns naturally with food batch/expiry tracking.
   - **Option B (`Moving Weighted Average`):** Blends flour to `₹43.125/kg` -> `₹31.14/packet` (`₹5,855 / 188`).
   - *Requires your choice: `FIFO` or `Weighted Average`?*

6. **`DEC-02` — Damaged Packaging Cost in Unit Cost (`AMB-04`):**
   - **Option A (Recommended):** Include `6` damaged pouches (`₹15.00`) inside run cost (`₹30.90/pkt` FIFO).
   - **Option B:** Exclude damaged pouches from unit cost (`₹30.82/pkt`) and book `₹15.00` separately as floor scrap loss.

7. **`DEC-03` — Valuation of 50 Opening Finished Packets (`AMB-05`):**
   - Section 5 lists `50` opening packets of Murukku 200 g without an opening unit cost.
   - **Option A (Recommended):** Seed opening FG `CostLot` at standard opening BOM + overhead cost (`₹28.85/packet` = `₹1,442.50`) and document clearly in README.
   - **Option B:** Seed at zero / uncosted opening stock (excluded from COGS until run 1).

8. **`DEC-04` — Packaging Consumption Variance Baseline (`AMB-03`):**
   - **Option A (Recommended):** Compare consumed pouches (`194`) against output-scaled requirement (`188` -> `+6 / 188 = +3.19%` flagged), while showing batch BOM (`200`) alongside.
   - **Option B:** Compare strictly against fixed batch BOM (`194 vs 200 = -3.0%`).

9. **`DEC-05` — Salesman Customer Visibility Scope (`AMB-09`):**
   - **Option A:** Salesman sees only customers assigned to them (`Customer.assigned_salesman_id == user.id`, with unassigned/shared customers optionally visible).
   - **Option B:** All active salesmen can place orders for any active customer (simpler for small 5-person teams).

10. **`DEC-06` — Stock Reservation Policy (`AMB-02`):**
    - Approve **Soft Reservation on Order Approval** (`Available = On-Hand - Reserved`) with physical deduction at **Dispatch**, vs checking only at Dispatch?
