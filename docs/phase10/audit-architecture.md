# Centralized Audit Architecture (`audit.audit_logs`)

## 1. Design Philosophy

From Phase 4 onward, every write path in the ERP records audit entries inside the same database transaction as the business mutation via `app.modules.audit.service.record_audit_log`. Phase 10 promotes this log into an enterprise-grade Audit Management subsystem without breaking earlier callers.

---

## 2. Request Correlation Tracking (`contextvars`)

- Middleware in `backend/app/main.py` generates a per-request ID (`REQ-<8-hex>`) on every HTTP call, binds it using `set_request_correlation_id` in `backend/app/core/logging.py`, resets it cleanly in a `finally` block, and echoes it in the `X-Request-ID` HTTP response header.
- `record_audit_log` resolves `correlation_ref` automatically: explicit document numbers (such as `REC/2026-27/0001` during reconciliation) or the active `REQ-...` request correlation ID when omitted.
- Database index `idx_audit_correlation_ref` (`WHERE correlation_ref IS NOT NULL`) enables sub-millisecond lookup of every database mutation triggered within a single HTTP request or workflow batch.

---

## 3. Credential Sanitization Policy

`record_audit_log` runs recursive key sanitization (`_sanitize_payload`) across `before_state`, `after_state`, and `metadata_json` before persistence:
- Sensitive keys (`password`, `password_hash`, `token`, `access_token`, `refresh_token`, `secret`, `authorization`, `jwt`) are automatically replaced with `"[REDACTED]"`.
- `LOGIN_SUCCESS`, `LOGIN_FAILED`, `USER_CREATED`, `USER_ROLE_CHANGED`, and `USER_STATUS_CHANGED` store only non-secret identifiers (`username`, `role_code`, `is_active`) and never record plaintext passwords, bcrypt digests, or JWT tokens.

---

## 4. Database Protection & Immutability

- PostgreSQL table `audit.audit_logs` is protected by trigger `trg_audit_logs_append_only` executing `audit.fn_prevent_mutation()`.
- Any direct SQL `UPDATE` or `DELETE` against `audit.audit_logs` raises SQLSTATE `42501` and aborts the transaction.
- `action` column length is expanded to `VARCHAR(48)` in Migration `0007_phase10_audit_recon` with composite index `idx_audit_action_time (action, occurred_at DESC)`.

---

## 5. Querying, User Activity & Export Controls

- **Queryable Explorer (`GET /api/v1/audit/logs`):** Filterable by `actor_user_id`, `actor_role`, `action`, `entity_schema`, `entity_table`, `entity_id`, `correlation_ref`, `date_from`/`date_to` (IST boundaries converted to UTC), and case-insensitive keyword search across `entity_table`, `action`, `correlation_ref`, and `reason`.
- **Audit Summary (`GET /api/v1/audit/summary`):** Computes total events, security events (`LOGIN_SUCCESS`, `LOGIN_FAILED`, `ACCESS_DENIED`), failure/denied counts, distinct actors, per-schema distribution, and top action breakdown.
- **User Activity Report (`GET /api/v1/audit/user-activity`):** Joins all `iam.users` with aggregated counts of `login_success_count`, `login_failed_count`, `access_denied_count`, `business_events_count`, `last_login_at`, and `last_event_at`.
- **CSV Export (`GET /api/v1/audit/logs/export/csv`):** Streams sanitized UTF-8 CSV (up to 5,000 rows per export) including serialized Before/After JSON snapshots.
