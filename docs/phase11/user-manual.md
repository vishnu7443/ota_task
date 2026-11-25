# User Manual — Order-to-Audit ERP (`Kaveri Traditional Snacks Pvt. Ltd.`)

This manual guides day-to-day operational users across mobile field sales and desktop factory control desks.

---

## 1. Login & Role-Based Landing Routes

Navigate to `/login` and sign in with assigned credentials:

| Role | Seed Username | Default Landing Page | Primary Responsibilities |
| --- | --- | --- | --- |
| Field Salesman (`SALESMAN`) | `salesman_a`, `salesman_b` | `/salesman` | Browse customers & live available FG stock, place mobile orders, track approvals, download invoice PDFs, monitor customer billed/paid/due balances. |
| Production Supervisor (`PRODUCTION_SUPERVISOR`) | `supervisor` | `/admin/inventory` | Manage BOM versions, run BOM material calculator, plan/issue/complete/post production runs, record batch overheads, create POs & GRNs, request stock adjustments. |
| Factory Admin (`FACTORY_ADMIN`) | `admin` | `/admin` | Full operational workbench: approve/adjust/reject orders, manage customers & SKU pricing, approve POs/GRNs & stock adjustments, verify/issue GST invoices, issue credit notes, dispatch/deliver shipments, record customer payments & refunds, close reconciliations. |
| Accountant / Auditor (`ACCOUNTANT_AUDITOR`) | `auditor` | `/admin` (Read-Only Oversight) | View all orders, GST invoices/reports, payments/AR ageing, batch costing, profitability, centralized audit logs, discrepancies, and reconciliation reports without write permissions. |
| Business Owner (`OWNER`) | `owner` | `/admin/intelligence` | Executive Management Intelligence Dashboard, KPI watchlists, profitability & AR oversight, user role governance, reconciliation correction approvals. |

---

## 2. Mobile Field Sales Workflow (`SALESMAN`, 375px-Optimized)

1. **Dashboard (`/salesman`):** View assigned customer cards showing live `Billed`, `Paid`, and `Due / Advance` INR balances alongside recent order statuses.
2. **Create Order (`/salesman/orders/new`):**
   - Select customer (state code & GST treatment auto-derived from customer master).
   - Add pack sizes (e.g., `MRK-200G` Murukku 200 g); live available stock (`on_hand - reserved`) is shown inline.
   - Review server-estimated Intra-State (`CGST + SGST`) vs Inter-State (`IGST`) tax breakdown before tapping **Submit Order**.
   - Client UUID (`client_order_id`) prevents accidental duplicate submission on flaky mobile networks.
3. **Order Tracking & Invoice Sharing (`/salesman/orders`, `/salesman/orders/:id`):**
   - Track real-time timeline (`SUBMITTED` -> `APPROVED` -> `INVOICED` -> `PARTIALLY_DISPATCHED` -> `DISPATCHED`).
   - Respond if Factory Admin sends `CORRECTION_REQUESTED`.
   - Download issued GST Invoice PDFs and share directly via **WhatsApp** or **Email** buttons, and view dispatch status (`DISPATCHED -> IN_TRANSIT -> DELIVERED`).

---

## 3. Desktop Factory Control Desk (`FACTORY_ADMIN` & `PRODUCTION_SUPERVISOR`)

### 3.1 Purchasing & Inventory
- **Suppliers (`/admin/suppliers`):** Maintain supplier GSTIN, state code, active status, and view PO/GRN history.
- **Purchase Orders (`/admin/purchasing`):** Supervisor drafts and submits multi-line POs (`kg`, `L`, `piece`); Admin approves (`POs never increase stock before GRN posting`).
- **Goods Receipts (`/admin/grn`):** Receive accepted vs rejected quantities linked to POs or direct supplier bills, verify, and post to add `PURCHASE_IN` ledger movements & FIFO `CostLot` layers.
- **Inventory & Adjustments (`/admin/inventory`, `/admin/inventory/ledger`, `/admin/reports/stock`):** Monitor live `Opening`, `Received`, `Issued`, `Dispatched`, `Adjusted`, `Physical`, `Reserved`, and `Available` metrics, filter chronological movements, export CSVs, and submit/approve dual-control count/damage adjustments.

### 3.2 BOM & Production Execution
- **Customers & Pricing (`/admin/catalog`):** Factory Admin adds verified customers (`BILLING` + `SHIPPING` addresses) and adjusts SKU selling prices with mandatory audit reasons (never alters issued invoices).
- **BOM & Scaling Calculator (`/admin/bom`):** Maintain versioned BOMs (`DRAFT -> ACTIVE`, immutable once active), inspect unit conversions, and calculate raw + carton requirements (`math.ceil` rounding) for any batch multiplier or packet target.
- **Production Runs (`/admin/production`, `/admin/production/:id`, `/admin/reports/variance`):**
  1. **Plan Run** (pins active `BomVersion`).
  2. **Issue Raw Materials** (`PROD_ISSUE_OUT` from FIFO lots; double issue blocked).
  3. **Complete Run** (record good vs rejected packets, actual raw consumed/wasted, good vs damaged packaging).
  4. **Post Production** (`PROD_OUTPUT_IN` FG FIFO lot + automatic `PRELIMINARY v1` batch cost summary + flagged variance alerts).

### 3.3 GST Billing, Dispatch & Credit Notes
- **Billing Console (`/admin/billing`, `/admin/invoices/:id`):** Generate GST draft invoices from `APPROVED` orders, verify tax snapshot (`HSN`, `CGST`/`SGST` or `IGST`, commercial round-off), issue statutory `INV/YYYY-YY/NNNN`, print/download single-page PDF, and record `INVOICE_CANCELLATION` or `SALES_RETURN` (`RESTOCK_SELLABLE` vs `SCRAP_DAMAGED`) Credit Notes.
- **Dispatch Tracking (`/admin/dispatch`):** Create partial or full dispatches from `ISSUED` invoices (stock deducts atomically on dispatch post via FEFO lot consumption, releasing order reservations), then update `IN_TRANSIT` and `DELIVERED` POD quantities.
- **Billing Reports (`/admin/reports/billing`):** Export CSV registers across all 7 tabs (Sales Register, GST Summary, Credit Notes, Dispatch Register, Customer Summary, Product Summary, Outstanding Invoices).

### 3.4 Finance, Payments & Product Costing
- **Payments (`/admin/finance/payments`):** Record `CASH`, `UPI`, `BANK_TRANSFER`, `NEFT`, `RTGS`, `IMPS`, `CHEQUE`, `CARD`, or `OTHER` payments with split allocations across one or many invoices (or hold as unallocated Advance), generate `%PDF-1.4` receipts (`PMT/YYYY-YY/NNNN`), refund advances (`RFD/YYYY-YY/NNNN`), or reverse payments with mandatory audit reason, and export CSV history.
- **Receivables & Ageing (`/admin/finance/receivables`):** Inspect due-date AR ageing buckets (`NOT_DUE`, `0–30`, `31–60`, `61–90`, `> 90` days) and download customer statements.
- **Batch Costing & Profitability (`/admin/costing`, `/admin/finance/profitability`):** Finalize direct overheads (`DIRECT_LABOUR`, `GAS_POWER`, etc.) and monthly shared factory pools (`cost_status: FINALIZED` snapshots), and review gross margin analytics by product, customer, and order.
