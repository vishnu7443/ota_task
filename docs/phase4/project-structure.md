# Project Structure

```
d:\mac\ota\
├── Problem Statement - Winter Internship Application - 2026.docx
├── .gitignore
├── .env.example
├── docker-compose.yml
├── README.md
├── docs/
│   ├── phase1/                         # Business discovery & requirements (10 docs)
│   ├── phase2/                         # DDD & system architecture (14 docs)
│   ├── phase3/                         # PostgreSQL physical engineering (12 docs)
│   └── phase4/                         # Phase 4 implementation docs (9 docs)
├── infrastructure/
│   └── postgres/init/
│       └── 01-create-test-db.sql      # Creates separate `ota_test` database
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── Dockerfile
│   ├── .env.example
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_phase4_foundation_and_orders.py
│   ├── app/
│   │   ├── main.py                     # FastAPI entry point, CORS, request logging, health check
│   │   ├── core/
│   │   │   ├── config.py               # Pydantic BaseSettings & production safety validator
│   │   │   ├── database.py             # SQLAlchemy 2.0 engine, Base naming convention, SessionLocal
│   │   │   ├── exceptions.py           # Typed domain exceptions + global handlers
│   │   │   ├── logging.py              # Structured JSON logging
│   │   │   └── security.py             # Argon2id password hashing + HS256 JWT tokens
│   │   ├── modules/
│   │   │   ├── iam/                    # Identity, roles, authentication & RBAC dependencies
│   │   │   ├── sales/                  # Customers, products, pack sizes, authoritative price lists
│   │   │   ├── orders/                 # SalesOrder submission, idempotency, Admin visibility
│   │   │   ├── inventory/              # Opening FG balance ledger + read-only stock availability
│   │   │   └── audit/                  # Immutable AuditLog service
│   │   └── seeds/
│   │       └── benchmark_seed.py       # Idempotent Section 5 master & 50-packet FG seed
│   └── tests/
│       ├── conftest.py                 # Isolated ota_test fixture & Alembic migration hook
│       ├── test_health_and_db.py
│       ├── test_auth.py
│       ├── test_sales_catalog.py
│       └── test_orders_vertical_slice.py
└── frontend/
    ├── package.json
    ├── tsconfig.json / tsconfig.app.json / tsconfig.node.json
    ├── vite.config.ts
    ├── tailwind.config.ts
    ├── components.json                 # shadcn/ui configuration
    ├── Dockerfile
    └── src/
        ├── App.tsx
        ├── main.tsx
        ├── index.css
        ├── lib/                        # API client, money formatter, auth context, utils
        ├── components/                 # shadcn/ui primitives, StatusBadge, Mobile & Admin layouts
        └── pages/
            ├── LoginPage.tsx
            ├── salesman/               # Home, NewOrder (Customer->Products->Cart/Submit), Confirm, MyOrders
            └── admin/                  # Dashboard, IncomingOrders (polling), OrderDetail review
```

Each backend domain module (`iam`, `sales`, `orders`) separates `models.py`, `schemas.py`, `repository.py`, `service.py`, and `router.py` cleanly.
