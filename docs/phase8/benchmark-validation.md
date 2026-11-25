# Phase 8 — Official Benchmark Acceptance Validation (NIT Trichy Section 5)

Validated end-to-end against clean `benchmark_seed` data on `ota_test` inside [`test_1_final_acceptance_benchmark_retailer_a_and_distributor_b`](file:///d:/mac/ota/backend/tests/test_phase8_billing_and_dispatch.py#L113-L306).

---

## Verified Benchmark Execution Trace

| Step | Scenario Actor & Action | Verified System & Financial Output |
| --- | --- | --- |
| **Opening & Phase 7 Production** | `supervisor` completes 1× `MRK-200G` batch yielding `188` good packets | Physical FG becomes `50 + 188 = 238` packets (`available = 238`) |
| **Step 1 — Order A** | `salesman_a` orders `150` pkts `Murukku 200 g` (`₹50.00/pkt`) for `Retailer A` (`CUST-RET-A`, Tamil Nadu `33`, GSTIN `33AAACR9999K1Z2`) -> `admin` approves | Order status `APPROVED`; `StockReservation = 150`; `available = 238 - 150 = 88` pkts |
| **Step 2 — Draft Invoice** | `admin` creates Draft invoice (`2026-11-25`) | `doc_status = 'DRAFT'`, `invoice_number = NULL`; FG physical remains `238`, reserved remains `150`; duplicates blocked (`409 DUPLICATE_INVOICE`) |
| **Step 3 — Verify & Issue Invoice** | `admin` verifies and issues invoice | `INV/2026-27/0001` (`FY 2026-27`), `B2B` `INTRA_STATE`, HSN `21069099` `5%`; Taxable `750,000` paise (`₹7,500.00`), CGST `18,750` paise (`₹187.50`), SGST `18,750` paise (`₹187.50`), IGST `0`, Grand Total **`787,500` paise (`₹7,875.00`)**, `outstanding_paisa = 787500` |
| **Step 4 — Statutory PDF** | `admin` and `salesman_a` download PDF (`GET /invoices/{id}/pdf`) | `200 OK`, `application/pdf`, starts with `%PDF-1.4`, contains `INV/2026-27/0001`, `33AABCK1234F1Z5`, `33AAACR9999K1Z2`, `21069099`, `7,500.00`, `187.50`, `7,875.00` |
| **Step 5 — Physical Dispatch** | `admin` posts dispatch `DSP/2026-27/0001` for `150` pkts | `status = 'DISPATCHED'`; `DISPATCH_OUT` written to `inventory.inventory_movements`; FEFO `CostLot` depleted; `on_hand = 88`, `reserved = 0`, `available = 88`; Order `DISPATCHED` |
| **Step 6 — Delivery POD** | `admin` advances `IN_TRANSIT` -> `DELIVERED` (`150` pkts received) | `salesman_a` sees `INV/2026-27/0001` & `DELIVERED` tracking directly on own order detail |
| **Step 7 — Order B Shortage** | `salesman_b` orders `120` pkts for `Distributor B` (`CUST-DIST-B`, Karnataka `29`, GSTIN `29AAACD8888M1Z9`) | Flags `has_shortage = True`, `shortage_pkts = 32` (`88` available), pre-bill tax preview shows `INTER_STATE` IGST `30,000` paise (`₹300.00` on `₹6,000.00`); Approval blocked `409`; Invoicing unapproved order blocked `409` |
| **Step 8 — Inter-State Invoice B** | `admin` revises Order B to `88` pkts -> approves -> issues invoice | `INV/2026-27/0002`, `INTER_STATE` (Karnataka POS `29`), CGST `0`, SGST `0`, Taxable `440,000` paise (`₹4,400.00`), IGST `22,000` paise (`5% = ₹220.00`), Grand Total **`462,000` paise (`₹4,620.00`)** |
| **Step 9 — Reports Rollup** | `admin` checks `GET /api/v1/billing/reports` | `sales_register` count = `2`; `net_taxable_paisa = 1,190,000` (`₹11,900.00`), `net_cgst_paisa = 18,750`, `net_sgst_paisa = 18,750`, `net_igst_paisa = 22,000` |

---

## Stop-After-Phase-8 Confirmation

Per system phase rules, customer payment receipt `₹4,000` against `Retailer A` (`INV/2026-27/0001`), Step 8 overhead costing, and financial reconciliation remain cleanly out of scope (`outstanding_paisa` stays `787500` until Phase 9 Payments/Receivables).
