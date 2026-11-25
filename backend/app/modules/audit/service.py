from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditLog


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
) -> AuditLog:
    """Append an immutable audit entry inside the caller's active transaction."""
    entry = AuditLog(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        entity_schema=entity_schema,
        entity_table=entity_table,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
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
