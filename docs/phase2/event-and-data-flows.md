# Event and Data Flows & Monolith Architecture Evaluation

---

## 1. Event Propagation Taxonomy

Every step in a business flow is classified accurately by how it executes inside our system:
- **`[RECORD]` Persisted Business Record:** Primary ACID entity/ledger row saved in the relational store.
- **`[EVENT]` Synchronous In-Process Domain Event:** Internal typed domain event dispatched **inside the same transaction or immediately post-commit** within the modular monolith so modules remain decoupled without distributed network fragility.
- **`[PROJECTION]` Derived Read Model:** Query-time or transactionally synchronized read view (`InventoryBalance`, `CustomerReceivable`, Reports).
- **`[NOTIFY]` External Notification Trigger:** Outbound action after commit (PDF download stream, WhatsApp/Email share intent URL).

---

## 2. Event Flow A: Sales Loop (`Order -> Invoice -> Dispatch -> Payment`)

```mermaid
sequenceDiagram
    actor SM as Salesman (Mobile)
    participant ORD as Orders Module
    actor ADM as Factory Admin
    participant INV as Inventory Module
    participant BIL as Billing & GST
    participant PAY as Payments & AR
    participant AUD as Reporting & Audit

    SM->>ORD: SubmitOrder(client_order_id, lines)
    Note over ORD: [RECORD] SalesOrder(SUBMITTED) + AuditLog
    ORD-->>ADM: [PROJECTION] Appears in Admin Pending Queue

    ADM->>ORD: ApproveOrder(order_id)
    ORD->>INV: Check & ReserveFinishedStock(150 pkts)
    Note over INV: [PROJECTION] Reserved=150 (Avail: 238->88)
    ORD->>AUD: [EVENT] SalesOrderApproved -> AuditLog

    ADM->>BIL: IssueInvoiceFromOrder(order_id)
    Note over BIL: [RECORD] Invoice(INV/2026-27/0001) + TaxComponents
    BIL->>PAY: [EVENT] InvoiceIssued -> CreateReceivable(₹7,875)
    Note over PAY: [RECORD] CustomerReceivable(₹7,875 open)
    BIL-->>SM: [NOTIFY] Invoice PDF Shareable (WhatsApp/Email)

    ADM->>BIL: RecordDispatch(invoice_id, 150 pkts)
    BIL->>INV: [EVENT] DispatchRecorded -> PostDispatchDeduction(-150)
    Note over INV: [RECORD] InventoryMovement(DISPATCH_OUT -150)<br/>[PROJECTION] On-Hand: 238->88, Reserved: 150->0

    ADM->>PAY: RecordAndAllocatePayment(₹4,000)
    Note over PAY: [RECORD] Payment + PaymentAllocation<br/>[PROJECTION] Receivable=₹3,875; Invoice=PARTIALLY_PAID
    PAY->>AUD: [EVENT] PaymentAllocated -> AuditLog
```

### Step-by-Step Classification
1. `SalesOrderSubmitted` -> **`[RECORD]`** (`SalesOrder`) + **`[PROJECTION]`** (Admin Incoming Queue refreshes).
2. `StockAvailabilityChecked` -> **`[PROJECTION]`** (`Available = On-Hand - Reserved`; if short, `shortage_flag = true` triggers Admin warning).
3. `SalesOrderApproved` -> **`[RECORD]`** (`SalesOrder` state + `AuditLog`) + **`[EVENT]`** triggering `Inventory.ReserveFinishedStock`.
4. `InvoiceIssued` -> **`[RECORD]`** (`Invoice`, `InvoiceItem`, `InvoiceTaxComponent`, `FiscalSequence`) + **`[EVENT]`** triggering `Payments.CreateReceivable` + **`[NOTIFY]`** PDF/share preparation.
5. `DispatchRecorded` -> **`[RECORD]`** (`Dispatch`, `DispatchItem`) + **`[EVENT]`** triggering `Inventory.PostDispatchDeduction` (`InventoryMovement`: `DISPATCH_OUT`).
6. `PaymentAllocated` -> **`[RECORD]`** (`Payment`, `PaymentAllocation`) + **`[PROJECTION]`** (`CustomerReceivable`, `Invoice.payment_status`).

---

## 3. Event Flow B: Production & Variance Loop (`Purchase -> Run -> Costing -> Alerts`)

```
[PurchaseReceiptRecorded] ([RECORD] PUR + CostLot + PURCHASE_IN Movement)
        │
        ▼
[ProductionRunStarted] ([RECORD] PRD IN_PROGRESS + PROD_ISSUE_OUT + FIFO CostLot Depletion)
        │  └─► If |MaterialVar%| > 3% ──► [EVENT] VarianceAlertRaised ([RECORD] VarianceAlert)
        ▼
[ProductionRunCompleted] ([RECORD] PROD_OUTPUT_IN +188 FG + Packaging/Damage Movements)
        │  ├─► If |YieldVar%| > 3%   ──► [EVENT] VarianceAlertRaised ([RECORD] VarianceAlert)
        │  └─► [PROJECTION] Available FG Stock increases -> Pending Shortage Orders can now be re-evaluated!
        ▼
[ProductionOverheadsPosted] ([RECORD] ProductionOverhead -> ProductionCostSummary: ₹30.90/pkt)
        │
        ▼
[MonthEndAuditPackQueried] ([PROJECTION] Read-Only CSV/Excel/PDF Reports across all Modules)
```

---

## 4. Architectural Evaluation: Modular Monolith vs Distributed Microservices

| Dimension | Modular Monolith *(Selected)* | Distributed Microservices *(Rejected)* |
| --- | --- | --- |
| **ACID Consistency Across Modules** | **Native single-DB ACID transactions:** `ProductionRun` completion updates RM stock, packaging stock, FG stock, cost lots, and variance alerts atomically — zero partial failure! | Requires complex Saga / 2PC / Outbox orchestration; temporary negative stock or split-brain invoices easily occur on failure. |
| **Operational Scale Fit** | Ideal for 1 factory, 5–15 salesmen, 1–3 admins, and 1 auditor. Single deployable unit (`docker compose` / single command per Section 7 & 8). | Severe operational overhead (service discovery, distributed tracing, message brokers, multi-DB deployment) penalized as overengineering. |
| **Strict Domain Boundaries** | Enforced via clean module packages (`orders/`, `billing/`, `inventory/`, `production/`, `costing/`, `payments/`, `reporting/`) with explicit service APIs and forbidden cross-module raw table writes. | Enforced over HTTP/gRPC network hops, adding latency on weak-network mobile calls. |
| **Future Evolution Path** | Clean module interfaces and internal domain events let any module (e.g., PDF renderer or mobile sync gateway) extract cleanly later if the business scales to multiple factories. | Premature optimization upfront. |

**Conclusion:** A **Domain-Modular Monolith** with **Synchronous In-Process Domain Events** inside shared ACID boundaries delivers maximum correctness, zero distributed drift, simple single-command deployment, and crystal-clear code structure for live interview walkthroughs.
