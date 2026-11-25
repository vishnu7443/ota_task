from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.main import app
from app.modules.orders.models import SalesOrder, SalesOrderItem
from app.modules.sales.models import Customer, PackSize
from tests.conftest import login_and_get_headers


def _get_ids(db: Session) -> dict[str, int]:
    ret_a = db.execute(select(Customer).where(Customer.code == "CUST-RET-A")).scalar_one()
    dist_b = db.execute(select(Customer).where(Customer.code == "CUST-DIST-B")).scalar_one()
    mrk = db.execute(select(PackSize).where(PackSize.sku_code == "MRK-200G")).scalar_one()
    return {"ret_a": ret_a.id, "dist_b": dist_b.id, "mrk": mrk.id}


def test_valid_order_submission_benchmark_slice_and_no_stock_deduction(
    client: TestClient, db_session: Session
) -> None:
    ids = _get_ids(db_session)
    sm_a_headers = login_and_get_headers(client, "salesman_a")
    client_order_id = str(uuid4())

    resp = client.post(
        "/api/v1/orders",
        headers=sm_a_headers,
        json={
            "customer_id": ids["ret_a"],
            "client_order_id": client_order_id,
            "notes": "Morning retail route order",
            "items": [{"pack_size_id": ids["mrk"], "ordered_qty_pkts": 150}],
        },
    )
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["status"] == "SUBMITTED"
    assert order["customer_name"] == "Retailer A"
    assert order["salesman_name"] == "Salesman A"
    assert order["total_packets"] == 150
    assert order["taxable_total_paisa"] == 750000  # ₹7,500.00
    assert order["tax_estimate"]["supply_type"] == "INTRA_STATE"
    assert order["tax_estimate"]["cgst_total_paisa"] == 18750  # ₹187.50
    assert order["tax_estimate"]["sgst_total_paisa"] == 18750  # ₹187.50
    assert order["tax_estimate"]["igst_total_paisa"] == 0
    assert order["tax_estimate"]["grand_total_paisa"] == 787500  # ₹7,875.00
    assert order["is_duplicate_replay"] is False
    # Read-only shortage check flagged (150 ordered vs 50 opening stock) WITHOUT mutating stock!
    assert order["has_shortage"] is True
    assert order["items"][0]["shortage_pkts"] == 100

    # Verify inventory_balances was NOT reserved or deducted on submission
    bal = db_session.execute(
        text("SELECT on_hand_qty_base, reserved_qty_base, available_qty_base FROM inventory.inventory_balances LIMIT 1")
    ).one()
    assert int(bal.on_hand_qty_base) == 50
    assert int(bal.reserved_qty_base) == 0
    assert int(bal.available_qty_base) == 50


def test_server_side_price_ignores_tampered_client_price(
    client: TestClient, db_session: Session
) -> None:
    ids = _get_ids(db_session)
    sm_a_headers = login_and_get_headers(client, "salesman_a")

    resp = client.post(
        "/api/v1/orders",
        headers=sm_a_headers,
        json={
            "customer_id": ids["ret_a"],
            "client_order_id": str(uuid4()),
            # Client attempts to spoof unit_price_paisa and total
            "unit_price_paisa": 100,
            "taxable_total_paisa": 100,
            "items": [
                {
                    "pack_size_id": ids["mrk"],
                    "ordered_qty_pkts": 10,
                    "unit_price_paisa": 1,
                }
            ],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["items"][0]["unit_price_paisa"] == 5000
    assert data["taxable_total_paisa"] == 50000


def test_duplicate_submission_idempotency(client: TestClient, db_session: Session) -> None:
    ids = _get_ids(db_session)
    sm_a_headers = login_and_get_headers(client, "salesman_a")
    idem_uuid = str(uuid4())
    payload = {
        "customer_id": ids["ret_a"],
        "client_order_id": idem_uuid,
        "items": [{"pack_size_id": ids["mrk"], "ordered_qty_pkts": 25}],
    }

    first = client.post("/api/v1/orders", headers=sm_a_headers, json=payload)
    assert first.status_code == 201
    assert first.json()["is_duplicate_replay"] is False

    second = client.post("/api/v1/orders", headers=sm_a_headers, json=payload)
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["order_number"] == first.json()["order_number"]
    assert second.json()["is_duplicate_replay"] is True

    total_orders = db_session.execute(select(func.count(SalesOrder.id))).scalar_one()
    assert total_orders == 1


def test_invalid_quantity_and_invalid_customer(client: TestClient, db_session: Session) -> None:
    ids = _get_ids(db_session)
    sm_a_headers = login_and_get_headers(client, "salesman_a")

    # Zero / negative quantity rejected (422)
    zero_qty = client.post(
        "/api/v1/orders",
        headers=sm_a_headers,
        json={
            "customer_id": ids["ret_a"],
            "client_order_id": str(uuid4()),
            "items": [{"pack_size_id": ids["mrk"], "ordered_qty_pkts": 0}],
        },
    )
    assert zero_qty.status_code == 422

    neg_qty = client.post(
        "/api/v1/orders",
        headers=sm_a_headers,
        json={
            "customer_id": ids["ret_a"],
            "client_order_id": str(uuid4()),
            "items": [{"pack_size_id": ids["mrk"], "ordered_qty_pkts": -10}],
        },
    )
    assert neg_qty.status_code == 422

    # Nonexistent customer rejected (404)
    missing_cust = client.post(
        "/api/v1/orders",
        headers=sm_a_headers,
        json={
            "customer_id": 999999,
            "client_order_id": str(uuid4()),
            "items": [{"pack_size_id": ids["mrk"], "ordered_qty_pkts": 5}],
        },
    )
    assert missing_cust.status_code == 404

    # Salesman A cannot submit order for Distributor B assigned to Salesman B (403)
    forbidden_cust = client.post(
        "/api/v1/orders",
        headers=sm_a_headers,
        json={
            "customer_id": ids["dist_b"],
            "client_order_id": str(uuid4()),
            "items": [{"pack_size_id": ids["mrk"], "ordered_qty_pkts": 5}],
        },
    )
    assert forbidden_cust.status_code == 403


def test_salesman_order_isolation_and_admin_order_visibility(
    client: TestClient, db_session: Session
) -> None:
    ids = _get_ids(db_session)
    sm_a_headers = login_and_get_headers(client, "salesman_a")
    sm_b_headers = login_and_get_headers(client, "salesman_b")
    adm_headers = login_and_get_headers(client, "admin")

    created = client.post(
        "/api/v1/orders",
        headers=sm_a_headers,
        json={
            "customer_id": ids["ret_a"],
            "client_order_id": str(uuid4()),
            "items": [{"pack_size_id": ids["mrk"], "ordered_qty_pkts": 150}],
        },
    )
    assert created.status_code == 201
    order_id = created.json()["id"]

    # Salesman A sees own order
    my_a = client.get("/api/v1/orders/my", headers=sm_a_headers)
    assert my_a.status_code == 200
    assert my_a.json()["total"] == 1
    assert my_a.json()["items"][0]["id"] == order_id

    # Salesman B does NOT see Salesman A's order in list or detail
    my_b = client.get("/api/v1/orders/my", headers=sm_b_headers)
    assert my_b.status_code == 200
    assert my_b.json()["total"] == 0
    assert client.get(f"/api/v1/orders/{order_id}", headers=sm_b_headers).status_code == 403

    # Admin sees exact persisted order in queue and detail view
    admin_list = client.get("/api/v1/admin/orders", headers=adm_headers)
    assert admin_list.status_code == 200
    admin_items = admin_list.json()["items"]
    assert len(admin_items) == 1
    assert admin_items[0]["order_number"] == created.json()["order_number"]
    assert admin_items[0]["customer_name"] == "Retailer A"
    assert admin_items[0]["salesman_name"] == "Salesman A"
    assert admin_items[0]["total_packets"] == 150
    assert admin_items[0]["status"] == "SUBMITTED"

    admin_detail = client.get(f"/api/v1/admin/orders/{order_id}", headers=adm_headers)
    assert admin_detail.status_code == 200
    detail = admin_detail.json()
    assert detail["customer_gstin"] == "33AAACR9999K1Z2"
    assert detail["items"][0]["display_name"] == "Murukku 200 g"
    assert detail["items"][0]["ordered_qty_pkts"] == 150
    assert detail["items"][0]["live_on_hand_pkts"] == 50
    assert len(detail["status_history"]) == 1


def test_transaction_rollback_on_failure_leaves_zero_partial_records(
    client: TestClient, db_session: Session
) -> None:
    ids = _get_ids(db_session)
    sm_a_headers = login_and_get_headers(client, "salesman_a")

    with (
        patch(
            "app.modules.orders.service.record_audit_log",
            side_effect=RuntimeError("Simulated audit write failure"),
        ),
        TestClient(app, raise_server_exceptions=False) as no_raise_client,
    ):
        resp = no_raise_client.post(
            "/api/v1/orders",
            headers=sm_a_headers,
            json={
                "customer_id": ids["ret_a"],
                "client_order_id": str(uuid4()),
                "items": [{"pack_size_id": ids["mrk"], "ordered_qty_pkts": 30}],
            },
        )
        assert resp.status_code == 500

    # Verify full rollback: 0 orders and 0 order items persisted
    db_session.rollback()
    assert db_session.execute(select(func.count(SalesOrder.id))).scalar_one() == 0
    assert db_session.execute(select(func.count(SalesOrderItem.id))).scalar_one() == 0
