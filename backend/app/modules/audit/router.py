"""Phase 10 Centralized Audit Trail & User Activity API router."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.audit import service as audit_service
from app.modules.audit.schemas import (
    AuditLogEntryOut,
    AuditSummaryOut,
    PaginatedAuditLogsOut,
    UserActivityRowOut,
)
from app.modules.iam import service as iam_service
from app.modules.iam.schemas import CurrentActor

router = APIRouter(prefix="/audit", tags=["Centralized Audit & Activity"])

_AuditViewer = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN", "ACCOUNTANT_AUDITOR", "OWNER")),
]


@router.get("/logs", response_model=PaginatedAuditLogsOut)
def list_audit_logs(
    _actor: _AuditViewer,
    db: Annotated[Session, Depends(get_db)],
    actor_user_id: Annotated[int | None, Query(gt=0)] = None,
    actor_role: Annotated[str | None, Query(max_length=32)] = None,
    action: Annotated[str | None, Query(max_length=48)] = None,
    entity_schema: Annotated[str | None, Query(max_length=32)] = None,
    entity_table: Annotated[str | None, Query(max_length=64)] = None,
    entity_id: Annotated[int | None, Query(ge=0)] = None,
    correlation_ref: Annotated[str | None, Query(max_length=64)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=80)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> PaginatedAuditLogsOut:
    return audit_service.list_audit_logs_paginated(
        db,
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
        page=page,
        page_size=page_size,
    )


@router.get("/logs/export/csv")
def export_audit_logs_csv(
    _actor: _AuditViewer,
    db: Annotated[Session, Depends(get_db)],
    actor_user_id: Annotated[int | None, Query(gt=0)] = None,
    actor_role: Annotated[str | None, Query(max_length=32)] = None,
    action: Annotated[str | None, Query(max_length=48)] = None,
    entity_schema: Annotated[str | None, Query(max_length=32)] = None,
    entity_table: Annotated[str | None, Query(max_length=64)] = None,
    entity_id: Annotated[int | None, Query(ge=0)] = None,
    correlation_ref: Annotated[str | None, Query(max_length=64)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=80)] = None,
) -> Response:
    csv_text = audit_service.export_audit_logs_csv(
        db,
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
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit_logs_export.csv"'},
    )


@router.get("/logs/{audit_id}", response_model=AuditLogEntryOut)
def get_audit_log_detail(
    audit_id: int,
    _actor: _AuditViewer,
    db: Annotated[Session, Depends(get_db)],
) -> AuditLogEntryOut:
    return audit_service.get_audit_log_detail(db, audit_id)


@router.get("/summary", response_model=AuditSummaryOut)
def get_audit_summary(
    _actor: _AuditViewer,
    db: Annotated[Session, Depends(get_db)],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> AuditSummaryOut:
    return audit_service.get_audit_summary(db, date_from=date_from, date_to=date_to)


@router.get("/user-activity", response_model=list[UserActivityRowOut])
def get_user_activity_report(
    _actor: _AuditViewer,
    db: Annotated[Session, Depends(get_db)],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    role_code: Annotated[str | None, Query(max_length=32)] = None,
) -> list[UserActivityRowOut]:
    return audit_service.get_user_activity_report(
        db, date_from=date_from, date_to=date_to, role_code=role_code
    )
