# Phase 4 — Implementation Overview

**Project:** Order-to-Audit Management System for a South Indian Packaged Food Manufacturer (`Kaveri Traditional Snacks Pvt. Ltd.`, fictional benchmark tenant)  
**Scope:** Project Foundation, PostgreSQL Database Foundation, Authentication & RBAC, and the **First Vertical Slice (Mobile Salesman Order Submission -> PostgreSQL Persistence -> Desktop Admin Order Visibility)**

---

## 1. Architecture & Pre-Implementation Review Findings

Before creating code, all existing documentation under [docs/phase1/](file:///d:/mac/ota/docs/phase1), [docs/phase2/](file:///d:/mac/ota/docs/phase2), and [docs/phase3/](file:///d:/mac/ota/docs/phase3) plus [Problem Statement - Winter Internship Application - 2026.docx](file:///d:/mac/ota/Problem%20Statement%20-%20Winter%20Internship%20Application%20-%202026.docx) were reviewed:

### Reconciled Tensions & Architectural Guardrails
1. **Stock Check vs Stock Mutation on Submission:**
   - Phase 1/2/3 (`BR-AVL-02`) and Phase 4 Task 7 mandate that submitting an order must **not** deduct or reserve finished-goods stock; reservation happens only upon Order Approval and physical deduction on Dispatch (Phase 5).
   - Meanwhile, read-only stock availability (`available = on_hand - reserved`) is computed at submission time to populate `sales.sales_orders.has_shortage` and `sales.sales_order_approvals.stock_snapshot` cleanly without modifying `inventory.inventory_balances`.
2. **Incremental Alembic Schema Scope vs Full Phase 3 Schema:**
   - Phase 3 defines 51 tables across 9 schemas (`iam`, `sales`, `purchasing`, `production`, `costing`, `inventory`, `billing`, `finance`, `audit`).
   - Phase 4 strictly forbids implementing invoicing, dispatch, production, costing, or complete inventory workflows yet. Therefore, initial Alembic migration `0001_phase4_foundation` deploys the exact Phase 3 tables required for IAM, Sales Masters, Sales Orders, Opening Finished Goods Inventory (`50` packets via `opening_balances` -> `inventory_movements` -> `inventory_balances`), and `audit.audit_logs` — preserving all Phase 3 column types, `CHECK` constraints, `ON DELETE RESTRICT` FKs, and PostgreSQL append-only triggers so Phase 5+ migrations extend cleanly without refactoring.
3. **Salesman Customer Territory Scoping (`DEC-05`):**
   - `Retailer A` is assigned to `Salesman A`; `Distributor B` is assigned to `Salesman B`. Customers with `assigned_salesman_id IS NULL` are shared; assigned customers are visible only to their owning salesman (plus Admin/Owner/Auditor).

---

## 2. Implemented Vertical Slice Milestones

| Milestone | Scope | Key Modules |
| --- | --- | --- |
| **1. Monorepo & Infrastructure** | Git repo initialized, clean folder boundaries (`backend/`, `frontend/`, `infrastructure/`, `docs/`), Docker Compose + separate `ota_test` DB init | Root config, `docker-compose.yml` |
| **2. Database & Migrations** | SQLAlchemy 2.0 models, Alembic `0001_phase4_foundation`, PostgreSQL immutability & balance sync triggers, idempotent benchmark seed (`50` FG pkts) | `app/core/database.py`, `alembic/`, `app/seeds/benchmark_seed.py` |
| **3. Auth & RBAC** | Argon2id password hashing, HS256 JWT tokens, server-side `require_roles` guard, PostgreSQL `SET LOCAL app.current_*` context, login/me endpoints | `app/modules/iam/`, `app/core/security.py` |
| **4. Mobile Order Submission** | Salesman customer & product retrieval, server-side integer-paisa pricing, `client_order_id` idempotency, atomic order + history + audit creation, mobile React UI (`<1 min` entry) | `app/modules/sales/`, `app/modules/orders/`, `frontend/src/pages/salesman/` |
| **5. Admin Order Visibility** | Paginated/filterable Admin incoming order queue with 10s polling, detailed order review screen with live stock coverage & GST estimate | `orders/router.py`, `frontend/src/pages/admin/` |
