# Production Deployment Guide — Order-to-Audit ERP

This guide documents production containerization, configuration safety gates, reverse proxying, migrations, health monitoring, and backup procedures without storing plaintext secrets in source control.

---

## 1. Production Architecture (`docker-compose.prod.yml`)

```text
Internet / TLS Reverse Proxy (Host Caddy / Cloud ALB / Cloudflare)
        │ HTTPS (443) -> HTTP (APP_HTTP_PORT, default 80)
        ▼
[frontend] nginx:1.27-alpine (frontend/Dockerfile.prod + frontend/nginx.conf)
  ├── Static React/Vite bundle (/usr/share/nginx/html) + SPA try_files fallback
  ├── Security headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy)
  └── /api/* reverse proxy ──▶ http://backend:8000/api/
                                    │
                                    ▼
[backend] python:3.12-slim + uvicorn (2 workers, port 8000)
  ├── Startup: alembic upgrade head -> uvicorn app.main:app
  ├── Fails fast if ENVIRONMENT=production with ENABLE_DEV_SEED=true
  │   or weak/dev JWT_SECRET_KEY (validate_production_safety())
  └── Healthcheck: GET /api/v1/health
                                    │
                                    ▼
[postgres] postgres:16-alpine (persistent named volume: ota_pgdata_prod)
```

- Deployment definitions: [`docker-compose.prod.yml`](file:///d:/mac/ota/docker-compose.prod.yml), [`frontend/Dockerfile.prod`](file:///d:/mac/ota/frontend/Dockerfile.prod), [`frontend/nginx.conf`](file:///d:/mac/ota/frontend/nginx.conf), [`backend/Dockerfile`](file:///d:/mac/ota/backend/Dockerfile).

> [!NOTE]
> Local workstation verification executed `npx tsc --noEmit` and `vite build` directly (`0` errors) and statically audited all Docker/Nginx configs. Live `docker compose -f docker-compose.prod.yml up --build -d` container execution requires an active Docker Engine / Compose daemon, which was unavailable on the local Windows test host during final QA.

---

## 2. Required Production Environment Variables (`.env.prod`)

Create a host-only `.env.prod` file (chmod `600`, **never** committed to Git):

```ini
POSTGRES_USER=ota_prod_user
POSTGRES_PASSWORD=<generate-strong-32-byte-secret>
POSTGRES_DB=ota_prod
POSTGRES_TEST_DB=ota_test_unused
JWT_SECRET_KEY=<openssl rand -hex 32>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480
CORS_ORIGINS=["https://erp.yourdomain.com"]
APP_HTTP_PORT=8080
LOG_LEVEL=INFO
```

Security safeguards enforced by [`backend/app/core/config.py`](file:///d:/mac/ota/backend/app/core/config.py):
- `ENVIRONMENT=production` requires `ENABLE_DEV_SEED=false` (`docker-compose.prod.yml` hardcodes `"false"`).
- `JWT_SECRET_KEY` must be `>= 32` characters and cannot contain `"dev_only"`.
- Sample dev passwords (`SalesA@2026!`, `Admin@2026!`, etc.) are **never** seeded when `ENABLE_DEV_SEED=false`.

---

## 3. Build, Migrate & Launch Commands

```bash
# Build & launch production stack cleanly
docker compose --env-file .env.prod -f docker-compose.prod.yml up --build -d

# Verify health checks
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
curl -fsS http://127.0.0.1:${APP_HTTP_PORT:-80}/api/v1/health
```

Expected health payload:
```json
{"status": "ok", "database": "connected", "environment": "production"}
```

---

## 4. Initial Production Master Setup (Without Dev Passwords)

When deploying cleanly to production (`ENABLE_DEV_SEED=false`):
1. Bootstrap only `iam.roles`, `iam.company_profiles`, units (`production.unit_conversions`), and initial `OWNER` / `FACTORY_ADMIN` account with a freshly salted Argon2id hash generated out-of-band.
2. Never run `benchmark_seed.py` in production unless demonstrating in an isolated training environment with `ENABLE_DEV_SEED=true`.

---

## 5. TLS Termination, Backups & Recovery

1. **TLS Termination:** Bind `APP_HTTP_PORT` to `127.0.0.1:8080` and terminate TLS (Let's Encrypt via Caddy / Nginx / AWS ALB) forwarding HTTPS `443 -> 127.0.0.1:8080`. Ensure `CORS_ORIGINS` matches exact `https://` origin.
2. **Nightly Logical Backups:**
   ```bash
   docker exec ota-postgres-prod pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "/backups/ota_prod_$(date +%F_%H%M).dump"
   ```
3. **Recovery Drill:**
   ```bash
   pg_restore -U "$POSTGRES_USER" -d ota_staging_restore --clean --if-exists /backups/ota_prod_YYYY-MM-DD_HHMM.dump
   ```
4. **Migration Upgrade Safety:** Always take a pre-upgrade `pg_dump` before running `alembic upgrade head`.
