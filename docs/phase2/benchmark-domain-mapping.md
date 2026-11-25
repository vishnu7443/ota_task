# Benchmark Domain Mapping (Official Section 5 Scenario)

Maps all 9 mandatory benchmark steps strictly using official master data (`Murukku 200 g`, Tamil Nadu factory, `5%` GST, `3%` variance tolerance) to exact domain entities, modules, stock movements, financial effects, and verified outcomes.

---

## 1. Seed / Opening Domain State (`Step 0`)

| Item / Entity | Domain Classification | Opening Qty (`Base UOM`) | Valuation Rate / State |
| --- | --- | --- | --- |
| `Flour` | `Material` (`RAW_MATERIAL`, `MASS`) | `100 kg` (`100,000 g`) | `CostLot L0-FLR`: `100 kg @ ₹42.00/kg` (`₹4,200.00`) |
| `Cooking oil` | `Material` (`RAW_MATERIAL`, `VOLUME`) | `30 L` (`30,000 ml`) | `CostLot L0-OIL`: `30 L @ ₹140.00/L` (`₹4,200.00`) |
| `Salt and spice mix` | `Material` (`RAW_MATERIAL`, `MASS`) | `5 kg` (`5,000 g`) | `CostLot L0-SPC`: `5 kg @ ₹200.00/kg` (`₹1,000.00`) |
| `200 g pouch` | `Material` (`PACKAGING_MATERIAL`, `COUNT`) | `500 pcs` | `CostLot L0-PCH`: `500 pcs @ ₹2.50/pc` (`₹1,250.00`) |
| `Carton (20 pkts)` | `Material` (`PACKAGING_MATERIAL`, `COUNT`) | `30 pcs` | `CostLot L0-CTN`: `30 pcs @ ₹15.00/pc` (`₹450.00`) |
| `Murukku 200 g` | `Product` (`SKU`, `HSN`, `5% GST`) | `50 pkts` (`On-Hand=50, Reserved=0`) | `Selling Price = ₹50.00`; Opening Cost TBD (`DEC-03`) |

---

## 2. Step-by-Step Domain Execution Mapping

| Step | Business Operation | Owning & Collaborating Modules | Participating Entities | Inventory Movements (`InventoryMovement` & `CostLot`) | Financial / Tax / Variance Effects | Expected Verified State / Result |
| --- | --- | --- | --- | --- | --- | --- |
| **1** | Record purchase of `60 kg` flour at `₹45/kg` | `Purchasing` -> `Inventory`, `ReportingAndAudit` | `Supplier`, `PurchaseReceipt (PUR-001)`, `PurchaseReceiptItem`, `Material (Flour)`, `InventoryBalance`, `InventoryMovement`, `CostLot`, `AuditLog` | `+60,000 g` (`+60 kg`) Flour (`PURCHASE_IN`, source=`PUR-001`). Creates `CostLot L1-FLR` (`60 kg @ ₹45.00/kg`). | Purchase value = `₹2,700.00` (`270,000 paise`). Appears in Purchase Register. | Flour `On-Hand = 160 kg` (`₹6,900.00` across FIFO lots `₹42` + `₹45`). |
| **2** | Start run of `Murukku 200 g`: issue `40 kg` flour, `10.5 L` oil, `1.2 kg` spice | `ProductionAndBom` -> `Inventory`, `ReportingAndAudit` | `Product`, `BomVersion (v1)`, `ProductionRun (PRD-001)`, `ProductionMaterialIssue`, `InventoryBalance`, `InventoryMovement`, `CostLot`, `VarianceAlert` | `PROD_ISSUE_OUT` (source=`PRD-001`):<br>• Flour `-40 kg` (depletes `L0-FLR`: `100->60 kg @ ₹42`)<br>• Oil `-10.5 L` (depletes `L0-OIL`: `30->19.5 L @ ₹140`)<br>• Spice `-1.2 kg` (depletes `L0-SPC`: `5->3.8 kg @ ₹200`) | Raw Material Cost absorbed (FIFO) = `₹1,680 + ₹1,470 + ₹240 = ₹3,390.00`.<br>**Oil Consumption Variance:** `(10.5-10)/10 = +5.0%` -> **`VarianceAlert` Raised**. | Run `IN_PROGRESS`. Closing RM: Flour `120 kg`, Oil `19.5 L`, Spice `3.8 kg`. |
| **3** | Record output `188` good pkts, `6` pouches damaged, `9` cartons used | `ProductionAndBom` -> `Inventory`, `Costing`, `ReportingAndAudit` | `ProductionRun (PRD-001)`, `ProductionMaterialIssue` (packaging), `InventoryBalance`, `InventoryMovement`, `CostLot`, `VarianceAlert`, `ProductionCostSummary` | Source=`PRD-001`:<br>• Pouches `PROD_ISSUE_OUT -188` + `PACKAGING_DAMAGE_OUT -6` (`-194` total)<br>• Cartons `PROD_ISSUE_OUT -9`<br>• Murukku 200 g `PROD_OUTPUT_IN +188` (creates FG `CostLot`) | Packaging Cost = `194×₹2.50 + 9×₹15 = ₹620.00`.<br>**Yield Variance:** `(188-200)/200 = -6.0%` -> **`VarianceAlert` Raised**.<br>Output-scaled pouch wastage: `+3.19%` (`6/188`) -> Flagged. | Run `COMPLETED`. Pouches `306`, Cartons `21`, Finished Murukku `238 pkts`. |
| **4** | Salesman A (mobile) orders `150` pkts for Retailer A (Tamil Nadu) | `Orders` <- `SalesCatalog`, `IAM` | `User (Salesman A)`, `Customer (Retailer A, TN-33)`, `PriceList`, `SalesOrder (ORD-001)`, `SalesOrderItem`, `AuditLog` | **None** (Demand order only; FG stays `On-Hand=238, Reserved=0`). | Order quote = `150 × ₹50.00 = ₹7,500.00` before tax (`client_order_id` ensures idempotency). | `ORD-001` status = `SUBMITTED` in Admin Queue. |
| **5** | Admin approves `ORD-001`, raises GST invoice (`CGST+SGST`), records dispatch | `Orders` -> `Billing` -> `Inventory` -> `Payments` | `SalesOrder (ORD-001)`, `FiscalSequence`, `Invoice (INV/2026-27/0001)`, `InvoiceItem`, `InvoiceTaxComponent`, `CustomerReceivable`, `Dispatch (DSP-001)`, `DispatchItem`, `InventoryBalance`, `InventoryMovement`, `AuditLog` | 1. **On Approval:** `Reserved += 150` (`Available = 88`).<br>2. **On Dispatch:** `DISPATCH_OUT -150 pkts` (source=`DSP-001`); `Reserved -= 150`. *(Cartons untouched.)* | `INTRA_STATE (TN == TN)`: Taxable `₹7,500.00` + CGST (`2.5%`) `₹187.50` + SGST (`2.5%`) `₹187.50` = **`₹7,875.00`**.<br>`CustomerReceivable` created = `₹7,875.00`. | `ORD-001` = `DISPATCHED`; `INV` = `ISSUED / UNPAID`; Finished Goods closing = **`88 packets`**. |
| **6** | Salesman B orders `120` pkts for Distributor B (Karnataka) | `Orders` <- `Inventory`, `SalesCatalog` | `User (Salesman B)`, `Customer (Distributor B, KA-29)`, `SalesOrder (ORD-002)`, `SalesOrderItem`, `InventoryBalance`, `AuditLog` | **None** (Submission accepted; Approval blocked against `Available = 88`). | `ORD-002` `shortage_flag = true` (`Shortage = 32 pkts`).<br>Tax Preview: `INTER_STATE (KA != TN)` -> **`IGST 5%`** applies if invoiced (`₹6,000 + ₹300 = ₹6,300` full, or `₹4,400 + ₹220 = ₹4,620` if reduced to 88). | `ORD-002` held at `SUBMITTED` / `UNDER_REVIEW`; FG stock stays **`88 packets`**. |
| **7** | Record payment of `₹4,000` from Retailer A | `Payments` -> `Billing`, `ReportingAndAudit` | `Customer (Retailer A)`, `Payment (PMT-001)`, `PaymentAllocation`, `CustomerReceivable`, `Invoice (INV/2026-27/0001)`, `AuditLog` | **None** | `PMT-001` (`₹4,000.00`) allocated to `INV/2026-27/0001`.<br>AR reduced: `₹7,875.00 - ₹4,000.00` = **`₹3,875.00`**. | `INV` `payment_status = PARTIALLY_PAID`; Retailer A Outstanding = **`₹3,875.00`**. |
| **8** | Add `₹1,200` labour & `₹600` gas/power for run; show cost/packet | `Costing` -> `ProductionAndBom`, `Inventory` | `ProductionRun (PRD-001)`, `ProductionOverhead` (2 rows), `ProductionCostSummary`, `CostLot` (FG lot updated), `AuditLog` | Updates FG `CostLot` unit cost (`3090 paise/pkt`) without changing packet quantity (`188`). | Overheads = `₹1,800.00`. Total Cost (FIFO) = `₹3,390 + ₹620 + ₹1,800 = ₹5,810.00`.<br>**Cost/Packet = `₹5,810 / 188 = ₹30.90`** (`Margin = ₹19.10` / `38.20%`). | `PRD-001` = `POSTED`; `ProductionCostSummary` finalized. |
| **9** | Generate monthly reports (Section 4.6) | `ReportingAndAudit` (Read-Only queries over Modules 2–9) | Read Models over `Invoice`, `InvoiceTaxComponent`, `PurchaseReceipt`, `InventoryMovement`, `ProductionRun`, `VarianceAlert`, `ProductionCostSummary`, `CustomerReceivable`, `AuditLog` | Reconciles `Opening + Receipts - Issues/Sales = Closing` across all 6 items with zero drift. | Sales `₹7,500`, CGST `₹187.50`, SGST `₹187.50`, Purchases `₹2,700`, AR `₹3,875` (`0–30d`), Oil `+5%`, Yield `-6%`, Cost `₹30.90/pkt`. | All 6 report packs exported cleanly to CSV/Excel & PDF. |

---

## 3. Post-Benchmark Reconciled Closing Ledger Snapshot

| Item | Opening | Receipts (+) | Issues / Dispatch (−) | Closing Balance | FIFO Asset Value (₹) |
| --- | --- | --- | --- | --- | --- |
| Flour | `100 kg` | `+60 kg` (`PUR-001`) | `-40 kg` (`PRD-001`) | **`120 kg`** | `₹5,220.00` (`60×₹42 + 60×₹45`) |
| Cooking Oil | `30 L` | `0` | `-10.5 L` (`PRD-001`) | **`19.5 L`** | `₹2,730.00` (`19.5×₹140`) |
| Salt & Spice Mix | `5 kg` | `0` | `-1.2 kg` (`PRD-001`) | **`3.8 kg`** | `₹760.00` (`3.8×₹200`) |
| 200 g Pouch | `500 pcs` | `0` | `-188` good, `-6` dmg (`PRD-001`) | **`306 pcs`** | `₹765.00` (`306×₹2.50`) |
| Carton (`20 pkts`) | `30 pcs` | `0` | `-9 pcs` (`PRD-001`) | **`21 pcs`** | `₹315.00` (`21×₹15.00`) |
| Murukku 200 g (FG) | `50 pkts` | `+188 pkts` (`PRD-001`) | `-150 pkts` (`DSP-001`) | **`88 pkts`** | `50` opening (`DEC-03`) + `38` @ `₹30.90` |
