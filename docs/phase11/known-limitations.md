# Known Limitations & Scope Boundaries — Phase 11 Final Submission

This document transparently inventories every technical, regulatory, and functional scope boundary verified at the conclusion of Phase 11.

---

## 1. Deliberately Excluded External Integrations & Statutory Connectors

- **GST IRP / NIC e-Invoice & e-Way Bill Portals:** GST tax calculation, HSN validation, state-code place-of-supply verification, FY invoice numbering (`INV/YYYY-YY/NNNN`), and statutory PDF generation are complete, but live NIC e-Invoice IRN/QR API submission and E-Way Bill government portal uploads remain external integrations out of scope for the standalone hackathon/internship ERP.
- **Real-Time Payment Gateway Webhooks:** Customer payments (`UPI`, `NEFT`, `RTGS`, `IMPS`, `CHEQUE`, `CASH`, `CARD`) capture verified bank/UPI reference numbers manually with duplicate reference guards and PDF receipt generation; automated Razorpay/Stripe/NPCI webhook callbacks are not connected.
- **WhatsApp Business Cloud API / SMTP Mail Server:** Salesman and Admin **Share via WhatsApp** and **Share via Email** buttons launch `wa.me` and `mailto:` pre-filled links cleanly on the client device rather than relaying messages through paid third-party WhatsApp/SMTP SaaS credentials.

---

## 2. Export & Document Format Boundaries

- **Tabular Reports Export CSV & Print/PDF (Not Binary `.xlsx`):** All 7 Billing & GST Report tabs, Payments History, Inventory Ledger, Stock Valuation Reports, Centralized Audit Trail, Reconciliation Inventory Reports, and Executive Intelligence Summary export UTF-8 CSV (plus statutory Invoice PDF & Payment Receipt PDF). Multi-sheet binary `.xlsx` Excel generation is not bundled (CSV opens natively in Excel and LibreOffice Calc).

---

## 3. Financial Accounting & Costing Scope Boundaries

- **Gross Margin Only (No Full General Ledger / Double-Entry Accounting):** Product Costing and Profitability calculate FIFO raw/packaging material consumption, direct run overheads (`DIRECT_LABOUR`, `GAS_POWER`), and monthly factory overhead pool allocations to produce **Gross Profit (`Net Revenue excl. GST - Production COGS`)**. Non-production corporate SG&A expenses (office salaries, depreciation, bank charges), input GST credit claim offsetting (GSTR-2B vs GSTR-3B payable filing), and full P&L / Balance Sheet GL ledgers are explicitly outside MVP scope and flagged via API disclaimers.
- **Configurable Supplier Invoice Input Tax vs Benchmark 0%:** Purchasing POs and GRNs support configurable `gst_rate_bps` (including 5%/12%/18%), while the Section 5 Benchmark flow uses `0` bps (0% input tax) per `AMB-06` (`docs/phase1/benchmark-analysis.md`) so RM stock valuation tracks exact purchase rate `₹45/kg`.

---

## 4. Operational Concurrency & Frontend UX Boundaries

- **Containerized Production Runtime Verified by Static Inspection Only Locally:** [`docker-compose.prod.yml`](file:///d:/mac/ota/docker-compose.prod.yml), [`frontend/Dockerfile.prod`](file:///d:/mac/ota/frontend/Dockerfile.prod), and [`frontend/nginx.conf`](file:///d:/mac/ota/frontend/nginx.conf) follow Nginx reverse-proxy + non-seed production startup safety checks (`validate_production_safety()`), though local Docker Engine CLI execution was unavailable/timed out on the development workstation during final QA.
- **No WebSocket Push Alerts:** Dashboard KPIs and order queues update immediately on action responses and page navigation/refresh triggers rather than persistent Server-Sent Events or WebSockets.
- **Offline Queue Persistence:** Client-generated UUID idempotency keys (`client_order_id`, `client_payment_id`, `client_receipt_id`) protect retried mobile submissions against duplicates within an active browser session; full IndexedDB background Service Worker sync for zero-connectivity zones is future work.
