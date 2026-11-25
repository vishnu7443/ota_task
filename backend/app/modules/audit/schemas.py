"""Pydantic schemas for Centralized Audit Explorer, Event Detail & User Activity Reports."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogEntryOut(BaseModel):
    id: int
    actor_user_id: int | None = None
    actor_username: str | None = None
    actor_full_name: str | None = None
    actor_role: str
    occurred_at: datetime
    action: str
    entity_schema: str
    entity_table: str
    entity_id: int
    correlation_ref: str | None = None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None
    reason: str | None = None


class PaginatedAuditLogsOut(BaseModel):
    items: list[AuditLogEntryOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class AuditActionCountOut(BaseModel):
    action: str
    count: int


class AuditSchemaCountOut(BaseModel):
    entity_schema: str
    count: int


class AuditSummaryOut(BaseModel):
    total_events: int
    security_events_count: int
    login_failures_count: int
    access_denied_count: int
    distinct_active_actors: int
    by_schema: list[AuditSchemaCountOut]
    top_actions: list[AuditActionCountOut]


class UserActivityRowOut(BaseModel):
    user_id: int
    username: str
    full_name: str
    role_code: str
    role_name: str
    is_active: bool
    total_actions: int
    login_success_count: int
    login_failed_count: int
    access_denied_count: int
    business_events_count: int
    last_login_at: datetime | None = None
    last_event_at: datetime | None = None
