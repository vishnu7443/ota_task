from collections.abc import Generator

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import get_settings
from app.core.database import get_db
from app.main import app
from app.seeds.benchmark_seed import DEV_SEED_PASSWORDS, seed_benchmark_master_data

settings = get_settings()

if settings.TEST_DATABASE_URL == settings.DATABASE_URL:
    raise RuntimeError("TEST_DATABASE_URL must point to a separate test database, not DATABASE_URL.")

test_engine = create_engine(settings.TEST_DATABASE_URL, pool_pre_ping=True, future=True)
TestSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def migrate_test_database() -> Generator[None, None, None]:
    """Run Alembic migrations cleanly against the isolated test database."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.TEST_DATABASE_URL)
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
    yield
    test_engine.dispose()


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Provide a clean, freshly seeded test database for every test function."""
    with test_engine.begin() as conn:
        # Temporarily bypass append-only triggers only for test fixture cleanup
        conn.execute(text("ALTER TABLE inventory.inventory_movements DISABLE TRIGGER trg_inventory_movements_append_only"))
        conn.execute(text("ALTER TABLE audit.audit_logs DISABLE TRIGGER trg_audit_logs_append_only"))
        conn.execute(text("ALTER TABLE audit.reconciliation_events DISABLE TRIGGER trg_reconciliation_events_append_only"))
        conn.execute(text("ALTER TABLE sales.sales_order_status_history DISABLE TRIGGER trg_order_status_history_append_only"))
        conn.execute(
            text(
                """
                TRUNCATE TABLE
                    audit.reconciliation_events,
                    audit.reconciliation_discrepancies,
                    audit.reconciliation_runs,
                    audit.variance_alerts,
                    audit.audit_logs,
                    costing.production_cost_summaries,
                    costing.production_overheads,
                    finance.customer_receivables,
                    finance.payment_refunds,
                    finance.payment_allocations,
                    finance.payments,
                    inventory.cost_lot_consumptions,
                    inventory.stock_reservations,
                    inventory.cost_lots,
                    inventory.inventory_movements,
                    inventory.inventory_balances,
                    inventory.stock_adjustments,
                    inventory.opening_balances,
                    billing.dispatch_status_history,
                    billing.dispatch_items,
                    billing.dispatches,
                    billing.credit_note_items,
                    billing.credit_notes,
                    billing.invoice_tax_components,
                    billing.invoice_items,
                    billing.invoices,
                    billing.fiscal_sequences,
                    production.production_variances,
                    production.production_wastages,
                    production.production_outputs,
                    production.production_material_issues,
                    production.production_runs,
                    production.bom_components,
                    production.bom_versions,
                    production.bom_headers,
                    production.recipe_templates,
                    purchasing.purchase_receipt_items,
                    purchasing.purchase_receipts,
                    purchasing.purchase_order_items,
                    purchasing.purchase_orders,
                    purchasing.suppliers,
                    sales.sales_order_approvals,
                    sales.sales_order_status_history,
                    sales.sales_order_items,
                    sales.sales_orders,
                    sales.price_list_items,
                    sales.price_lists,
                    sales.pack_sizes,
                    sales.products,
                    sales.customer_addresses,
                    sales.customers,
                    sales.salesman_profiles,
                    production.unit_conversions,
                    production.materials,
                    iam.users,
                    iam.roles,
                    iam.company_profiles
                RESTART IDENTITY CASCADE
                """
            )
        )
        conn.execute(text("ALTER TABLE inventory.inventory_movements ENABLE TRIGGER trg_inventory_movements_append_only"))
        conn.execute(text("ALTER TABLE audit.audit_logs ENABLE TRIGGER trg_audit_logs_append_only"))
        conn.execute(text("ALTER TABLE audit.reconciliation_events ENABLE TRIGGER trg_reconciliation_events_append_only"))
        conn.execute(text("ALTER TABLE sales.sales_order_status_history ENABLE TRIGGER trg_order_status_history_append_only"))

    db = TestSessionLocal()
    try:
        seed_benchmark_master_data(db)
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login_and_get_headers(client: TestClient, username: str) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": DEV_SEED_PASSWORDS[username]},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
