# Order-to-Audit Management System (`Kaveri Traditional Snacks Pvt. Ltd.`)

Independent end-to-end ERP / Factory Management implementation for the **NIT Tiruchirappalli Centre for Digital Infrastructure (CDI) Winter Internship 2026** problem statement.

All company, customer, product, supplier, and transaction records are fictional benchmark/test data derived from the problem specification and approved Phase 1–3 architecture baselines.

---

## Quick Start for Evaluators (Run Locally)

### Prerequisites
- **Option 1 (Fastest):** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with Docker Compose v2) + Git
- **Option 2 (Native Local Setup):**
  - **PostgreSQL 16** running on `localhost:5432`
  - **Python 3.12+** & [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
  - **Node.js 20+** & `npm`

---

### Option 1: Run Everything with Docker Compose (Recommended)

```bash
git clone https://github.com/vishnu7443/ota_task.git
cd ota_task
```

Create `.env` from template:
- **macOS / Linux:** `cp .env.example .env`
- **Windows PowerShell:** `Copy-Item .env.example .env`

Start PostgreSQL, Backend (`alembic upgrade head` + automatic Section 5 benchmark seed), and Frontend:
```bash
docker compose up --build -d
```

Wait ~20–30 seconds for migrations and seeding to finish, then open:
- **Web App (Login):** `http://localhost:5173`
- **Backend API Health:** `http://localhost:8000/api/v1/health`
- **Swagger / OpenAPI Docs:** `http://localhost:8000/api/v1/docs`

Useful Docker management commands:
```bash
docker compose logs -f backend     # Watch backend migrations & seed output
docker compose down                # Stop containers (preserve DB data)
docker compose down -v             # Stop containers and reset database volume
```

---

### Option 2: Run Locally Without Docker (Windows PowerShell / macOS / Linux)

#### Step 1 — Create PostgreSQL 16 Role & Databases (`ota_dev` and isolated `ota_test`)
Connect as PostgreSQL superuser (`psql -U postgres`) and run:
```sql
CREATE ROLE ota_admin WITH LOGIN PASSWORD 'ota_dev_password' CREATEDB SUPERUSER;
CREATE DATABASE ota_dev OWNER ota_admin ENCODING 'UTF8';
CREATE DATABASE ota_test OWNER ota_admin ENCODING 'UTF8';
```

#### Step 2 — Configure, Migrate, Seed & Start Backend (Terminal 1)

**macOS / Linux:**
```bash
cd backend
cp .env.example .env
uv sync --python 3.12
uv run alembic upgrade head
uv run python -m app.seeds.benchmark_seed
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Windows PowerShell:**
```powershell
cd backend
Copy-Item .env.example .env
uv sync --python 3.12
uv run alembic upgrade head
uv run python -m app.seeds.benchmark_seed
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

*(Optional dev-only helper if you want to immediately test full 150-packet Retailer A approval without first running a production batch: `uv run python -m app.seeds.dev_fixtures --add-pkts 150`.)*

#### Step 3 — Install & Start Frontend (Terminal 2)
```bash
cd frontend
npm install
npm run dev
```

Open **`http://localhost:5173`** in your browser. Root `/` always directs to **`/login`**, and signing in routes automatically to that role's workspace.

---

## Evaluator Test Accounts (`ENABLE_DEV_SEED=true`)

Seeded idempotently by [`backend/app/seeds/benchmark_seed.py`](backend/app/seeds/benchmark_seed.py):

| Username | Role | Password | Landing Route | Scope |
| --- | --- | --- | --- | --- |
| `salesman_a` | `SALESMAN` | `SalesA@2026!` | `/salesman` | Mobile Field App (`375px`) — assigned `Retailer A` (TN `33`), orders, invoice PDF/share, billed/paid/due AR cards |
| `salesman_b` | `SALESMAN` | `SalesB@2026!` | `/salesman` | Mobile Field App (`375px`) — assigned `Distributor B` (KA `29`), isolated from Salesman A & factory costing |
| `admin` | `FACTORY_ADMIN` | `Admin@2026!` | `/admin` | Desktop Control Desk — Orders, Customers & SKU Pricing (`/admin/catalog`), Purchasing, Inventory, BOM, Production, Billing, Dispatch, Payments, AR, Costing & Reconciliation |
| `supervisor` | `PRODUCTION_SUPERVISOR` | `Prod@2026!` | `/admin/inventory` | Purchasing, Inventory, BOM & Production, Batch Costing & Overheads (blocked `403` on Sales Orders, Billing & Customer Finance) |
| `auditor` | `ACCOUNTANT_AUDITOR` | `Audit@2026!` | `/admin` | Read-only financial oversight — Centralized Audit Explorer, Reconciliation, Management Intelligence, Finance/AR/Profitability, Costing, GST Reports & Ledger |
| `owner` | `OWNER` | `Owner@2026!` | `/admin/intelligence` | Executive Management Intelligence Dashboard, KPI watchlists, profitability/AR oversight, IAM user governance & reconciliation correction approvals |

Follow the step-by-step **[10-Minute Live Demo Script](docs/phase11/final-demo-script.md)** to test all 19 integrated workflow steps and all 11 benchmark check values live.

---

## Running Automated QA Tests & Builds

> Automated tests run exclusively against the isolated **`ota_test`** database (`conftest.py` enforces `TEST_DATABASE_URL != DATABASE_URL`), never mutating `ota_dev`.

**Backend Lint & Full Pytest Suite (`62` tests across Phases 4–11):**
```bash
cd backend
uv run ruff check app tests
uv run pytest -v
```

**Frontend TypeScript Check & Production Bundle:**
```bash
cd frontend
npx tsc --noEmit
npm run build
```

---

## Implemented Capabilities (Phases 4–11)

- **Modular Monolith Backend & Role-Scoped UI:** 12 FastAPI domain modules (`iam`, `sales`, `orders`, `purchasing`, `inventory`, `production`, `billing`, `finance`, `costing`, `audit`, `reconciliation`, `intelligence`) sharing one ACID PostgreSQL 16 database, paired with mobile-first Salesman (`375px`) and desktop-first Factory Control Desk (`1280px`) interfaces.
- **PostgreSQL 16 Schema, Constraints & Triggers (`0001`–`0007`):** Integer-paisa (`BigInteger`) financial columns, `NUMERIC(18,3)` canonical base units (`g`, `ml`, `piece`, `packet`), `NUMERIC(18,6)` lot unit costs, `GENERATED ALWAYS AS` available-stock / invoice-total / receivable-outstanding columns, `ON DELETE RESTRICT` FKs, append-only immutability triggers (`fn_prevent_mutation()`), and atomic stock movement sync (`fn_sync_balance_from_movement()`).
- **Sales Orders, Customers & SKU Pricing (Phases 4–5, 11):** Lifecycle (`SUBMITTED -> UNDER_REVIEW -> CORRECTION_REQUESTED -> APPROVED -> INVOICED -> PARTIALLY_DISPATCHED -> DISPATCHED` + `REJECTED`/`CANCELLED`) with row-level `FOR UPDATE` locks, atomic FG stock reservation on approval, Customer Master creation (`POST /api/v1/sales/customers`), SKU price updates (`PATCH /api/v1/sales/products/{id}/price`), Salesman `Billed / Paid / Due` cards, and WhatsApp/Email invoice sharing.
- **Purchasing, GRNs & Single Stock Ledger (Phase 6):** Suppliers CRUD, multi-UOM RM/Packaging POs (`POs never mutate stock prior to GRN posting`), GRNs (`PURCHASE_IN` + FIFO `CostLot`), unified Stock Overview, CSV-exportable Stock Ledger & Reports, and dual-control Stock Adjustments.
- **BOM Versioning, Production Execution & Variance Audit (Phase 7):** Shared cooking recipes, multi-pack SKUs (`MRK-200G`, `MRK-500G`), immutable active BOM versions, Decimal scaling + ceiling carton rounding calculator, controlled production posting (`DRAFT -> POSTED`), dual yield/consumption/output-scaled variances (`BR-VAR-03`), and `audit.variance_alerts`.
- **GST Billing, Credit Notes & Dispatch Tracking (Phase 8):** Indian FY sequential numbering (`INV/YYYY-YY/NNNN`), validated Place-of-Supply GST (`CGST+SGST` vs `IGST`), deterministic single-page `%PDF-1.4` invoices, `INVOICE_CANCELLATION` & `SALES_RETURN` Credit Notes, partial & full dispatches (`DISPATCH_OUT`), POD delivery tracking, and 7-tab CSV-exportable Billing & GST Reports.
- **Payments, AR Ageing & FIFO Batch Costing (Phase 9):** Multi-mode receipts (`PMT/YYYY-YY/NNNN`) & `%PDF-1.4` receipts, split allocations, advances/refunds (`RFD/YYYY-YY/NNNN`), reversals, Credit Note unwind, strict `due_date`-based AR ageing & statements, FIFO batch costing (`₹30.90/pkt` with labour/power/monthly pools), CSV collections register export, and Gross Margin profitability.
- **Centralized Audit, Cross-Module Reconciliation & Executive Intelligence (Phase 10):** Centralized Audit Explorer (`REQ-` correlation refs, automatic credential redaction, CSV export), IAM `/iam/users` governance, Cross-Module Reconciliation Engine (`REC/YYYY-YY/NNNN`), and Management Intelligence Dashboard (`/admin/intelligence`).
- **Stretch Capabilities Implemented:** Batch & expiry tracking with **FEFO dispatch** (`CostLot.expiry_date` + `list_open_fg_lots_fefo_for_update`), **Reorder levels & low-stock alerts** (`Material.reorder_level_base` + Inventory/Intelligence alerts), and `localStorage` mobile order draft retention + UUID retry idempotency.

> **Scope & Known Boundaries:** Tabular reports export UTF-8 CSV and statutory Invoices/Receipts export `%PDF-1.4` (binary `.xlsx` omitted); external NIC e-Invoice portals, payment-gateway webhooks, non-production SG&A GL ledgers, and background Service Worker offline sync remain outside current scope. See [known-limitations.md](docs/phase11/known-limitations.md).

---

## Official Section 5 Benchmark Validation Summary

Verified simultaneously end-to-end inside [`test_phase11_integration_benchmark_security.py`](backend/tests/test_phase11_integration_benchmark_security.py):

| Check | Official Expected Value | Verified Outcome |
| --- | --- | --- |
| Flour Closing (`MAT-FLR`) | `120 kg` (`100 + 60 - 40`) | Exact match (`120000.000 g`) |
| Oil Closing (`MAT-OIL`) | `19.5 L` (`30 - 10.5`) | Exact match (`19500.000 ml`) |
| Packaging & Spice Closing | `306 pouches`, `21 cartons`, `3.8 kg spice` | Exact match |
| Finished Goods (`MRK-200G`) | `238 pkts` post-production -> `88 pkts` post-dispatch | Exact match |
| Yield Variance | `-6.00%` (Flagged) | Exact match (`is_flagged = True`) |
| Oil Consumption Variance | `+5.00%` (Flagged) | Exact match (`is_flagged = True`) |
| Retailer A Invoice (`INV/2026-27/0001`) | `₹7,875.00` (`₹7,500 + ₹187.50 CGST + ₹187.50 SGST`) | Exact match (`787500 paise`) |
| Retailer A Receivable After `₹4,000` | `₹3,875.00` (`PARTIALLY_PAID`) | Exact match (`387500 paise`) |
| Distributor B Shortage (`120` ordered vs `88` avail) | `32 pkts` shortage (approval blocked) | Exact match (`409 Conflict`) |
| Distributor B Inter-State Tax Rule | `5% IGST` (`CGST = 0`, `SGST = 0`) | Exact match (`INTER_STATE`) |
| Batch Production Cost (`PRD-001`) | `₹30.90/pkt` (`₹5,810.00 / 188 pkts`) | Exact match (`3090 paise/pkt`) |

---

## Cloud Deployment Artifacts (Render + Vercel)

- **Backend + PostgreSQL 16 Blueprint:** [`render.yaml`](render.yaml) & [`backend/Dockerfile`](backend/Dockerfile) (supports `$PORT`, locked `uv.lock` install, auto `alembic upgrade head`, `production_bootstrap.py`, optional `benchmark_seed.py`, `postgres://`/`postgresql://` URL normalization).
- **Frontend SPA Configuration:** [`frontend/vercel.json`](frontend/vercel.json) (Vercel root directory `frontend`, `npm run build` -> `dist`, env `VITE_API_BASE_URL=https://<your-backend>.onrender.com/api/v1`).
- **Container Production Compose:** [`docker-compose.prod.yml`](docker-compose.prod.yml), [`frontend/Dockerfile.prod`](frontend/Dockerfile.prod), [`frontend/nginx.conf`](frontend/nginx.conf). See [`docs/phase11/deployment-guide.md`](docs/phase11/deployment-guide.md).

---

## Repository Structure

```text
├── Problem Statement - Winter Internship Application - 2026.docx
├── .gitignore
├── .env.example
├── docker-compose.yml                 # Local development stack (PostgreSQL + Backend + Frontend)
├── docker-compose.prod.yml            # Multi-stage Nginx + FastAPI + PostgreSQL production stack
├── render.yaml                        # Render Blueprint (PostgreSQL 16 + FastAPI Web Service)
├── infrastructure/
│   └── postgres/init/
│       └── 01-create-test-db.sql      # Creates isolated ota_test database in Docker
├── docs/
│   ├── phase1/ ... phase10/           # Discovery, ER model, schema & per-phase technical docs
│   └── phase11/                       # Final requirement matrix, QA, benchmark, security, perf & manuals
├── backend/
│   ├── alembic/                       # Migrations 0001 -> 0007_phase10_audit_recon
│   ├── app/
│   │   ├── core/                      # Config, PostgreSQL session, exceptions, logging, security
│   │   ├── modules/                   # iam, sales, orders, purchasing, inventory, production,
│   │   │                              # billing, finance, costing, audit, reconciliation, intelligence
│   │   └── seeds/
│   │       ├── benchmark_seed.py      # Official Section 5 master data, users & opening stock
│   │       ├── production_bootstrap.py# Production-safe company/roles/UOMs + optional initial admin
│   │       └── dev_fixtures.py        # Optional controlled dev FG stock helper
│   └── tests/                         # 62 automated Pytest tests against isolated ota_test DB
└── frontend/
    ├── Dockerfile.prod                # Multi-stage Vite build -> Nginx 1.27 + /api/ proxy
    ├── nginx.conf                     # Security headers & SPA fallback configuration
    ├── vercel.json                    # Vercel SPA rewrite configuration
    └── src/
        ├── lib/                       # API client, money & unit formatters, auth context
        ├── components/                # UI primitives, StatusBadge, mobile & desktop layouts
        └── pages/                     # Login, Salesman mobile pages, Admin Control Desk
```

---

## Detailed Documentation

- **Phase 11 Final Submission Docs (`docs/phase11/`):**
  - [final-requirement-matrix.md](docs/phase11/final-requirement-matrix.md)
  - [system-integration-report.md](docs/phase11/system-integration-report.md)
  - [benchmark-validation-report.md](docs/phase11/benchmark-validation-report.md)
  - [end-to-end-testing-report.md](docs/phase11/end-to-end-testing-report.md)
  - [security-testing-report.md](docs/phase11/security-testing-report.md)
  - [performance-testing-report.md](docs/phase11/performance-testing-report.md)
  - [installation-guide.md](docs/phase11/installation-guide.md)
  - [deployment-guide.md](docs/phase11/deployment-guide.md)
  - [user-manual.md](docs/phase11/user-manual.md)
  - [administrator-manual.md](docs/phase11/administrator-manual.md)
  - [known-limitations.md](docs/phase11/known-limitations.md)
  - [final-project-report.md](docs/phase11/final-project-report.md)
  - [final-demo-script.md](docs/phase11/final-demo-script.md)
- **Earlier Phase Directories:** [Phase 1](docs/phase1) · [Phase 2](docs/phase2) · [Phase 3](docs/phase3) · [Phase 4](docs/phase4) · [Phase 5](docs/phase5) · [Phase 6](docs/phase6) · [Phase 7](docs/phase7) · [Phase 8](docs/phase8) · [Phase 9](docs/phase9) · [Phase 10](docs/phase10)
  - **Phase 6 Docs (`docs/phase6/`):** [supplier-management.md](docs/phase6/supplier-management.md) · [purchase-workflow.md](docs/phase6/purchase-workflow.md) · [goods-receipt-workflow.md](docs/phase6/goods-receipt-workflow.md) · [inventory-ledger.md](docs/phase6/inventory-ledger.md) · [stock-balance-management.md](docs/phase6/stock-balance-management.md) · [unit-management.md](docs/phase6/unit-management.md) · [stock-adjustments.md](docs/phase6/stock-adjustments.md) · [inventory-dashboard.md](docs/phase6/inventory-dashboard.md) · [api-documentation.md](docs/phase6/api-documentation.md) · [testing-report.md](docs/phase6/testing-report.md) · [benchmark-validation.md](docs/phase6/benchmark-validation.md) · [known-limitations.md](docs/phase6/known-limitations.md)
  - **Phase 7 Docs (`docs/phase7/`):** [production-management-overview.md](docs/phase7/production-management-overview.md) · [bom-management.md](docs/phase7/bom-management.md) · [bom-versioning.md](docs/phase7/bom-versioning.md) · [bom-calculation-engine.md](docs/phase7/bom-calculation-engine.md) · [production-planning.md](docs/phase7/production-planning.md) · [material-issue-workflow.md](docs/phase7/material-issue-workflow.md) · [production-execution.md](docs/phase7/production-execution.md) · [quality-and-output-recording.md](docs/phase7/quality-and-output-recording.md) · [production-posting.md](docs/phase7/production-posting.md) · [variance-analysis.md](docs/phase7/variance-analysis.md) · [inventory-integration.md](docs/phase7/inventory-integration.md) · [api-documentation.md](docs/phase7/api-documentation.md) · [testing-report.md](docs/phase7/testing-report.md) · [benchmark-validation.md](docs/phase7/benchmark-validation.md) · [known-limitations.md](docs/phase7/known-limitations.md)
  - **Phase 8 Docs (`docs/phase8/`):** [billing-overview.md](docs/phase8/billing-overview.md) · [invoice-generation.md](docs/phase8/invoice-generation.md) · [gst-calculation-engine.md](docs/phase8/gst-calculation-engine.md) · [place-of-supply-rules.md](docs/phase8/place-of-supply-rules.md) · [invoice-lifecycle.md](docs/phase8/invoice-lifecycle.md) · [invoice-numbering.md](docs/phase8/invoice-numbering.md) · [invoice-pdf-generation.md](docs/phase8/invoice-pdf-generation.md) · [credit-note-management.md](docs/phase8/credit-note-management.md) · [dispatch-management.md](docs/phase8/dispatch-management.md) · [partial-dispatch.md](docs/phase8/partial-dispatch.md) · [delivery-tracking.md](docs/phase8/delivery-tracking.md) · [inventory-integration.md](docs/phase8/inventory-integration.md) · [api-documentation.md](docs/phase8/api-documentation.md) · [testing-report.md](docs/phase8/testing-report.md) · [benchmark-validation.md](docs/phase8/benchmark-validation.md) · [known-limitations.md](docs/phase8/known-limitations.md)
  - **Phase 9 Docs (`docs/phase9/`):** [phase9-overview.md](docs/phase9/phase9-overview.md) · [payment-workflow.md](docs/phase9/payment-workflow.md) · [invoice-allocation.md](docs/phase9/invoice-allocation.md) · [receivables-management.md](docs/phase9/receivables-management.md) · [costing-methodology.md](docs/phase9/costing-methodology.md) · [profitability-calculations.md](docs/phase9/profitability-calculations.md) · [database-changes.md](docs/phase9/database-changes.md) · [api-documentation.md](docs/phase9/api-documentation.md) · [testing-report.md](docs/phase9/testing-report.md)
  - **Phase 10 Docs (`docs/phase10/`):** [phase10-overview.md](docs/phase10/phase10-overview.md) · [audit-architecture.md](docs/phase10/audit-architecture.md) · [audit-event-catalog.md](docs/phase10/audit-event-catalog.md) · [inventory-reconciliation.md](docs/phase10/inventory-reconciliation.md) · [financial-reconciliation.md](docs/phase10/financial-reconciliation.md) · [production-reconciliation.md](docs/phase10/production-reconciliation.md) · [discrepancy-resolution.md](docs/phase10/discrepancy-resolution.md) · [management-dashboard.md](docs/phase10/management-dashboard.md) · [database-changes.md](docs/phase10/database-changes.md) · [api-documentation.md](docs/phase10/api-documentation.md) · [testing-report.md](docs/phase10/testing-report.md)
#   o t a _ t a s k  
 