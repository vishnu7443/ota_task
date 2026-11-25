# Final Project Report — Order-to-Audit ERP (`Kaveri Traditional Snacks Pvt. Ltd.`)

**Internship Program:** NIT Tiruchirappalli Centre for Digital Infrastructure (CDI) Winter Internship 2026  
**Project Title:** Original Order-to-Audit Management System  
**Final Phase Completed:** Phase 11 — Full System Integration, Benchmark Validation, QA, Deployment & Submission (`2026-11-25`)

---

## 1. Executive Summary

Built from the ground up per the official CDI 2026 specification, this ERP replaces fragmented spreadsheets and informal messaging with a deterministic, role-scoped **Order-to-Audit system** for packaged snack manufacturing (`Kaveri Traditional Snacks Pvt. Ltd.`, Tiruchirappalli, Tamil Nadu).

All operations — mobile field order capture, admin stock reservation & shortage prevention, RM/Packaging purchasing & QC receipts, BOM-driven production & dual variance tracking, Indian GST billing (`CGST+SGST` vs `IGST`) & PDF rendering, partial/full FEFO dispatches, customer payments/advances/refunds & `due_date` AR ageing, FIFO production batch costing & gross margin profitability, immutable audit trails, cross-module reconciliation, and executive management intelligence — execute through **one single authoritative Stock Ledger (`inventory.inventory_movements`) and PostgreSQL 16 database**.

---

## 2. Architecture & Design Rationale

- **Backend Modular Monolith (Python 3.12 + FastAPI + SQLAlchemy 2.0 + Psycopg 3):** Selected so sales approvals, inventory deductions, FIFO cost lots, GST invoices, payment allocations, and audit events commit atomically inside single ACID PostgreSQL transactions without distributed-consensus failure modes.
- **Financial & Physical Precision:**
  - All currency figures stored as integer **paise (`BigInteger`)** (`₹50.00 -> 5000`); GST calculations use exact Python `Decimal` `ROUND_HALF_UP`.
  - Physical stock tracked in canonical base units (`g`, `ml`, `piece`, `packet`) as `NUMERIC(18,3)` with `NUMERIC(18,6)` lot unit costs and generated invariant columns (`available = on_hand - reserved`, `outstanding = original - credited - paid`).
- **Database-Enforced Guardrails (Alembic Migrations `0001`–`0007` across 9 Schemas / 54 Tables):**
  - PostgreSQL `fn_sync_balance_from_movement()` guarantees stock balances derive strictly from ledger inserts.
  - PostgreSQL `fn_prevent_mutation()` blocks updates/deletes on `audit.audit_logs`, `inventory.inventory_movements`, `sales.sales_order_status_history`, `billing.dispatch_status_history`, `audit.reconciliation_events`, active BOM versions, issued invoices/taxes, and closed reconciliation runs.
- **Role-Scoped Frontend (React 19 + TypeScript + Vite + Tailwind CSS):**
  - Dedicated `375px`-first Mobile Sales Experience (`/salesman/*`) with offline draft retention and UUID idempotency.
  - Dedicated Desktop Factory Control Desk (`/admin/*`) spanning all operational, financial, costing, audit, reconciliation, customer/pricing catalog, and executive intelligence views.

---

## 3. Delivery Progression Summary (Phases 1–11)

- **Phases 1–3:** Functional discovery, 11-check benchmark analysis (`AMB-01`–`AMB-07`), ER modelling (54 tables / 9 schemas), Alembic migration foundation, Argon2id/JWT security architecture.
- **Phases 4–5:** Auth, role boundaries, Salesman mobile order entry (`< 1 min`), Admin order queue, inline edit audit log, stock reservation on `APPROVED`, shortage block, concurrency locks.
- **Phase 6:** Suppliers, multi-unit POs, GRNs (`PURCHASE_IN` + FIFO `CostLot`), unified Stock Overview, Stock Ledger, dual-control Stock Adjustments, CSV Stock Reports.
- **Phase 7:** Extensible Product/Pack Size catalog (`MRK-500G`), versioned BOMs (`bom_headers`/`bom_versions`), BOM scaling calculator, controlled production lifecycle (`DRAFT -> POSTED`), dual yield/consumption/output-scaled variances (`BR-VAR-03`), `VarianceAlert`.
- **Phase 8:** Indian FY sequencing (`INV/YYYY-YY/NNNN`), GST place-of-supply engine (`33` TN vs `29` KA), statutory single-page `%PDF-1.4` invoice, Credit Notes (`INVOICE_CANCELLATION` / `SALES_RETURN`), partial & full FEFO dispatch, POD tracking, and 7-tab Billing Reports.
- **Phase 9:** Multi-mode customer payments (`PMT/YYYY-YY/NNNN`) & `%PDF-1.4` receipts, split invoice allocation, advances/refunds/reversals, CN payment unwind, `due_date` AR ageing & statements, FIFO production costing (`₹30.90/pkt`) + monthly pools, and Gross Margin profitability.
- **Phase 10:** Centralized Audit Explorer (`REQ-` correlation & secret redaction), `/iam/users` governance, Cross-Module Reconciliation Engine (`REC/YYYY-YY/NNNN`) with `STOCK_ADJUSTMENT` resolution workflow, and Owner Intelligence Dashboard.
- **Phase 11 (Final Hardening & Submission):**
  - Added Customer Master create (`POST /api/v1/sales/customers`), SKU price revision (`PATCH /api/v1/sales/products/{id}/price`), and [`AdminCatalogPage.tsx`](file:///d:/mac/ota/frontend/src/pages/admin/AdminCatalogPage.tsx).
  - Updated `OWNER` landing route directly to `/admin/intelligence`, added `Billed`/`Paid`/`Due` customer summaries on `SalesmanHomePage.tsx`, implemented CSV exports across all 7 tabs of `AdminBillingReportsPage.tsx` plus `AdminPaymentsPage.tsx` and `AdminInventoryLedgerPage.tsx`, and added `WhatsApp`/`Email` invoice share controls on Admin & Salesman views.
  - Added production multi-stage Nginx deployment stack ([`docker-compose.prod.yml`](file:///d:/mac/ota/docker-compose.prod.yml), [`frontend/Dockerfile.prod`](file:///d:/mac/ota/frontend/Dockerfile.prod), [`frontend/nginx.conf`](file:///d:/mac/ota/frontend/nginx.conf)).
  - Authored [`test_phase11_integration_benchmark_security.py`](file:///d:/mac/ota/backend/tests/test_phase11_integration_benchmark_security.py), measured real endpoint & concurrency benchmarks, completed all 13 Phase 11 deliverables + updated [`README.md`](file:///d:/mac/ota/README.md).

---

## 4. Verification Summary & Honest Environment Notes

| Check | Scope | Result | Reference |
| --- | --- | --- | --- |
| Backend Code Quality | `uv run ruff check app tests` | **0 errors** | Post-final edit |
| Full Automated Backend Suite | `uv run pytest -v` (Phases 4–11 on `ota_test`) | **62 passed, 0 failed (`160.10s`)** | [`end-to-end-testing-report.md`](file:///d:/mac/ota/docs/phase11/end-to-end-testing-report.md) |
| Section 5 Benchmark (11 Checks) | Continuous HTTP execution Steps 1–9 | **All 11/11 checks exact pass** | [`benchmark-validation-report.md`](file:///d:/mac/ota/docs/phase11/benchmark-validation-report.md) |
| Frontend TypeScript & Production Build | `npx tsc --noEmit && npm run build` | **0 errors (`1699` modules, `4.63s`)** | [`end-to-end-testing-report.md`](file:///d:/mac/ota/docs/phase11/end-to-end-testing-report.md) |
| Measured Latency & Concurrency | 11 core endpoints + 24 concurrent reads (8 workers) | **`8.93–69.87 ms` mean; `1371.86 ms` burst (24/24 200 OK)** | [`performance-testing-report.md`](file:///d:/mac/ota/docs/phase11/performance-testing-report.md) |
| Security, RBAC & Trigger Invariants | 5 roles, JWT, SQLi queries, triggers, ledger sums | **100% pass** | [`security-testing-report.md`](file:///d:/mac/ota/docs/phase11/security-testing-report.md) |
| Interactive Chrome DevTools Click-Through | Live browser UI (`375px` & `1280px`) | **Blocked in host env (`DevToolsActivePort ENOENT`)** | Live Uvicorn & Vite booted cleanly; Chrome remote debugging disabled locally |
| Container Stack Execution | `docker-compose.prod.yml` | **Statically verified; daemon N/A locally** | Docker Engine unavailable on local Windows host |

---

## 5. Final Submission Readiness Checklist

- [x] Every Section 6 Must-Have (`FR-M-01`–`14`) & Should-Have (`FR-S-01`–`08`) operational workflow complete and tested cleanly (with CSV/PDF report exports documented cleanly in lieu of binary `.xlsx`).
- [x] All 11 Official Section 5 Benchmark values verified simultaneously in [`test_phase11_integration_benchmark_security.py`](file:///d:/mac/ota/backend/tests/test_phase11_integration_benchmark_security.py).
- [x] Real PostgreSQL 16 ledger-backed architecture with zero mock financial/inventory records.
- [x] All 13 Phase 11 submission documents authored under `docs/phase11/` and [`README.md`](file:///d:/mac/ota/README.md) updated cleanly.
- [x] No plaintext production secrets or `.env` credentials tracked in Git.
