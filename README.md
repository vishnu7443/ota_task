# Order-to-Audit Management System (`Kaveri Traditional Snacks Pvt. Ltd.`)

Independent implementation for the **NIT Tiruchirappalli Centre for Digital Infrastructure (CDI) Winter Internship 2026** problem statement.

All company, customer, product, and transaction records are strictly fictional benchmark/test data derived from the problem specification and approved Phase 1–3 architecture baselines.

---

## Current Status: Phase 11 — Final System Integration, Benchmark Validation, QA & Submission Ready

Implemented and verified across Phases 4 through 11:
- **Modular Monolith Backend & Role-Scoped UI:** Backend modules (`iam`, `sales`, `orders`, `purchasing`, `inventory`, `production`, `billing`, `finance`, `costing`, `audit`, `reconciliation`, `intelligence`) layered across FastAPI routers, Pydantic schemas, state guards, services, repositories, and SQLAlchemy 2.0 models inside one ACID PostgreSQL 16 database, paired with mobile-first Salesman (`375px`) and desktop-first Factory Control Desk (`1280px`) interfaces.
- **PostgreSQL 16 Schema, Constraints & Triggers (`0001`–`0007`):**
  - Integer-paisa (`BigInteger`) financial columns, `NUMERIC(18,3)` canonical base quantities (`g`, `ml`, `piece`, `packet`), `NUMERIC(18,6)` sub-paisa FIFO/FEFO unit costs, `GENERATED ALWAYS AS` available-stock, invoice/credit-note total, payment unallocated-balance, and receivable outstanding-balance columns, `ON DELETE RESTRICT` foreign keys, append-only ledger/audit/dispatch-history/refund/reconciliation-event triggers (`fn_prevent_mutation()`), immutable BOM/invoice/payment/allocation/cost-summary/closed-reconciliation triggers, over-dispatch & over-allocation DB guards, and atomic movement-to-balance trigger (`fn_sync_balance_from_movement()`).
- **Sales Order Management & Customer/Pricing Master (Phases 4–5, 11):**
  - Enforced lifecycle across `SUBMITTED`, `UNDER_REVIEW`, `CORRECTION_REQUESTED`, `APPROVED`, `INVOICED`, `PARTIALLY_DISPATCHED`, `DISPATCHED`, `REJECTED`, and `CANCELLED` with row-level `FOR UPDATE` locks and `version` checks, plus atomic FG reservation upon approval.
  - Audited Customer Master creation (`POST /api/v1/sales/customers` with GSTIN/state validation + BILLING/SHIPPING addresses), active SKU selling price updates (`PATCH /api/v1/sales/products/{pack_size_id}/price` preserving historical invoices), Salesman mobile customer `Billed / Paid / Due` cards, and WhatsApp/Email invoice sharing.
- **Purchasing, Goods Receipts & Immutable Stock Ledger (Phase 6):**
  - Suppliers CRUD, multi-UOM RM/Packaging POs (`POs never mutate stock before GRN posting`), GRNs (`PURCHASE_IN` + FIFO `CostLot` layers), unified Stock Dashboard, CSV-exportable Stock Ledger & Stock Reports, and dual-control Stock Adjustments.
- **Bill of Materials, Production Execution & Variance Audit (Phase 7):**
  - Shared recipe templates, multi-pack SKU extensibility (`MRK-200G`, `MRK-500G`), immutable BOM versions, Decimal scaling + ceiling carton rounding calculator, controlled production lifecycle (`DRAFT -> POSTED`), dual yield/consumption/output-scaled variances (`BR-VAR-03`), and `audit.variance_alerts`.
- **GST Billing, Credit Notes & Dispatch Tracking (Phase 8):**
  - Indian FY invoice numbering (`INV/YYYY-YY/NNNN`), verified Place-of-Supply GST (`CGST+SGST` vs `IGST`), deterministic single-page `%PDF-1.4` invoices, `INVOICE_CANCELLATION` / `SALES_RETURN` Credit Notes, partial & full FEFO dispatches (`DISPATCH_OUT`), POD delivery tracking, WhatsApp/Email sharing, and 7-tab CSV-exportable Billing & GST Reports.
- **Payments, Accounts Receivable & Product Costing (Phase 9):**
  - Multi-mode customer receipts (`PMT/YYYY-YY/NNNN`) & `%PDF-1.4` receipts, split allocations, advances/refunds (`RFD/YYYY-YY/NNNN`), reversals, Credit Note unwind, strict `due_date`-based AR ageing & statements, FIFO batch costing (`₹30.90/pkt` with labour/power/monthly pools), Collections CSV export, and Gross Margin analytics.
- **Centralized Audit, Cross-Module Reconciliation & Management Intelligence (Phase 10):**
  - Centralized Audit Explorer (`REQ-` correlation refs, secret redaction, CSV export), IAM `/iam/users` governance, Cross-Module Reconciliation Engine (`REC/YYYY-YY/NNNN`, `FULL_SYSTEM` + discrepancy workflow), and Executive Owner Dashboard (`/admin/intelligence` landing route).

> **Scope & Known Boundaries:** Covers all Must-Have (`FR-M-01`–`14`) and Should-Have (`FR-S-01`–`08`) workflows through CSV/PDF exports (binary `.xlsx` omitted); external NIC e-Invoice portals, payment-gateway webhooks, non-production SG&A GL ledgers, and Service Worker offline outbox remain outside current scope. See [known-limitations.md](file:///d:/mac/ota/docs/phase11/known-limitations.md).

---

## Repository Structure

```text
├── Problem Statement - Winter Internship Application - 2026.docx
├── .gitignore
├── .env.example
├── docker-compose.yml                 # Local development stack
├── docker-compose.prod.yml            # Production Postgres + FastAPI + Nginx static/reverse proxy stack
├── infrastructure/
│   └── postgres/init/
│       └── 01-create-test-db.sql      # Creates isolated ota_test database
├── docs/
│   ├── phase1/                        # Business discovery & requirements (10 docs)
│   ├── phase2/                        # Domain modelling & architecture (14 docs)
│   ├── phase3/                        # PostgreSQL schema & security engineering (12 docs)
│   ├── phase4/                        # Phase 4 implementation & testing docs (9 docs)
│   ├── phase5/                        # Phase 5 lifecycle, verification & audit docs (9 docs)
│   ├── phase6/                        # Phase 6 purchasing & inventory docs (12 docs)
│   ├── phase7/                        # Phase 7 BOM & production docs (15 docs)
│   ├── phase8/                        # Phase 8 GST billing, PDF, CN, dispatch & delivery docs (16 docs)
│   ├── phase9/                        # Phase 9 payments, AR, batch costing, profitability & verification docs (9 docs)
│   ├── phase10/                       # Phase 10 centralized audit, reconciliation, intelligence & testing docs (11 docs)
│   └── phase11/                       # Phase 11 integration, benchmark, security, perf, deployment & manuals (13 docs)
├── backend/
│   ├── alembic/                       # 0001 -> ... -> 0007_phase10_audit_recon
│   ├── app/
│   │   ├── core/                      # Config, PostgreSQL session, exceptions, logging, security
│   │   ├── modules/
│   │   │   ├── iam/                   # Roles, users, login/me, user/role governance endpoints, RBAC guards
│   │   │   ├── sales/                 # Salesmen, customers, customer CRUD, products, pack sizes, price revisions
│   │   │   ├── orders/                # State machine, submission, verification, audit queries
│   │   │   ├── purchasing/            # Suppliers, Purchase Orders, Goods Receipts & QC posting
│   │   │   ├── inventory/             # Materials, UOMs, CostLots, Ledger, Adjustments & Reports
│   │   │   ├── production/            # BOM versioning, BOM calculator, runs, execution, posting & variances
│   │   │   ├── billing/               # GST engine, FY numbering, Invoices, PDF, Credit Notes, Dispatch & Reports
│   │   │   ├── finance/               # Payments, multi-invoice allocations, refunds, AR ageing, statements & profitability
│   │   │   ├── costing/               # FIFO production batch costing, direct & monthly overhead pools, snapshots
│   │   │   ├── audit/                 # Append-only audit explorer, summary, activity & reconciliation workflow models
│   │   │   ├── reconciliation/        # Cross-module diagnostic engine & discrepancy workflow API
│   │   │   └── intelligence/          # Real-time Management Intelligence KPIs, watchlist & CSV exports
│   │   └── seeds/
│   │       ├── benchmark_seed.py      # Official Section 5 master, RM/Pkg/FG opening stock, SUP-001 & MRK-200G BOM v1
│   │       └── dev_fixtures.py        # Optional separate controlled dev stock fixture helper
│   └── tests/                         # 62 automated Pytest tests against isolated ota_test DB
└── frontend/
    ├── Dockerfile.prod                # Multi-stage Vite build -> Nginx 1.27 static + /api/ proxy
    ├── nginx.conf                     # Security headers & SPA fallback configuration
    └── src/
        ├── lib/                       # API client, money & unit formatters, auth context
        ├── components/                # UI primitives, StatusBadge, mobile & desktop layouts
        └── pages/                     # Login, Salesman mobile pages, Admin Control Desk (incl. Customers & Pricing, Intelligence)
```

---

## Technology Stack & Architecture Rationale

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, Psycopg 3, `pwdlib` (Argon2id), `PyJWT`, Pytest, Ruff
- **Database:** PostgreSQL 16 (modular monolith sharing one ACID ledger across 9 schemas and 54 tables so approvals, reservations, FIFO consumption, GST invoices, payment allocations, and audit logs never drift)
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS, shadcn/ui primitives, Lucide React, React Router
- **Infrastructure:** Docker Compose (dev + multi-stage Nginx 1.27 production proxy stack in [`docker-compose.prod.yml`](file:///d:/mac/ota/docker-compose.prod.yml)), `.env`-based configuration with `validate_production_safety()`

---

## Official Section 5 Benchmark Validation Summary

Verified simultaneously end-to-end inside [`test_phase11_integration_benchmark_security.py`](file:///d:/mac/ota/backend/tests/test_phase11_integration_benchmark_security.py):
- **Flour Closing:** `120 kg` (`100 + 60 - 40`)
- **Oil Closing:** `19.5 L` (`30 - 10.5`)
- **Pouches / Cartons / Spice Closing:** `306 pcs`, `21 cartons`, `3.8 kg spice`
- **Finished Goods (`MRK-200G`):** `238 pkts` (`50 + 188`) post-production -> **`88 pkts`** after Retailer A dispatch
- **Variances:** Yield **`-6.00%` (FLAGGED)**, Oil **`+5.00%` (FLAGGED)**, Pouches output-scaled **`+3.19%` (FLAGGED)**
- **Batch Costing:** **`₹30.90/pkt`** (`₹5,810.00 / 188 pkts`, Gross Margin `38.20%`)
- **Retailer A Invoice & AR:** **`₹7,875.00`** (`INV/2026-27/0001`, Intra-State `CGST 2.5% + SGST 2.5%`) -> **`₹3,875.00`** (`PARTIALLY_PAID`) after `₹4,000.00` payment
- **Distributor B Shortage & GST:** **`32 pkts` shortage** on `120`-pkt order (blocked `409`); **`5% IGST`** (`INTER_STATE` TN `33 ->` KA `29`)

---

## Quick Start

### Option A: Development Docker Compose

```bash
cp .env.example .env
docker compose up --build -d
```

- Frontend: `http://localhost:5173`
- Backend API & Swagger Docs: `http://localhost:8000/api/v1/docs`
- PostgreSQL: `localhost:5432` (`ota_dev` and isolated `ota_test`)

### Option B: Local Development (PostgreSQL + Backend + Frontend)

Ensure PostgreSQL 16 is running on `localhost:5432` with superuser `ota_admin` (password `ota_dev_password`) and databases `ota_dev` and `ota_test` (UTF-8).

**Backend:**

```bash
cd backend
cp .env.example .env
uv sync --python 3.12
uv run alembic upgrade head
uv run python -m app.seeds.benchmark_seed
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

*(Optional separate dev fixture to test 150-pkt approval locally without altering benchmark seed: `uv run python -m app.seeds.dev_fixtures --add-pkts 150`.)*

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

### Option C: Production Container Stack ([`docker-compose.prod.yml`](file:///d:/mac/ota/docker-compose.prod.yml))

Requires a host `.env.prod` supplying `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `JWT_SECRET_KEY` (>= 32 chars), and `CORS_ORIGINS`; enforces `ENVIRONMENT=production` and `ENABLE_DEV_SEED=false`:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up --build -d
```

*(Production artifacts statically audited + Vite bundled cleanly; local Docker daemon execution N/A on Windows host.)*

---

## Verification & Automated Tests

**Backend Lint & Pytest (62 tests executed against isolated `ota_test`, never mutating `ota_dev`):**

```bash
cd backend
uv run ruff check app tests
uv run pytest -v
```

**Frontend Typecheck & Production Build:**

```bash
cd frontend
npx tsc --noEmit
npm run build
```

---

## Development Seed Accounts (`ENABLE_DEV_SEED=true` only)

| Username | Role | Password | Primary View |
| --- | --- | --- | --- |
| `salesman_a` | `SALESMAN` | `SalesA@2026!` | Mobile Salesman (`/salesman`) — own orders, invoice PDF/share, billed/paid/due customer cards |
| `salesman_b` | `SALESMAN` | `SalesB@2026!` | Mobile Salesman (`/salesman`) — assigned `Distributor B` (strictly isolated from Salesman A & all costing) |
| `admin` | `FACTORY_ADMIN` | `Admin@2026!` | Desktop Control Desk (`/admin`) — Orders, Customers & SKU Pricing (`/admin/catalog`), Purchasing, Inventory, BOM, Production, Billing, Dispatch, Payments, AR, Costing & Reconciliation |
| `supervisor` | `PRODUCTION_SUPERVISOR` | `Prod@2026!` | BOM, Production, Product Costing & Overheads, Purchasing & Inventory (`/admin/inventory`, blocked `403` on Sales Orders, Billing & Customer Finance) |
| `auditor` | `ACCOUNTANT_AUDITOR` | `Audit@2026!` | Desktop read-only oversight — Audit Explorer, Reconciliation, Management Intelligence, Finance/AR/Profitability, Costing, GST Reports & Ledger |
| `owner` | `OWNER` | `Owner@2026!` | Executive Management Intelligence Dashboard (`/admin/intelligence`) — cross-module KPIs, watchlist, user role governance, reconciliation correction approvals |

---

## Detailed Documentation

- **Phase 4 Foundation Docs:** [docs/phase4/](file:///d:/mac/ota/docs/phase4)
- **Phase 5 Order Management Docs:** [docs/phase5/](file:///d:/mac/ota/docs/phase5)
- **Phase 6 Purchasing & Inventory Docs:**
  - [supplier-management.md](file:///d:/mac/ota/docs/phase6/supplier-management.md)
  - [purchase-workflow.md](file:///d:/mac/ota/docs/phase6/purchase-workflow.md)
  - [goods-receipt-workflow.md](file:///d:/mac/ota/docs/phase6/goods-receipt-workflow.md)
  - [inventory-ledger.md](file:///d:/mac/ota/docs/phase6/inventory-ledger.md)
  - [stock-balance-management.md](file:///d:/mac/ota/docs/phase6/stock-balance-management.md)
  - [unit-management.md](file:///d:/mac/ota/docs/phase6/unit-management.md)
  - [stock-adjustments.md](file:///d:/mac/ota/docs/phase6/stock-adjustments.md)
  - [inventory-dashboard.md](file:///d:/mac/ota/docs/phase6/inventory-dashboard.md)
  - [api-documentation.md](file:///d:/mac/ota/docs/phase6/api-documentation.md)
  - [testing-report.md](file:///d:/mac/ota/docs/phase6/testing-report.md)
  - [benchmark-validation.md](file:///d:/mac/ota/docs/phase6/benchmark-validation.md)
  - [known-limitations.md](file:///d:/mac/ota/docs/phase6/known-limitations.md)
- **Phase 7 Documentation (`docs/phase7/`):**
  - [production-management-overview.md](file:///d:/mac/ota/docs/phase7/production-management-overview.md)
  - [bom-management.md](file:///d:/mac/ota/docs/phase7/bom-management.md)
  - [bom-versioning.md](file:///d:/mac/ota/docs/phase7/bom-versioning.md)
  - [bom-calculation-engine.md](file:///d:/mac/ota/docs/phase7/bom-calculation-engine.md)
  - [production-planning.md](file:///d:/mac/ota/docs/phase7/production-planning.md)
  - [material-issue-workflow.md](file:///d:/mac/ota/docs/phase7/material-issue-workflow.md)
  - [production-execution.md](file:///d:/mac/ota/docs/phase7/production-execution.md)
  - [quality-and-output-recording.md](file:///d:/mac/ota/docs/phase7/quality-and-output-recording.md)
  - [production-posting.md](file:///d:/mac/ota/docs/phase7/production-posting.md)
  - [variance-analysis.md](file:///d:/mac/ota/docs/phase7/variance-analysis.md)
  - [inventory-integration.md](file:///d:/mac/ota/docs/phase7/inventory-integration.md)
  - [api-documentation.md](file:///d:/mac/ota/docs/phase7/api-documentation.md)
  - [testing-report.md](file:///d:/mac/ota/docs/phase7/testing-report.md)
  - [benchmark-validation.md](file:///d:/mac/ota/docs/phase7/benchmark-validation.md)
  - [known-limitations.md](file:///d:/mac/ota/docs/phase7/known-limitations.md)
- **Phase 8 Documentation (`docs/phase8/`):**
  - [billing-overview.md](file:///d:/mac/ota/docs/phase8/billing-overview.md)
  - [invoice-generation.md](file:///d:/mac/ota/docs/phase8/invoice-generation.md)
  - [gst-calculation-engine.md](file:///d:/mac/ota/docs/phase8/gst-calculation-engine.md)
  - [place-of-supply-rules.md](file:///d:/mac/ota/docs/phase8/place-of-supply-rules.md)
  - [invoice-lifecycle.md](file:///d:/mac/ota/docs/phase8/invoice-lifecycle.md)
  - [invoice-numbering.md](file:///d:/mac/ota/docs/phase8/invoice-numbering.md)
  - [invoice-pdf-generation.md](file:///d:/mac/ota/docs/phase8/invoice-pdf-generation.md)
  - [credit-note-management.md](file:///d:/mac/ota/docs/phase8/credit-note-management.md)
  - [dispatch-management.md](file:///d:/mac/ota/docs/phase8/dispatch-management.md)
  - [partial-dispatch.md](file:///d:/mac/ota/docs/phase8/partial-dispatch.md)
  - [delivery-tracking.md](file:///d:/mac/ota/docs/phase8/delivery-tracking.md)
  - [inventory-integration.md](file:///d:/mac/ota/docs/phase8/inventory-integration.md)
  - [api-documentation.md](file:///d:/mac/ota/docs/phase8/api-documentation.md)
  - [testing-report.md](file:///d:/mac/ota/docs/phase8/testing-report.md)
  - [benchmark-validation.md](file:///d:/mac/ota/docs/phase8/benchmark-validation.md)
  - [known-limitations.md](file:///d:/mac/ota/docs/phase8/known-limitations.md)
- **Phase 9 Documentation (`docs/phase9/`):**
  - [phase9-overview.md](file:///d:/mac/ota/docs/phase9/phase9-overview.md)
  - [payment-workflow.md](file:///d:/mac/ota/docs/phase9/payment-workflow.md)
  - [invoice-allocation.md](file:///d:/mac/ota/docs/phase9/invoice-allocation.md)
  - [receivables-management.md](file:///d:/mac/ota/docs/phase9/receivables-management.md)
  - [costing-methodology.md](file:///d:/mac/ota/docs/phase9/costing-methodology.md)
  - [profitability-calculations.md](file:///d:/mac/ota/docs/phase9/profitability-calculations.md)
  - [database-changes.md](file:///d:/mac/ota/docs/phase9/database-changes.md)
  - [api-documentation.md](file:///d:/mac/ota/docs/phase9/api-documentation.md)
  - [testing-report.md](file:///d:/mac/ota/docs/phase9/testing-report.md)
- **Phase 10 Documentation (`docs/phase10/`):**
  - [phase10-overview.md](file:///d:/mac/ota/docs/phase10/phase10-overview.md)
  - [audit-architecture.md](file:///d:/mac/ota/docs/phase10/audit-architecture.md)
  - [audit-event-catalog.md](file:///d:/mac/ota/docs/phase10/audit-event-catalog.md)
  - [inventory-reconciliation.md](file:///d:/mac/ota/docs/phase10/inventory-reconciliation.md)
  - [financial-reconciliation.md](file:///d:/mac/ota/docs/phase10/financial-reconciliation.md)
  - [production-reconciliation.md](file:///d:/mac/ota/docs/phase10/production-reconciliation.md)
  - [discrepancy-resolution.md](file:///d:/mac/ota/docs/phase10/discrepancy-resolution.md)
  - [management-dashboard.md](file:///d:/mac/ota/docs/phase10/management-dashboard.md)
  - [database-changes.md](file:///d:/mac/ota/docs/phase10/database-changes.md)
  - [api-documentation.md](file:///d:/mac/ota/docs/phase10/api-documentation.md)
  - [testing-report.md](file:///d:/mac/ota/docs/phase10/testing-report.md)
- **Phase 11 Final Submission Documentation (`docs/phase11/`):**
  - [final-requirement-matrix.md](file:///d:/mac/ota/docs/phase11/final-requirement-matrix.md)
  - [system-integration-report.md](file:///d:/mac/ota/docs/phase11/system-integration-report.md)
  - [benchmark-validation-report.md](file:///d:/mac/ota/docs/phase11/benchmark-validation-report.md)
  - [end-to-end-testing-report.md](file:///d:/mac/ota/docs/phase11/end-to-end-testing-report.md)
  - [security-testing-report.md](file:///d:/mac/ota/docs/phase11/security-testing-report.md)
  - [performance-testing-report.md](file:///d:/mac/ota/docs/phase11/performance-testing-report.md)
  - [deployment-guide.md](file:///d:/mac/ota/docs/phase11/deployment-guide.md)
  - [installation-guide.md](file:///d:/mac/ota/docs/phase11/installation-guide.md)
  - [user-manual.md](file:///d:/mac/ota/docs/phase11/user-manual.md)
  - [administrator-manual.md](file:///d:/mac/ota/docs/phase11/administrator-manual.md)
  - [known-limitations.md](file:///d:/mac/ota/docs/phase11/known-limitations.md)
  - [final-project-report.md](file:///d:/mac/ota/docs/phase11/final-project-report.md)
  - [final-demo-script.md](file:///d:/mac/ota/docs/phase11/final-demo-script.md)
#   o t a _ t a s k  
 