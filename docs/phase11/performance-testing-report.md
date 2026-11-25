# Performance & Latency Benchmark Report — Phase 11

All metrics in this report were directly measured on the local workstation against isolated PostgreSQL 16 (`ota_test`) populated via an automated workload setup script (`perf_benchmark.py`) executing **20 full Sales -> Approve -> Issue GST Invoice -> Dispatch -> Payment cycles** and **3 complete PO -> GRN -> Production -> Costing cycles** on top of seeded benchmark data.

---

## 1. Benchmark Methodology & Environment

- **Database:** PostgreSQL 16 (`localhost:5432`, isolated `ota_test`)
- **Backend:** FastAPI + SQLAlchemy 2.0 + Psycopg 3 (via ASGI `TestClient`)
- **Measurement:** 1 warm-up call followed by 15 timed sequential calls (`time.perf_counter()`), plus 1 burst concurrency test (`ThreadPoolExecutor(max_workers=8)` firing 24 concurrent `/api/v1/intelligence/dashboard` requests).

---

## 2. Measured Endpoint Latencies (15 Warm Sequential Requests Each)

| Endpoint | Workload Scope | Mean (ms) | Median `p50` (ms) | `p95` (ms) | Max (ms) | HTTP Status |
| --- | --- | --- | --- | --- | --- | --- |
| `GET /api/v1/health` | DB health ping (`SELECT 1`) | `8.93` | `8.75` | `10.88` | `10.88` | `200` (15/15) |
| `GET /api/v1/orders/my?page=1&page_size=20` | Salesman paginated orders | `31.75` | `31.72` | `39.18` | `39.18` | `200` (15/15) |
| `GET /api/v1/admin/orders?page=1&page_size=20` | Admin paginated orders + stock availability join | `31.12` | `30.42` | `40.86` | `40.86` | `200` (15/15) |
| `GET /api/v1/inventory/overview` | Unified RM/Pkg/FG opening/inward/outward/balance summary | `20.30` | `20.17` | `22.32` | `22.32` | `200` (15/15) |
| `GET /api/v1/inventory/ledger?limit=50` | Chronological ledger movements + doc refs | `22.73` | `23.02` | `27.48` | `27.48` | `200` (15/15) |
| `GET /api/v1/billing/reports` | Sales Register, GST, CN, Dispatch, Customer, SKU, AR reports | `40.97` | `31.64` | `129.48` | `129.48` | `200` (15/15) |
| `GET /api/v1/finance/receivables` | Live AR balance & ageing computation | `15.30` | `15.40` | `17.16` | `17.16` | `200` (15/15) |
| `GET /api/v1/finance/profitability` | FIFO COGS, net revenue & gross margin breakdown | `27.00` | `26.69` | `30.15` | `30.15` | `200` (15/15) |
| `GET /api/v1/audit/logs?page=1&page_size=50` | Paginated immutable audit log search | `13.72` | `13.66` | `14.40` | `14.40` | `200` (15/15) |
| `GET /api/v1/reconciliation/reports/inventory` | Full RM/Pkg/FG ledger-vs-balance-vs-lot verification | `17.94` | `17.71` | `20.42` | `20.42` | `200` (15/15) |
| `GET /api/v1/intelligence/dashboard` | Multi-module executive KPIs, watchlist & ageing aggregation | `69.87` | `70.06` | `83.46` | `83.46` | `200` (15/15) |

---

## 3. Concurrent Load Burst & Concurrency Locks

- **Concurrent Executive Read Test (`8` parallel workers, `24` requests):**
  - Target: `GET /api/v1/intelligence/dashboard`
  - **Result:** All `24/24` requests returned `HTTP 200` in **`1371.86 ms`** total wall time (`~57.16 ms` effective throughput interval per request, zero connection errors or pool exhaustion).
- **Row-Lock Write Concurrency Tests (Observed in Pytest Phases 5–9):**
  - 8 concurrent order approvals against finite `50`-pkt FG stock (`test_concurrent_approval_attempts_prevent_overselling_and_duplicate_history`): zero overselling (`SELECT ... FOR UPDATE`).
  - Concurrent GRN posting & concurrent adjustments (`test_concurrent_receipt_post_and_concurrent_adjustments_prevent_corruption`): zero balance drift.
  - Concurrent production material issuance (`test_6_concurrent_material_issues_and_transaction_rollback`): strictly one success, zero double issue.
  - Concurrent FG dispatch (`test_5_concurrency_insufficient_fg_rollback_and_rbac_isolation`): atomic FEFO stock conservation.
  - Concurrent payment allocation (`test_8_immutability_triggers_strict_rbac_and_concurrent_allocation_lock`): zero over-allocation.

---

## 4. Database Query & Indexing Assessment

- **Latency Target Compliance:** Every sequential read endpoint stays well under `75 ms` p50 (`8.75 ms – 70.06 ms`), well suited for snappy mobile field sales over Indian 4G networks and desktop control desks.
- **Scaling Note for High-Volume Production (Year 2+):** As transaction rows exceed 100k+ movements/audit logs, ensure periodic `VACUUM ANALYZE` on `inventory.inventory_movements` and `audit.audit_logs`, and consider time-range default windows on `billing/reports` and `intelligence/dashboard`.
