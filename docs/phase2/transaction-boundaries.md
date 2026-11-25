# Transaction Boundaries & Atomicity Guarantees

Every multi-entity mutation below executes inside a single **ACID atomic transaction (Unit of Work)**. Either every state transition, stock ledger movement, cost-lot change, receivable update, and audit entry commits together, or the entire operation rolls back cleanly leaving zero partial state.

---

## 1. Atomic Transaction Boundaries Catalogue

### `TX-01` — Mobile Order Submission (`Orders`)
- **Participating Entities:** `SalesOrder`, `SalesOrderItem`, `AuditLog`
- **Atomicity Scope:**
  1. Verify `(salesman_id, client_order_id)` idempotency uniqueness. If exists, exit early and return existing order (`200 OK`).
  2. Validate active `Customer` and resolve active `PriceList` rates (`unit_price_paisa` frozen onto lines).
  3. Insert `SalesOrder (SUBMITTED)` + all `SalesOrderItem` rows + `AuditLog` (`CREATE`).
- **Rollback & Failure Scenario:** If line price lookup fails or a negative quantity arrives mid-payload, entire `SalesOrder` rolls back; no orphan header without lines can exist.

### `TX-02` — Order Verification & Approval with Stock Reservation (`Orders` + `Inventory`)
- **Participating Entities:** `SalesOrder`, `SalesOrderItem`, `InventoryBalance` (row-locked), `AuditLog`
- **Deadlock Prevention:** Lock `InventoryBalance` rows for all SKUs on the order in deterministic ascending `product_id` order.
- **Atomicity Scope:**
  1. Re-verify `SalesOrder.status in (SUBMITTED, UNDER_REVIEW)`.
  2. If Admin edited qty/price, persist updates and log `before/after` diff + reason in `AuditLog`.
  3. For every line: assert `on_hand_qty_base - reserved_qty_base >= approved_qty_pkts`.
  4. Increment `InventoryBalance.reserved_qty_base += approved_qty_pkts`.
  5. Transition `SalesOrder.status -> APPROVED`, record `approved_by`, `approved_at`, and append `AuditLog`.
- **Rollback & Failure Scenario (`EC-03` / `EC-04`):** If line #2 of a 3-line order is short (`120 > 88`), the entire approval rolls back (`409 Conflict`); **zero** lines are partially reserved and `SalesOrder` stays `SUBMITTED`/`UNDER_REVIEW` with `shortage_flag = true`.

### `TX-03` — GST Invoice Posting (`Billing` + `Orders` + `Payments`)
- **Participating Entities:** `FiscalSequence` (locked), `SalesOrder`, `Invoice`, `InvoiceItem`, `InvoiceTaxComponent`, `CustomerReceivable`, `AuditLog`
- **Atomicity Scope:**
  1. Lock `SalesOrder` (`status == APPROVED`) to prevent double-invoicing.
  2. Determine `SupplyType` (`INTRA_STATE` vs `INTER_STATE`) from `CompanyProfile.state_code` vs `Customer.state_code`.
  3. Lock & increment `FiscalSequence` for `('INVOICE', indian_fy(invoice_date))` -> assign `INV/2026-27/0001`.
  4. Compute integer-paisa `InvoiceItem` & `InvoiceTaxComponent` totals (`ROUND_HALF_UP`).
  5. Persist `Invoice (ISSUED, UNPAID)` + lines + tax components + `CustomerReceivable (original = grand_total, outstanding = grand_total)`.
  6. Transition `SalesOrder.status -> INVOICED` and write `AuditLog`.
- **Rollback & Failure Scenario:** If receivable creation or tax symmetry assertion fails, `FiscalSequence` increment **rolls back too**, preserving strictly gap-free FY invoice numbering (`INV-BIL-02`).

### `TX-04` — Order Dispatch & Finished Stock Deduction (`Billing` + `Inventory` + `Orders`)
- **Participating Entities:** `Invoice`, `SalesOrder`, `Dispatch`, `DispatchItem`, `InventoryBalance` (locked), `InventoryMovement`, `CostLot` (FG COGS tracking), `AuditLog`
- **Atomicity Scope:**
  1. Verify `Invoice.doc_status == ISSUED` and `dispatched_qty <= remaining_undispatched`.
  2. Lock SKU `InventoryBalance`; assert `on_hand_qty_base >= dispatched_qty` (`INV-STK-01`).
  3. Create `Dispatch` + `DispatchItem` records.
  4. Append `InventoryMovement (DISPATCH_OUT, -dispatched_qty, source=DISPATCH)`.
  5. Decrement `InventoryBalance.on_hand_qty_base -= dispatched_qty` and release `reserved_qty_base -= min(reserved, dispatched_qty)`.
  6. Deplete Finished Goods `CostLot` layers (FIFO/FEFO) for COGS traceability.
  7. Update `Invoice.dispatch_status` & `SalesOrder.status` (`PARTIALLY_DISPATCHED` or `DISPATCHED`) and write `AuditLog`.
- **Rollback & Failure Scenario:** If ledger append or stock check fails, no `Dispatch` note is left behind and reservation remains intact.

### `TX-05` — Invoice Cancellation via Credit Note (`Billing` + `Payments` + `Inventory` + `Orders`)
- **Participating Entities:** `FiscalSequence` (locked), `Invoice`, `CreditNote`, `CreditNoteItem`, `CustomerReceivable`, `InventoryBalance` (if return/reservation), `InventoryMovement`, `SalesOrder`, `AuditLog`
- **Atomicity Scope:**
  1. Verify `Invoice.doc_status == ISSUED` (and not already fully credited).
  2. Acquire next `FiscalSequence` (`CN/2026-27/0001`).
  3. Create `CreditNote (ISSUED)` + `CreditNoteItem` reversing taxable, CGST/SGST/IGST, and total values.
  4. Update `Invoice.doc_status -> CANCELLED_BY_CN` (`payment_status -> CREDITED` if unpaid, or retain customer unallocated credit if payment existed).
  5. Update `CustomerReceivable` (`credited_paisa += total_reversed`, `outstanding_paisa` reduced).
  6. **Stock Branch:** If undispatched -> release FG reservation; if already dispatched & `return_disposition == RESTOCK_SELLABLE` -> append `CREDIT_RETURN_IN` (`+qty`) to `InventoryMovement` and increment `on_hand`; if `SCRAP` -> log return without polluting sellable FG.
  7. Append `AuditLog`.
- **Rollback & Failure Scenario:** Credit Note cannot exist without updating AR & original Invoice status; failure rolls back CN number allocation too.

### `TX-06` — Customer Payment Receipt & Allocation (`Payments` + `Billing`)
- **Participating Entities:** `Payment`, `PaymentAllocation`, `CustomerReceivable` (locked), `Invoice`, `AuditLog`
- **Atomicity Scope:**
  1. Check `idempotency_key` & duplicate reference guard (`EC-09`).
  2. Lock target `CustomerReceivable` & `Invoice` rows.
  3. Validate `allocated_paisa <= invoice_outstanding_paisa` (`INV-PAY-01`).
  4. Insert `Payment` + `PaymentAllocation` rows.
  5. Decrement `CustomerReceivable.outstanding_paisa` and increment `paid_paisa`.
  6. Update `Invoice.payment_status` (`PARTIALLY_PAID` or `PAID`) and write `AuditLog`.
- **Rollback & Failure Scenario:** Over-allocation on any invoice in a multi-invoice payment rolls back the entire payment receipt.

### `TX-07` — Purchase Receipt Posting (`Purchasing` + `Inventory`)
- **Participating Entities:** `PurchaseOrder` (optional), `PurchaseReceipt`, `PurchaseReceiptItem`, `InventoryBalance` (locked), `InventoryMovement`, `CostLot`, `AuditLog`
- **Atomicity Scope:**
  1. Convert each line's entered quantity (`60 kg`) to canonical base units (`60,000 g`) via `UnitConversion`.
  2. Save `PurchaseReceipt (RECEIVED)` + items (and increment `PurchaseOrderItem.received_qty_base` if PO-linked).
  3. For each item: append `InventoryMovement (PURCHASE_IN, +qty_base, source=PURCHASE_RECEIPT)`, increment `InventoryBalance.on_hand_qty_base`, and create a `CostLot` (`remaining = qty_base`, `unit_cost_paisa`).
  4. Write `AuditLog`.
- **Rollback & Failure Scenario:** Invalid UOM (`litres` for Flour) or negative cost rate aborts before any stock or cost lot changes.

### `TX-08` — Start Production Run & Issue Raw Materials (`ProductionAndBom` + `Inventory` + `ReportingAndAudit`)
- **Participating Entities:** `ProductionRun`, `ProductionMaterialIssue`, `InventoryBalance` (locked in `material_id` order), `CostLot` (locked), `InventoryMovement`, `VarianceAlert`, `AuditLog`
- **Atomicity Scope:**
  1. Pin active immutable `BomVersion`; compute `planned_qty_base = std_qty * batch_multiplier` and `expected_output_qty`.
  2. Lock `InventoryBalance` for all raw materials (`Flour`, `Oil`, `Spice`). Verify `on_hand >= actual_issued` (`INV-STK-01`).
  3. Deplete open `CostLot` rows (FIFO) -> compute exact `cost_absorbed_paisa` (`₹3,390.00`).
  4. Insert `ProductionRun (IN_PROGRESS)` + `ProductionMaterialIssue (RAW_ISSUE)` lines.
  5. Append `InventoryMovement (PROD_ISSUE_OUT, -actual_issued, source=PRODUCTION_RUN)` and decrement `InventoryBalance`.
  6. Evaluate consumption variances (`Oil +5.0% > 3.0%`) and insert `VarianceAlert` records + `AuditLog`.
- **Rollback & Failure Scenario (`EC-05`):** If Spice Mix passes check (`5 >= 1.2`) but Oil is short (`19.5 < 35`), the entire transaction rolls back — Spice Mix is **not** deducted!

### `TX-09` — Complete Production Run (Output + Damaged Packaging + Dual Ledger) (`ProductionAndBom` + `Inventory` + `Costing` + `ReportingAndAudit`)
- **Participating Entities:** `ProductionRun`, `ProductionMaterialIssue` (packaging), `InventoryBalance` (locked: pouches, cartons, finished product), `CostLot`, `InventoryMovement`, `ProductionCostSummary` (preliminary), `VarianceAlert`, `AuditLog`
- **Atomicity Scope:**
  1. Lock packaging (`200 g pouch`, `Carton`) and finished SKU (`Murukku 200 g`) balances in canonical sort order.
  2. Validate `good_pouches + damaged_pouches <= on_hand` (`194 <= 500`) and `cartons_used <= on_hand` (`9 <= 30`).
  3. Deplete packaging `CostLot`s (`₹485 + ₹135 = ₹620`) and post `PROD_ISSUE_OUT` (`-188` pouches, `-9` cartons) + `PACKAGING_DAMAGE_OUT` (`-6` pouches).
  4. Post `PROD_OUTPUT_IN` (`+188` Murukku 200 g packets) and create FG `CostLot` (`188 pkts`).
  5. Compute Yield Variance (`-6.0%`) & Output-Scaled Packaging Variance (`+3.19%`); insert `VarianceAlert`s if `abs(var) > 3%`.
  6. Transition `ProductionRun -> COMPLETED`, update preliminary `ProductionCostSummary`, and write `AuditLog`.
- **Rollback & Failure Scenario:** If pouch stock is insufficient (`194 > 150`), FG stock (`+188`) is **not** added and cartons (`-9`) are **not** deducted!

### `TX-10` — Record Run Overheads & Post Final Costing (`Costing` + `ProductionAndBom` + `Inventory`)
- **Participating Entities:** `ProductionRun`, `ProductionOverhead`, `ProductionCostSummary`, `CostLot` (FG lot unit cost update if unallocated / COGS adjustment), `AuditLog`
- **Atomicity Scope:**
  1. Persist `ProductionOverhead` rows (`Labour ₹1,200`, `Gas/Power ₹600`).
  2. Compute final `total_cost_paisa` (`₹5,810.00`), `cost_per_packet_paisa` (`₹30.90`), and `gross_margin_paisa` (`₹19.10`) in `ProductionCostSummary`.
  3. Update the run's Finished Goods `CostLot.unit_cost_paisa` (`3090 paise`) and transition `ProductionRun -> POSTED` + `AuditLog`.
- **Rollback & Failure Scenario:** Invalid negative overhead or `0`-good-output run triggers clean validation error or zero-output scrap handling (`INV-PRD-03`) without partial overhead rows.
