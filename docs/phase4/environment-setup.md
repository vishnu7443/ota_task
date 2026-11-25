# Environment & Development Setup

## 1. Environment Variables

Copy `.env.example` to `.env` (and `backend/.env.example` to `backend/.env` when running backend directly outside Docker):

| Variable | Default (Dev) | Purpose |
| --- | --- | --- |
| `POSTGRES_USER` | `ota_admin` | PostgreSQL superuser/owner for local containers |
| `POSTGRES_PASSWORD` | `ota_dev_password` | Development DB password (change outside dev) |
| `POSTGRES_DB` | `ota_dev` | Main runtime database |
| `POSTGRES_TEST_DB` | `ota_test` | Isolated test database for `pytest` |
| `DATABASE_URL` | `postgresql+psycopg://...@localhost:5432/ota_dev` | SQLAlchemy runtime connection string |
| `TEST_DATABASE_URL` | `postgresql+psycopg://...@localhost:5432/ota_test` | Isolated Pytest connection string (must differ from `DATABASE_URL`) |
| `JWT_SECRET_KEY` | `dev_only_secret_key_change_in_production_32chars` | HS256 signing secret (blocked in `ENVIRONMENT=production` if left default) |
| `CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | Allowed frontend origins |
| `ENABLE_DEV_SEED` | `true` | Allows `benchmark_seed.py` execution (`false` mandatory in production) |
| `VITE_API_BASE_URL` | `http://localhost:8000/api/v1` | Frontend API base URL |

---

## 2. Running via Docker Compose (Full Stack)

```bash
cp .env.example .env
docker compose up --build -d
```

- PostgreSQL (`postgres:16-alpine`) initializes both `ota_dev` and `ota_test` via `infrastructure/postgres/init/01-create-test-db.sql`.
- Backend container runs `alembic upgrade head`, seeds benchmark data (`app.seeds.benchmark_seed`), and serves FastAPI at `http://localhost:8000` (`/api/v1/docs` for OpenAPI).
- Frontend container serves Vite React at `http://localhost:5173`.

---

## 3. Running Locally (PostgreSQL in Docker + Local Backend/Frontend)

```bash
# 1. Start PostgreSQL container only
docker compose up -d postgres

# 2. Backend migrations, seed & server
cd backend
cp .env.example .env
uv sync --python 3.12
uv run alembic upgrade head
uv run python -m app.seeds.benchmark_seed
uv run uvicorn app.main:app --reload --port 8000

# 3. Frontend dev server
cd ../frontend
npm install
npm run dev
```

## 4. Running Automated Tests

```bash
cd backend
uv run pytest -v
```
`tests/conftest.py` enforces `TEST_DATABASE_URL != DATABASE_URL`, upgrades `ota_test` cleanly via Alembic, truncates & re-seeds before each test, and never touches `ota_dev`.
