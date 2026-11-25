from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.database import check_db_health
from app.modules.audit.service import record_audit_log


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


def test_database_connectivity_and_seed_opening_balance(db_session: Session) -> None:
    assert check_db_health(db_session) is True
    row = db_session.execute(
        text(
            """
            SELECT on_hand_qty_base, reserved_qty_base, available_qty_base
            FROM inventory.inventory_balances
            LIMIT 1
            """
        )
    ).one()
    assert int(row.on_hand_qty_base) == 50
    assert int(row.reserved_qty_base) == 0
    assert int(row.available_qty_base) == 50


def test_ledger_and_audit_triggers_forbid_update_and_delete(db_session: Session) -> None:
    # Seed an audit entry first so FOR EACH ROW triggers evaluate against actual persisted rows
    record_audit_log(
        db_session,
        actor_user_id=None,
        actor_role="SYSTEM",
        action="TEST_AUDIT_SEED",
        entity_schema="audit",
        entity_table="audit_logs",
        entity_id=1,
        after_state={"note": "trigger check"},
    )
    db_session.commit()

    # Verify PostgreSQL append-only triggers protect inventory_movements and audit_logs
    for stmt in (
        "DELETE FROM inventory.inventory_movements",
        "UPDATE inventory.inventory_movements SET notes = 'TAMPERED'",
        "DELETE FROM audit.audit_logs",
        "UPDATE audit.audit_logs SET action = 'TAMPERED'",
    ):
        try:
            db_session.execute(text(stmt))
            raise AssertionError(f"Expected PostgreSQL append-only trigger to block: {stmt}")
        except DBAPIError:
            db_session.rollback()
