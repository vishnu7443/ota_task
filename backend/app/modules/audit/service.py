"""Centralized Audit Service — sanitized event recording, querying, user activity & CSV exports."""

import csv
import io
import math
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import NotFoundError
from app.core.logging import get_request_correlation_id
from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import (
    AuditActionCountOut,
    AuditLogEntryOut,
    AuditSchemaCountOut,
    AuditSummaryOut,
    PaginatedAuditLogsOut,
    UserActivityRowOut,
)
from app.modules.iam.models import User

IST = ZoneInfo("Asia/Kolkata")
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "authorization",
        "jwt",
    }
)


def _sanitize_payload(data: Any) -> Any:
    """Recursively redact sensitive credential keys so secrets never land in audit logs."""
    if data is None:
        return None
    if isinstance(data, dict):
        cleaned: dict[str, Any] = {}
        for k, v in data.items():
            if str(k).lower() in _SENSITIVE_KEYS:
                cleaned[str(k)] = "[REDACTED]"
            else:
                cleaned[str(k)] = _sanitize_payload(v)
        return cleaned
    if isinstance(data, list):
        return [_sanitize_payload(item) for item in data]
    return data


def record_audit_log(
    db: Session,
    *,
    actor_user_id: int | None,
    actor_role: str,
    action: str,
    entity_schema: str,
    entity_table: str,
    entity_id: int,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    reason: str | None = None,
    correlation_ref: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> AuditLog:
    """Append an immutable sanitized audit entry inside the caller's active transaction."""
    resolved_corr = correlation_ref or get_request_correlation_id()
    entry = AuditLog(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        entity_schema=entity_schema,
        entity_table=entity_table,
        entity_id=entity_id,
        correlation_ref=resolved_corr[:64] if resolved_corr else None,
        before_state=_sanitize_payload(before_state),
        after_state=_sanitize_payload(after_state),
        metadata_json=_sanitize_payload(metadata_json),
        reason=reason,
    )
    db.add(entry)
    db.flush()
    return entry


def list_order_audit_logs(db: Session, order_id: int) -> list[AuditLog]:
    """Retrieve all immutable order and stock-reservation audit entries for an order."""
    stmt = (
        select(AuditLog)
        .where(
            or_(
                and_(AuditLog.entity_table == "sales_orders", AuditLog.entity_id == order_id),
                and_(
                    AuditLog.entity_table == "inventory_balances",
                    AuditLog.after_state["sales_order_id"].astext == str(order_id),
                ),
            )
        )
        .order_by(AuditLog.occurred_at.asc(), AuditLog.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def _date_bounds_utc(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    start_dt = datetime.combine(date_from, time.min, tzinfo=IST).astimezone(UTC) if date_from else None
    end_dt = datetime.combine(date_to, time.max, tzinfo=IST).astimezone(UTC) if date_to else None
    return start_dt, end_dt


def _build_audit_filters(
    *,
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    action: str | None = None,
    entity_schema: str | None = None,
    entity_table: str | None = None,
    entity_id: int | None = None,
    correlation_ref: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
) -> list[Any]:
    conds: list[Any] = []
    if actor_user_id is not None:
        conds.append(AuditLog.actor_user_id == actor_user_id)
    if actor_role:
        conds.append(AuditLog.actor_role == actor_role.strip().upper())
    if action:
        conds.append(AuditLog.action == action.strip().upper())
    if entity_schema:
        conds.append(AuditLog.entity_schema == entity_schema.strip().lower())
    if entity_table:
        conds.append(AuditLog.entity_table == entity_table.strip().lower())
    if entity_id is not None:
        conds.append(AuditLog.entity_id == entity_id)
    if correlation_ref:
        conds.append(AuditLog.correlation_ref == correlation_ref.strip())
    start_dt, end_dt = _date_bounds_utc(date_from, date_to)
    if start_dt:
        conds.append(AuditLog.occurred_at >= start_dt)
    if end_dt:
        conds.append(AuditLog.occurred_at <= end_dt)
    if search and search.strip():
        pat = f"%{search.strip()}%"
        conds.append(
            or_(
                AuditLog.action.ilike(pat),
                AuditLog.entity_table.ilike(pat),
                AuditLog.reason.ilike(pat),
                AuditLog.correlation_ref.ilike(pat),
            )
        )
    return conds


def _hydrate_audit_rows(db: Session, rows: list[AuditLog]) -> list[AuditLogEntryOut]:
    user_ids = {r.actor_user_id for r in rows if r.actor_user_id is not None}
    users = (
        {u.id: u for u in db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()}
        if user_ids
        else {}
    )
    out: list[AuditLogEntryOut] = []
    for r in rows:
        u = users.get(r.actor_user_id) if r.actor_user_id is not None else None
        out.append(
            AuditLogEntryOut(
                id=r.id,
                actor_user_id=r.actor_user_id,
                actor_username=u.username if u else None,
                actor_full_name=u.full_name if u else None,
                actor_role=r.actor_role,
                occurred_at=r.occurred_at,
                action=r.action,
                entity_schema=r.entity_schema,
                entity_table=r.entity_table,
                entity_id=r.entity_id,
                correlation_ref=r.correlation_ref,
                before_state=r.before_state,
                after_state=r.after_state,
                metadata_json=r.metadata_json,
                reason=r.reason,
            )
        )
    return out


def list_audit_logs_paginated(
    db: Session,
    *,
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    action: str | None = None,
    entity_schema: str | None = None,
    entity_table: str | None = None,
    entity_id: int | None = None,
    correlation_ref: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> PaginatedAuditLogsOut:
    conds = _build_audit_filters(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        entity_schema=entity_schema,
        entity_table=entity_table,
        entity_id=entity_id,
        correlation_ref=correlation_ref,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    total = int(
        db.execute(select(func.count(AuditLog.id)).where(*conds)).scalar_one()
    )
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
    rows = list(
        db.execute(
            select(AuditLog)
            .where(*conds)
            .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PaginatedAuditLogsOut(
        items=_hydrate_audit_rows(db, rows),
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def get_audit_log_detail(db: Session, audit_id: int) -> AuditLogEntryOut:
    row = db.execute(select(AuditLog).where(AuditLog.id == audit_id)).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Audit log entry {audit_id} was not found.")
    return _hydrate_audit_rows(db, [row])[0]


def export_audit_logs_csv(
    db: Session,
    *,
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    action: str | None = None,
    entity_schema: str | None = None,
    entity_table: str | None = None,
    entity_id: int | None = None,
    correlation_ref: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
) -> str:
    conds = _build_audit_filters(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        entity_schema=entity_schema,
        entity_table=entity_table,
        entity_id=entity_id,
        correlation_ref=correlation_ref,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    rows = list(
        db.execute(
            select(AuditLog)
            .where(*conds)
            .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
            .limit(5000)
        )
        .scalars()
        .all()
    )
    hydrated = _hydrate_audit_rows(db, rows)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "ID",
            "Occurred At (UTC)",
            "Actor Username",
            "Actor Full Name",
            "Actor Role",
            "Action",
            "Schema",
            "Entity Table",
            "Entity ID",
            "Correlation Ref",
            "Reason",
        ]
    )
    for item in hydrated:
        writer.writerow(
            [
                item.id,
                item.occurred_at.isoformat(),
                item.actor_username or "",
                item.actor_full_name or "",
                item.actor_role,
                item.action,
                item.entity_schema,
                item.entity_table,
                item.entity_id,
                item.correlation_ref or "",
                item.reason or "",
            ]
        )
    return buf.getvalue()


def get_audit_summary(
    db: Session, *, date_from: date | None = None, date_to: date | None = None
) -> AuditSummaryOut:
    conds = _build_audit_filters(date_from=date_from, date_to=date_to)
    total_events = int(db.execute(select(func.count(AuditLog.id)).where(*conds)).scalar_one())
    login_failures = int(
        db.execute(
            select(func.count(AuditLog.id)).where(*conds, AuditLog.action == "LOGIN_FAILED")
        ).scalar_one()
    )
    access_denied = int(
        db.execute(
            select(func.count(AuditLog.id)).where(*conds, AuditLog.action == "ACCESS_DENIED")
        ).scalar_one()
    )
    security_count = int(
        db.execute(
            select(func.count(AuditLog.id)).where(
                *conds,
                AuditLog.action.in_(
                    [
                        "LOGIN_SUCCESS",
                        "LOGIN_FAILED",
                        "ACCESS_DENIED",
                        "USER_CREATED",
                        "USER_ROLE_CHANGED",
                        "USER_STATUS_CHANGED",
                    ]
                ),
            )
        ).scalar_one()
    )
    distinct_actors = int(
        db.execute(
            select(func.count(func.distinct(AuditLog.actor_user_id))).where(
                *conds, AuditLog.actor_user_id.is_not(None)
            )
        ).scalar_one()
    )
    schema_rows = db.execute(
        select(AuditLog.entity_schema, func.count(AuditLog.id).label("cnt"))
        .where(*conds)
        .group_by(AuditLog.entity_schema)
        .order_by(desc("cnt"))
    ).all()
    action_rows = db.execute(
        select(AuditLog.action, func.count(AuditLog.id).label("cnt"))
        .where(*conds)
        .group_by(AuditLog.action)
        .order_by(desc("cnt"))
        .limit(12)
    ).all()
    return AuditSummaryOut(
        total_events=total_events,
        security_events_count=security_count,
        login_failures_count=login_failures,
        access_denied_count=access_denied,
        distinct_active_actors=distinct_actors,
        by_schema=[AuditSchemaCountOut(entity_schema=r[0], count=int(r[1])) for r in schema_rows],
        top_actions=[AuditActionCountOut(action=r[0], count=int(r[1])) for r in action_rows],
    )


def get_user_activity_report(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    role_code: str | None = None,
) -> list[UserActivityRowOut]:
    users_stmt = select(User).options(joinedload(User.role)).order_by(User.id.asc())
    users = list(db.execute(users_stmt).scalars().all())
    if role_code:
        users = [u for u in users if u.role.code == role_code.strip().upper()]

    start_dt, end_dt = _date_bounds_utc(date_from, date_to)
    conds: list[Any] = [AuditLog.actor_user_id.is_not(None)]
    if start_dt:
        conds.append(AuditLog.occurred_at >= start_dt)
    if end_dt:
        conds.append(AuditLog.occurred_at <= end_dt)

    agg_rows = db.execute(
        select(
            AuditLog.actor_user_id,
            func.count(AuditLog.id).label("total_cnt"),
            func.sum(case((AuditLog.action == "LOGIN_SUCCESS", 1), else_=0)).label("login_ok"),
            func.sum(case((AuditLog.action == "LOGIN_FAILED", 1), else_=0)).label("login_fail"),
            func.sum(case((AuditLog.action == "ACCESS_DENIED", 1), else_=0)).label("denied"),
            func.max(AuditLog.occurred_at).label("last_ev"),
        )
        .where(*conds)
        .group_by(AuditLog.actor_user_id)
    ).all()
    agg_map = {int(r[0]): r for r in agg_rows}

    out: list[UserActivityRowOut] = []
    for u in users:
        a = agg_map.get(u.id)
        total_cnt = int(a[1]) if a else 0
        login_ok = int(a[2] or 0) if a else 0
        login_fail = int(a[3] or 0) if a else 0
        denied = int(a[4] or 0) if a else 0
        last_ev = a[5] if a else None
        out.append(
            UserActivityRowOut(
                user_id=u.id,
                username=u.username,
                full_name=u.full_name,
                role_code=u.role.code,
                role_name=u.role.name,
                is_active=u.is_active,
                total_actions=total_cnt,
                login_success_count=login_ok,
                login_failed_count=login_fail,
                access_denied_count=denied,
                business_events_count=max(0, total_cnt - login_ok - login_fail - denied),
                last_login_at=u.last_login_at,
                last_event_at=last_ev,
            )
        )
    return out
