# Order-to-Audit Management System (`Kaveri Traditional Snacks Pvt. Ltd.`)

Independent implementation for the **NIT Tiruchirappalli Centre for Digital Infrastructure (CDI) Winter Internship 2026** problem statement.

All company, customer, product, and transaction records are strictly fictional benchmark/test data derived from the problem specification and approved Phase 1–3 architecture baselines.

---

## Current Status: Phase 5 — Complete Sales Order Lifecycle & Admin Verification

Implemented and verified across Phases 4 and 5:
- **Monorepo & Modular Monolith Architecture:** Backend modules (`iam`, `sales`, `orders`, `inventory`, `audit`) cleanly split across routers, schemas, state machine, services, repositories, and SQLAlchemy models; paired with mobile-first Salesman (`375px`) and desktop-first Factory Admin (`1280px`) React interfaces.
- **PostgreSQL 16 Schema, Constraints & Triggers (`0001` & `0002`):**
  - Integer-paisa financial columns, `GENERATED ALWAYS AS` computed taxable & available-stock columns, `ON DELETE RESTRICT` foreign keys, append-only ledger/audit triggers (`fn_prevent_mutation()`), ledger-to-balance trigger (`fn_sync_balance_from_movement()`), no-op transition guard (`from_status IS DISTINCT FROM to_status`), and per-item `inventory.stock_reservations`.
- **Explicit Order Lifecycle & Concurrency Controls:**
  - Enforced transitions across `SUBMITTED`, `UNDER_REVIEW`, `CORRECTION_REQUESTED`, `APPROVED`, `REJECTED`, and `CANCELLED` using row-level `SELECT ... FOR UPDATE` locks and `version` checks.
  - Atomic stock reservation upon `APPROVED` (`available = on_hand - reserved`) without deducting physical warehouse stock until future Dispatch; pre-invoice cancellation releases reservations cleanly.
  - Non-blocking read-only stock warnings on mobile submission; blocking `409 INSUFFICIENT_STOCK` protection against negative stock or concurrent overselling on Admin approval.
- **Factory Admin Verification Desk:**
  - Dashboard KPI summary (`GET /api/v1/admin/orders/summary`), lifecycle tabs (`Pending Verification`, `Incoming`, `Approved`, `Rejected`, `All`), multi-criteria search/filters (order #, customer, salesman, date range, status, shortage), pagination, and 10s polling.
  - Interactive verification workbench to inspect customer/salesman/stock breakdown, adjust quantities & authorized unit prices with mandatory audit reasons (preserving immutable originals), mark Under Review, request Salesman correction, Approve & Reserve, Reject, or Cancel pre-invoice.
- **Salesman Mobile Experience & Synchronization:**
  - Sub-minute customer -> SKU -> carton/packet cart submission with `client_order_id` idempotency.
  - My Orders tracking (`All`, `Submitted`, `Under Review`, `Correction`, `Approved`, `Rejected`, `Cancelled`) and rich Order Details displaying Admin remarks, rejection/cancellation reasons, original vs approved quantities, status timeline, 10s polling sync, inline correction resubmission (`PUT /orders/{id}`), and pre-approval cancellation.
- **Immutable Audit Trail:** Every order submission, quantity/price override, status transition, remark, stock reservation, reservation release, and RBAC denial is recorded with actor, role, timestamp, reason, and before/after JSON snapshots.

> **Scope Boundary (Stop After Phase 5):** GST Tax Invoices, Dispatches (physical FG deduction), Customer Payments/Receivables, Production Runs, BOMs, and Costing are intentionally excluded until the next phase.

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
│   └── phase5/                        # Phase 5 lifecycle, verification & audit docs (9 docs)
├── backend/
│   ├── alembic/                       # 0001_phase4_foundation -> 0002_phase5_order_lifecycle
│   ├── app/
│   │   ├── core/                      # Config, PostgreSQL session, exceptions, logging, security
│   │   ├── modules/
│   │   │   ├── iam/                   # Roles, users, login/me endpoints, RBAC guards
│   │   │   ├── sales/                 # Salesmen, customers, products, pack sizes, price lists
│   │   │   ├── orders/                # State machine, submission, verification, audit queries
│   │   │   ├── inventory/             # Opening balance ledger, balances & stock_reservations
│   │   │   └── audit/                 # Append-only audit log service
│   │   └── seeds/
│   │       ├── benchmark_seed.py      # Official Section 5 master & 50-pkt opening FG seed
│   │       └── dev_fixtures.py        # Optional separate controlled dev stock fixture helper
│   └── tests/                         # 24 automated Pytest tests against isolated ota_test DB
└── frontend/
    └── src/
        ├── lib/                       # API client, money formatter, auth context
        ├── components/                # UI primitives, StatusBadge, mobile & desktop layouts
        └── pages/                     # Login, Salesman mobile pages, Admin verification pages
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

**Backend Lint & Pytest (24 tests executed against isolated `ota_test`, never mutating `ota_dev`):**

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
| `admin` | `FACTORY_ADMIN` | `Admin@2026!` | Desktop Admin (`/admin`) — full order verification controls |
| `supervisor` | `PRODUCTION_SUPERVISOR` | `Prod@2026!` | Floor scope (Phase 6 production; blocked `403` on orders) |
| `auditor` | `ACCOUNTANT_AUDITOR` | `Audit@2026!` | Desktop read-only oversight + Audit Trail view |
| `owner` | `OWNER` | `Owner@2026!` | Desktop read-only oversight + Audit Trail view |

---

## Detailed Documentation

- **Phase 4 Foundation Docs:** [docs/phase4/](file:///d:/mac/ota/docs/phase4)
- **Phase 5 Order Management Docs:**
  - [order-management-overview.md](file:///d:/mac/ota/docs/phase5/order-management-overview.md)
  - [order-state-transitions.md](file:///d:/mac/ota/docs/phase5/order-state-transitions.md)
  - [admin-verification-workflow.md](file:///d:/mac/ota/docs/phase5/admin-verification-workflow.md)
  - [stock-availability-design.md](file:///d:/mac/ota/docs/phase5/stock-availability-design.md)
  - [salesman-order-tracking.md](file:///d:/mac/ota/docs/phase5/salesman-order-tracking.md)
  - [audit-trail-implementation.md](file:///d:/mac/ota/docs/phase5/audit-trail-implementation.md)
  - [api-documentation.md](file:///d:/mac/ota/docs/phase5/api-documentation.md)
  - [testing-report.md](file:///d:/mac/ota/docs/phase5/testing-report.md)
  - [known-limitations.md](file:///d:/mac/ota/docs/phase5/known-limitations.md)
