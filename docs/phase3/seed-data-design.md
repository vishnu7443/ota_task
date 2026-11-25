# Benchmark Seed Data Design & Validation Specification

**Goal:** Guarantee exact, repeatable loading of the NIT Trichy Section 5 master data (`Step 0`) and mathematically validate every intermediate and final row state across `Steps 1–9`.

---

## 1. Deterministic Benchmark Master & Opening Seed Dataset (`Step 0`)

### 1.1 `iam` Seed
- **`iam.company_profiles`:** `legal_name = 'Kaveri Traditional Snacks Pvt. Ltd.'` (fictional), `gstin = '33AABCK1234F1Z5'`, `state_name = 'Tamil Nadu'`, `state_code = '33'`, `variance_tolerance_pct = 3.00`, `valuation_method = 'FIFO'`.
- **`iam.roles`:** `SALESMAN`, `FACTORY_ADMIN`, `PRODUCTION_SUPERVISOR`, `ACCOUNTANT_AUDITOR`, `OWNER`.
- **`iam.users`:** `salesman_a` (`Salesman A`), `salesman_b` (`Salesman B`), `admin` (`Factory Admin`), `supervisor` (`Production Supervisor`), `auditor` (`External Auditor`), `owner` (`Factory Owner`).

### 1.2 `sales` & `purchasing` Masters Seed
- **`sales.customers` & `customer_addresses`:**
  - `CUST-RET-A` (`Retailer A`, `RETAILER`, `Tamil Nadu`, `state_code = '33'`, `gstin = '33AAACR9999K1Z2'`, `assigned_salesman_id -> salesman_a`)
  - `CUST-DIST-B` (`Distributor B`, `DISTRIBUTOR`, `Karnataka`, `state_code = '29'`, `gstin = '29AAACD8888M1Z9'`, `assigned_salesman_id -> salesman_b`)
- **`purchasing.suppliers`:** `SUP-001` (`Cauvery Agro Mills`, `state_code = '33'`, `gstin = '33AAACS7777P1Z1'`).
- **`sales.products` & `sales.pack_sizes`:**
  - Product: `PROD-MRK` (`Murukku`, `category = 'Murukku'`, `hsn_code = '21069099'`, `gst_rate_bps = 500` [`5%`]).
  - Pack Size: `MRK-200G` (`Murukku 200 g`, `pack_weight_g = 200`, `packets_per_carton = 20`, `base_selling_price_paisa = 5000` [`₹50.00`]).
- **`sales.price_lists` & `price_list_items`:** Default price list (`is_default = TRUE`) mapping `MRK-200G -> 5000 paise`.

### 1.3 `production` Materials, Unit Conversions & BOM Seed
- **`production.unit_conversions`:** `kg->g (1000)`, `g->g (1)`, `L->ml (1000)`, `ml->ml (1)`, `piece->piece (1)`, `packet->packet (1)`.
- **`production.materials`:**
  1. `MAT-FLR` (`Flour`, `RAW_MATERIAL`, `MASS`, `g`, `kg`)
  2. `MAT-OIL` (`Cooking oil`, `RAW_MATERIAL`, `VOLUME`, `ml`, `L`)
  3. `MAT-SPC` (`Salt and spice mix`, `RAW_MATERIAL`, `MASS`, `g`, `kg`)
  4. `MAT-PCH-200` (`200 g pouch`, `PACKAGING_MATERIAL`, `COUNT`, `piece`, `piece`)
  5. `MAT-CTN-20` (`Carton (20 pkts)`, `PACKAGING_MATERIAL`, `COUNT`, `piece`, `piece`)
- **`production.recipe_templates`:** `REC-MRK` (`Murukku Base Mix`, `product = PROD-MRK`, `base_yield_weight_g = 40000.000`).
- **`production.bom_headers` / `bom_versions` / `bom_components`:**
  - `BOM-MRK-200G` -> `BomVersion v1` (`ACTIVE`, `expected_yield_pkts = 200`):
    - `MAT-FLR`: `40000.000 g` (`40 kg`, `COOKING_RAW`)
    - `MAT-OIL`: `10000.000 ml` (`10 L`, `COOKING_RAW`)
    - `MAT-SPC`: `1200.000 g` (`1.2 kg`, `COOKING_RAW`)
    - `MAT-PCH-200`: `200.000 piece` (`PACKAGING`)
    - `MAT-CTN-20`: `10.000 piece` (`PACKAGING`)

### 1.4 `inventory` Opening Balances (`Step 0` — Triggers `OPENING` Movements & `CostLot`s)

| Item | `opening_qty_base` | Display Qty | `entered_unit_rate` | `unit_cost_paisa_per_base` | Opening Value (`paisa` / `₹`) |
| --- | --- | --- | --- | --- | --- |
| `MAT-FLR` | `100000.000 g` | `100 kg` | `₹42.00 / kg` | `4.200000` | `420,000` (`₹4,200.00`) |
| `MAT-OIL` | `30000.000 ml` | `30 L` | `₹140.00 / L` | `14.000000` | `420,000` (`₹4,200.00`) |
| `MAT-SPC` | `5000.000 g` | `5 kg` | `₹200.00 / kg` | `20.000000` | `100,000` (`₹1,000.00`) |
| `MAT-PCH-200` | `500.000 pc` | `500 pcs` | `₹2.50 / pc` | `250.000000` | `125,000` (`₹1,250.00`) |
| `MAT-CTN-20` | `30.000 pc` | `30 pcs` | `₹15.00 / pc` | `1500.000000` | `45,000` (`₹450.00`) |
| `MRK-200G` | `50.000 pkt` | `50 pkts` | *TBD (`DEC-03`: e.g. ₹28.85)* | `2885.000000` *(proposed)* | `144,250` (`₹1,442.50`) |

---

## 2. Database-Level Validation Across Steps 1–9

| Step | Database Writes Executed | Verified Table State / Official Check Match |
| --- | --- | --- |
| **1** | Insert `purchase_receipts` (`PUR-001`), `purchase_receipt_items` (`60000 g`, `4500 paise/kg`, `4.500000 paise/g`, `270000 paise`), `inventory_movements` (`PURCHASE_IN +60000 g`), `cost_lots` (`L1-FLR: 60000 g @ 4.50`). | `inventory_balances` (`MAT-FLR`): `on_hand = 160000.000 g` (`160 kg`). |
| **2** | Insert `production_runs` (`PRD-001`, `IN_PROGRESS`, `v1`, `expected = 200`), `production_material_issues` (`RAW_ISSUE` × 3), `inventory_movements` (`PROD_ISSUE_OUT` × 3), `cost_lot_consumptions` (`L0-FLR: 40000 g`, `L0-OIL: 10500 ml`, `L0-SPC: 1200 g`), `production_variances` (Oil `+5.00%` flagged), `audit.variance_alerts` (Oil `+5%`). | `MAT-FLR = 120000 g (120 kg)`; `MAT-OIL = 19500 ml (19.5 L)`; `MAT-SPC = 3800 g (3.8 kg)`. RM cost = `339000 paise` (`₹3,390.00`). |
| **3** | Insert `production_outputs` (`188 pkts`), `production_wastages` (`6` damaged pouches = `1500 paise`), `production_material_issues` (`PACKAGING_PACK`: pouches `188 good + 6 dmg`, cartons `9`), `inventory_movements` (`PROD_OUTPUT_IN +188`, `PROD_ISSUE_OUT -188`, `PACKAGING_DAMAGE_OUT -6`, `PROD_ISSUE_OUT -9`), `production_variances` (Yield `-6.00%` flagged; Pouches `+3.19%` flagged), `audit.variance_alerts`. Update `PRD-001 -> COMPLETED`. | `MAT-PCH-200 = 306 pcs`; `MAT-CTN-20 = 21 pcs`; `MRK-200G = 238 pkts` (`50 + 188`). |
| **4** | Insert `sales_orders` (`ORD-001`, `SUBMITTED`, `client_order_id`, `Retailer A`, `state='33'`), `sales_order_items` (`150 pkts @ 5000 = 750000 paise`), `sales_order_status_history`. | `MRK-200G` remains `on_hand = 238, reserved = 0, available = 238`. |
| **5** | **Approve (`TX-02`):** `reserved += 150` (`available = 88`), `sales_order_approvals` (`APPROVED`).<br>**Invoice (`TX-03`):** `fiscal_sequences` -> `'INV/2026-27/0001'`; `invoices` (`INTRA_STATE`, `taxable=750000`, `cgst=18750`, `sgst=18750`, `igst=0`, `grand=787500`); `customer_receivables` (`original=787500, outstanding=787500`).<br>**Dispatch (`TX-04`):** `dispatches` (`DSP-001`), `inventory_movements` (`DISPATCH_OUT -150`), `on_hand = 88, reserved = 0, available = 88`. | Invoice = `₹7,500.00 + ₹187.50 + ₹187.50 = ₹7,875.00`; Finished `MRK-200G` = **`88 pkts`**; Cartons still `21`. |
| **6** | Insert `sales_orders` (`ORD-002`, `SUBMITTED`, `Distributor B`, `state='29'`, `120 pkts`). Admin check sees `available = 88 < 120`; `TX-02` rejects approval & writes `sales_order_approvals` (`HELD_SHORTAGE`, `shortage_pkts = 32`), `has_shortage = TRUE`. | Shortage of **`32`** flagged; `available = 88` preserved; `state '29' != '33'` computes **`IGST 5%`** if invoiced (`30000 paise` on 120 pkts / `22000` on 88). |
| **7** | Insert `payments` (`PMT-001`, `400000 paise` = `₹4,000.00`, `idempotency_key`), `payment_allocations` (`400000` -> `INV/2026-27/0001`). Update `customer_receivables` (`paid = 400000`, `outstanding = 387500`), `invoices.payment_status = 'PARTIALLY_PAID'`. | Retailer A outstanding = **`₹3,875.00`** (`387500 paise`). |
| **8** | Insert `production_overheads` (`LABOUR 120000`, `GAS_POWER 60000`), `production_cost_summaries` (`rm=339000`, `pkg=62000`, `direct_ovh=180000`, `total=581000`, `good=188`, `cost_per_packet=3090`, `selling=5000`, `margin=1910`). Update `PRD-001 -> POSTED` & FG `cost_lots.unit_cost = 3090`. | Cost per packet (FIFO) = **`₹30.90`** (`3090 paise`); Margin = **`₹19.10` (`38.20%`)**. |
| **9** | Query `reporting.*` views (`v_sales_register`, `v_gst_outward_summary`, `v_purchase_register`, `v_stock_reconciliation`, `v_production_summary`, `v_ar_ageing`) and `audit.audit_logs`. | Zero ledger drift (`v_stock_reconciliation.drift_qty_base = 0`); 100% parity with all 11 checks. |
