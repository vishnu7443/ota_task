# Order-to-Audit Management System (`Kaveri Traditional Snacks Pvt. Ltd.`)

Independent implementation for the **NIT Tiruchirappalli Centre for Digital Infrastructure (CDI) Winter Internship 2026** problem statement.

All company, customer, product, and transaction records are strictly fictional benchmark/test data derived from the problem specification and approved Phase 1–3 architecture baselines.

---

## Current Status: Phase 7 — Bill of Materials & Production Management

Implemented and verified across Phases 4, 5, 6, and 7:
- **Modular Monolith Backend & Role-Scoped UI:** Backend modules (`iam`, `sales`, `orders`, `purchasing`, `inventory`, `production`, `audit`) cleanly layered across FastAPI routers, Pydantic schemas, state guards, services, repositories, and SQLAlchemy 2.0 models, paired with mobile-first Salesman (`375px`) and desktop-first Factory Control Desk (`1280px`) interfaces.
- **PostgreSQL 16 Schema, Constraints & Triggers (`0001`, `0002`, `0003`, `0004`):**
  - Integer-paisa financial columns, `NUMERIC(18,3)` canonical base quantities (`g`, `ml`, `piece`, `packet`), `NUMERIC(18,6)` sub-paisa FIFO unit costs, `GENERATED ALWAYS AS` available-stock columns, `ON DELETE RESTRICT` foreign keys, append-only ledger/audit triggers (`fn_prevent_mutation()`), immutable active/superseded BOM triggers (`trg_bom_version_immutability`, `trg_bom_component_immutability`), and atomic movement-to-balance trigger (`fn_sync_balance_from_movement()`).
- **Sales Order Management & Stock Reservation (Phases 4–5):**
  - Enforced lifecycle across `SUBMITTED`, `UNDER_REVIEW`, `CORRECTION_REQUESTED`, `APPROVED`, `REJECTED`, and `CANCELLED` with row-level `FOR UPDATE` locks and `version` checks.
  - Atomic stock reservation upon `APPROVED` (`available = on_hand - reserved`) protecting sales commitments against concurrent overselling or negative stock adjustments.
- **Purchasing, Goods Receipts & Immutable Stock Ledger (Phase 6):**
  - **Suppliers (`purchasing.suppliers`):** CRUD, GSTIN/state-code validation, active toggle, and chronological PO/GRN purchase history.
  - **Purchase Orders (`purchasing.purchase_orders`):** Multi-line Raw Material & Packaging POs across dimension-compatible units with GST/subtotal calculation; strict rule that POs do not mutate inventory before posting.
  - **Goods Receipts (`purchasing.purchase_receipts`):** Approved/Partial PO fulfillment tracking, `client_receipt_id` idempotency, Received vs Damaged/Rejected split, excess-receipt guard, and `DRAFT -> SUBMITTED -> VERIFIED -> POSTED` workflow writing `PURCHASE_IN` movements and FIFO `CostLot` layers.
  - **Inventory & Adjustments (`inventory.*`):** Unified Stock Dashboard (`Opening`, `Received`, `Issued`, `Dispatched`, `Adjusted`, `Physical`, `Reserved`, `Available`, Low-Stock Alerts), chronological Ledger viewer, dual-control Stock Adjustments (Supervisor requests `PENDING_APPROVAL`, Admin approves/posts with negative-stock & sales-reservation protection), and CSV-exportable Stock Reports.
- **Bill of Materials, Production Execution, Atomic Posting & Variance Audit (Phase 7):**
  - **Extensible Product/BOM Versioning (`production.recipe_templates`, `bom_headers`, `bom_versions`, `bom_components`):** Shared cooking recipe templates (`RCP-MRK-BASE`), multiple pack sizes per product (`MRK-200G`, `MRK-500G`), editable `DRAFT` BOM versions, atomic `ACTIVE -> SUPERSEDED` promotion, and trigger-enforced immutability of historical/active BOM versions.
  - **BOM Scaling Calculator & Availability Engine:** Exact Decimal scaling by `batch_multiplier` or `target_output_pkts`, explicit metric conversions (`kg <-> g`, `L <-> ml`), ceiling rounding (`math.ceil`) for indivisible cartons/pouches with shortfall indicators against `available_qty_base`.
  - **Controlled Production Lifecycle (`DRAFT -> PLANNED -> IN_PROGRESS -> COMPLETED -> POSTED` + `CANCELLED`):** Deterministic `BomVersion` pinning, double-issue prevention (`409 DOUBLE_MATERIAL_ISSUE`), FIFO `CostLot` issuance (`PROD_ISSUE_OUT` + `cost_lot_consumptions`), clean separation of `good_qty_pkts` vs `rejected_qty_pkts` vs `damaged_packaging_qty`, atomic posting (`PROD_OUTPUT_IN`, `PACKAGING_DAMAGE_OUT`, `PROD_RETURN_IN`), dual yield/raw/output-scaled variance computation (`BR-VAR-03`), `audit.variance_alerts`, and end-to-end ledger traceability.

> **Scope Boundary (Stop After Phase 7):** Step 8 Final Costing (Labour / Gas-Power / Overhead Allocation), GST Tax Invoicing, Dispatches (physical FG deduction), and Customer Payments/Receivables remain deferred cleanly until the next phases.

---

## Repository Structure

```text
├── Problem Statement - Winter Internship Application - 2026.docx
├── .gitignore
├── .env.example
├── docker-compose.yml
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
│   └── phase7/                        # Phase 7 BOM & production docs (15 docs)
├── backend/
│   ├── alembic/                       # 0001 -> 0002 -> 0003 -> 0004_phase7_bom_production
│   ├── app/
│   │   ├── core/                      # Config, PostgreSQL session, exceptions, logging, security
│   │   ├── modules/
│   │   │   ├── iam/                   # Roles, users, login/me endpoints, RBAC guards
│   │   │   ├── sales/                 # Salesmen, customers, products, pack sizes, price lists
│   │   │   ├── orders/                # State machine, submission, verification, audit queries
│   │   │   ├── purchasing/            # Suppliers, Purchase Orders, Goods Receipts & QC posting
│   │   │   ├── inventory/             # Materials, UOMs, CostLots, Ledger, Adjustments & Reports
│   │   │   ├── production/            # BOM versioning, BOM calculator, runs, execution, posting & variances
│   │   │   └── audit/                 # Append-only audit log service & variance alerts
│   │   └── seeds/
│   │       ├── benchmark_seed.py      # Official Section 5 master, RM/Pkg/FG opening stock, SUP-001 & MRK-200G BOM v1
│   │       └── dev_fixtures.py        # Optional separate controlled dev stock fixture helper
│   └── tests/                         # 41 automated Pytest tests against isolated ota_test DB
└── frontend/
    └── src/
        ├── lib/                       # API client, money & unit formatters, auth context
        ├── components/                # UI primitives, StatusBadge, mobile & desktop layouts
        └── pages/                     # Login, Salesman mobile pages, Admin Order/Purchasing/Inventory/BOM/Production pages
```

---

## Technology Stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, Psycopg 3, `pwdlib` (Argon2id), `PyJWT`, Pytest, Ruff
- **Database:** PostgreSQL 16
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS, shadcn/ui primitives, Lucide React, React Router, TanStack Query
- **Infrastructure:** Docker, Docker Compose, `.env`-based configuration

---

## Quick Start

### Option A: Docker Compose

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

*(Optional separate dev fixture to test full 150-pkt approval locally without altering benchmark seed or fabricating production output: `uv run python -m app.seeds.dev_fixtures --add-pkts 150`.)*

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

---

## Verification & Automated Tests

**Backend Lint & Pytest (41 tests executed against isolated `ota_test`, never mutating `ota_dev`):**

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
| `salesman_a` | `SALESMAN` | `SalesA@2026!` | Mobile Salesman (`/salesman`) — assigned `Retailer A` |
| `salesman_b` | `SALESMAN` | `SalesB@2026!` | Mobile Salesman (`/salesman`) — assigned `Distributor B` |
| `admin` | `FACTORY_ADMIN` | `Admin@2026!` | Desktop Control Desk (`/admin`) — Sales, Purchasing, Inventory, BOM & Production |
| `supervisor` | `PRODUCTION_SUPERVISOR` | `Prod@2026!` | BOM, Production, Purchasing & Inventory (blocked `403` on Sales Orders) |
| `auditor` | `ACCOUNTANT_AUDITOR` | `Audit@2026!` | Desktop read-only oversight, Ledger, Variances, Reports & Audit Trail |
| `owner` | `OWNER` | `Owner@2026!` | Desktop read-only executive oversight, Variances (can acknowledge alerts), Reports & Audit Trail |

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
