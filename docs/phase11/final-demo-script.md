# Final 10-Minute Live Demo Script (`Kaveri Traditional Snacks Pvt. Ltd.`)

Follow this step-by-step live presentation script using seeded benchmark credentials (`ENABLE_DEV_SEED=true`). Ensure backend (`127.0.0.1:8000`) and frontend (`127.0.0.1:5173`) are running on a freshly seeded `ota_dev` database (`uv run alembic upgrade head && uv run python -m app.seeds.benchmark_seed`).

---

## Segment 1 — Mobile Field Salesman & Shortage Detection (2 min)

1. **Open Mobile Viewport (`375px` width):** Navigate to `http://127.0.0.1:5173/login`, sign in as `salesman_a` / `SalesA@2026!`.
2. **Salesman Home (`/salesman`):** Show `Retailer A (TN)` card displaying live `Billed: ₹0.00 | Paid: ₹0.00 | Due: ₹0.00` balances.
3. **Attempt Full 150-Packet Order (`/salesman/orders/new`):**
   - Select `Retailer A`, add `MRK-200G` quantity `150` pkts (`₹50.00/pkt`).
   - Point out live available stock (`50 pkts`), shortage indicator (`Short by 100 pkts`), and automatic Intra-State GST preview (`CGST 2.5% + SGST 2.5%` = `₹187.50 + ₹187.50`, total `₹7,875.00`).
   - Tap **Submit Order**.
4. **Show Control Guard (`admin`):** Switch tab to desktop (`1280px`), sign in as `admin` / `Admin@2026!`, open the `150`-pkt order, and show that **Approve** is blocked cleanly because available FG (`50`) < ordered (`150`).

---

## Segment 2 — Purchasing, Production & BOM Variances (3 min)

1. **Purchase 60 kg Flour (`/admin/purchasing` -> `/admin/grn`):**
   - Sign in as `supervisor` / `Prod@2026!` (or `admin` for approval/GRN post): Create PO for `SUP-001` -> `60 kg MAT-FLR @ ₹45/kg`, approve as `admin`, receive GRN (`60 kg`, verified, posted).
   - Confirm `/admin/inventory` shows `MAT-FLR` increased `100 kg -> 160 kg`.
2. **Plan & Execute Batch PRD-001 (`/admin/bom` -> `/admin/production`):**
   - Inspect active BOM v1 for `MRK-200G` (200-pkt yield).
   - Plan 1.0x run -> Issue Materials (`40 kg MAT-FLR`, `10.5 L MAT-OIL`, `1.2 kg MAT-SPC`).
   - Complete Run (`188 good pkts`, `0 rejected`, `6 damaged pouches`, `9 cartons`) -> Post Production.
   - Show exact post-production stock balances: **Flour `120 kg`**, **Oil `19.5 L`**, **Pouches `306 pcs`**, **Cartons `21 pcs`**, **FG `MRK-200G` = `238 pkts`**.
   - Open Variance Report (`/admin/reports/variance`): highlight **Yield `-6.00% (FLAGGED)`** and **Oil `+5.00% (FLAGGED)`** alerts.
3. **Finalize Batch Costing (`/admin/costing`):**
   - Finalize overheads (`₹1,200` Direct Labour + `₹600` Gas/Power) -> point out exact **FIFO Batch Cost = `₹30.90/pkt`** (`Total ₹5,810.00`, `Gross Margin 38.20%`).

---

## Segment 3 — Order Approval, GST Billing, Dispatch & Payments (3 min)

1. **Approve & Invoice Retailer A (`/admin/orders` -> `/admin/billing`):**
   - Now approve Retailer A's `150`-pkt order (FG Available drops `238 -> 88 pkts`, Reserved `150`).
   - Generate, verify, and issue statutory invoice (`INV/2026-27/0001`, Total **`₹7,875.00`**), download **Invoice PDF**, and show **WhatsApp / Email** customer share actions.
2. **Dispatch (`INV-1` -> `88 pkts`):**
   - Post full dispatch (`150 pkts`), advance `IN_TRANSIT -> DELIVERED`, and show FG physical stock drops cleanly from **`238 -> 88 pkts`**.
3. **Inter-State Order & Shortage Guard (`salesman_b`):**
   - Login `salesman_b` / `SalesB@2026!`, submit `Distributor B (Karnataka 29)` order for `120 pkts` -> highlights **`32 pkts` Shortage** and automatic **Inter-State 5% IGST (`₹300.00`, zero CGST/SGST)**.
4. **Partial Payment & AR (`/admin/finance/payments`, `/admin/finance/receivables`):**
   - Record **`₹4,000.00` UPI** against `INV/2026-27/0001` -> Invoice updates to `PARTIALLY_PAID`, **AR Outstanding = `₹3,875.00`**, generate Payment Receipt PDF.
   - Refresh Salesman A mobile view (`/salesman`) -> shows Retailer A `Billed ₹7,875.00 | Paid ₹4,000.00 | Due ₹3,875.00`.

---

## Segment 4 — Audit, Cross-Module Reconciliation & Owner Intelligence (2 min)

1. **Centralized Audit Explorer (`/admin/audit`):** Sign in as `auditor` (`Audit@2026!`) or `owner` (`Owner@2026!`) — show request correlation `REQ-`, event types across all modules, zero exposed credentials, CSV export, and read-only enforcement.
2. **Cross-Module Reconciliation (`/admin/reconciliation`):** Run `INVENTORY` Sweep -> **`RECONCILED` (0 drift)**; run `FULL_SYSTEM` Sweep showing automated surfacing of PRD-001's low-severity `BOM_CONSUMPTION_VARIANCE` alongside clean Inventory/Sales/GST/AR/Dispatch parity.
3. **Management Intelligence Dashboard (`/admin/intelligence`):** Highlight Owner landing KPIs (`Net Sales ₹7,500`, `Gross Profit Margin`, `Open AR ₹3,875`, `Collections ₹4,000`, `Stock Valuation`, `Watchlist`).
