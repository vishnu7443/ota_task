# Installation Guide — Order-to-Audit Management System (`Kaveri Traditional Snacks Pvt. Ltd.`)

This guide covers full local installation from a clean workstation (Windows PowerShell or Linux/macOS bash) for development and verification without modifying seeded production defaults.

---

## 1. Prerequisites

| Component | Version | Purpose |
| --- | --- | --- |
| Python | `>= 3.12` | FastAPI backend (`pyproject.toml`) |
| `uv` | Latest | Python virtualenv & lockfile package manager |
| Node.js & npm | Node `>= 20` | Vite + React 19 + TypeScript frontend |
| PostgreSQL | `16` | Primary operational + isolated test databases (`ota_dev`, `ota_test`) |
| Docker & Docker Compose (optional) | Latest | Containerized PostgreSQL / dev / production stack |

---

## 2. Database Setup (PostgreSQL 16)

Ensure PostgreSQL 16 listens on `localhost:5432` and create the role plus separate development and test databases:

```sql
CREATE ROLE ota_admin WITH LOGIN PASSWORD 'ota_dev_password' CREATEDB SUPERUSER;
CREATE DATABASE ota_dev OWNER ota_admin ENCODING 'UTF8';
CREATE DATABASE ota_test OWNER ota_admin ENCODING 'UTF8';
```

> [!IMPORTANT]
> `conftest.py` enforces `TEST_DATABASE_URL != DATABASE_URL`. Never run automated tests against `ota_dev`.

If using Docker solely for PostgreSQL:

```bash
cp .env.example .env
docker compose up -d db
```

[`infrastructure/postgres/init/01-create-test-db.sql`](file:///d:/mac/ota/infrastructure/postgres/init/01-create-test-db.sql) initializes the isolated `ota_test` database automatically inside the container.

---

## 3. Environment Configuration

Copy the template without committing real secrets:

```bash
cp .env.example .env
```

Default local development variables documented in [`.env.example`](file:///d:/mac/ota/.env.example):

```ini
APP_NAME=Kaveri Snacks Order-to-Audit ERP
ENVIRONMENT=development
ENABLE_DEV_SEED=true
DATABASE_URL=postgresql+psycopg://ota_admin:ota_dev_password@localhost:5432/ota_dev
TEST_DATABASE_URL=postgresql+psycopg://ota_admin:ota_dev_password@localhost:5432/ota_test
JWT_SECRET_KEY=replace_with_32_plus_char_secret_for_dev_only
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480
```

> [!WARNING]
> In [`backend/app/core/config.py`](file:///d:/mac/ota/backend/app/core/config.py), `validate_production_safety()` rejects `ENVIRONMENT=production` if `ENABLE_DEV_SEED=true` or if `JWT_SECRET_KEY` is shorter than 32 chars or contains `"dev_only"`.

---

## 4. Backend Installation, Migrations & Seeding

```bash
cd backend
uv sync --python 3.12
uv run alembic upgrade head
uv run python -m app.seeds.benchmark_seed
```

### Seeded Benchmark Baseline (`app.seeds.benchmark_seed`)
- **Company Profile:** `Kaveri Traditional Snacks Pvt. Ltd.`, State `Tamil Nadu (33)`, GSTIN `33AABCK1234F1Z5`.
- **Customers:** `CUST-RET-A` (Tamil Nadu `33`, B2B GSTIN `33AAACR9999K1Z2`, assigned to `salesman_a`), `CUST-DIST-B` (Karnataka `29`, B2B GSTIN `29AAACD8888M1Z9`, assigned to `salesman_b`).
- **Finished SKU:** `MRK-200G` (`Murukku 200 g`, HSN `21069099`, 5% GST, ₹50.00/pkt, opening FG `50 pkts` @ ₹28.85/pkt).
- **Raw & Packaging Stock:** `MAT-FLR` (`100 kg` @ ₹42/kg), `MAT-OIL` (`30 L` @ ₹140/L), `MAT-SPC` (`5 kg` @ ₹200/kg), `MAT-PCH-200` (`500 pcs` @ ₹2.50), `MAT-CTN-20` (`30 pcs` @ ₹15).
- **Supplier & BOM:** `SUP-001` (`Cauvery Agro Mills`, TN `33`), active `MRK-200G` BOM v1 (200-pkt batch template).
- *(Optional dev testing helper)* Add 150 FG packets without altering benchmark production history: `uv run python -m app.seeds.dev_fixtures --add-pkts 150`.

Start FastAPI:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

API health & interactive Swagger UI:
- Health check: `http://127.0.0.1:8000/api/v1/health`
- Swagger UI: `http://127.0.0.1:8000/api/v1/docs`

---

## 5. Frontend Installation & Startup

```bash
cd frontend
npm install
npm run dev
```

Frontend serves at `http://127.0.0.1:5173` (with Vite `/api` proxy or `VITE_API_BASE_URL` pointing to `http://127.0.0.1:8000/api/v1`).

---

## 6. Verification Commands After Installation

**Backend Lint & Test Suite (against isolated `ota_test`):**
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
