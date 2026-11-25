from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.iam.models import User
from tests.conftest import DEV_SEED_PASSWORDS, login_and_get_headers


def test_login_success_and_me_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "salesman_a", "password": DEV_SEED_PASSWORDS["salesman_a"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "salesman_a"
    assert data["user"]["role_code"] == "SALESMAN"

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200
    assert me.json()["full_name"] == "Salesman A"


def test_login_invalid_credentials_rejected(client: TestClient) -> None:
    bad_pw = client.post(
        "/api/v1/auth/login",
        json={"username": "salesman_a", "password": "WrongPassword!"},
    )
    assert bad_pw.status_code == 401
    assert bad_pw.json()["error"]["code"] == "AUTHENTICATION_FAILED"

    bad_user = client.post(
        "/api/v1/auth/login",
        json={"username": "nobody", "password": "WrongPassword!"},
    )
    assert bad_user.status_code == 401


def test_inactive_user_cannot_login(client: TestClient, db_session: Session) -> None:
    user = db_session.execute(select(User).where(User.username == "salesman_b")).scalar_one()
    user.is_active = False
    db_session.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "salesman_b", "password": DEV_SEED_PASSWORDS["salesman_b"]},
    )
    assert resp.status_code == 401


def test_unauthorized_access_and_rbac_boundaries(client: TestClient) -> None:
    # Unauthenticated request
    assert client.get("/api/v1/sales/customers").status_code == 401
    assert client.get("/api/v1/admin/orders").status_code == 401

    # Tampered token
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid.jwt.token"}).status_code
        == 401
    )

    # Salesman cannot access Admin incoming orders queue
    sm_headers = login_and_get_headers(client, "salesman_a")
    admin_attempt = client.get("/api/v1/admin/orders", headers=sm_headers)
    assert admin_attempt.status_code == 403
    assert admin_attempt.json()["error"]["code"] == "FORBIDDEN"

    # Admin cannot submit orders via Salesman-only endpoint
    adm_headers = login_and_get_headers(client, "admin")
    submit_attempt = client.post(
        "/api/v1/orders",
        headers=adm_headers,
        json={
            "customer_id": 1,
            "client_order_id": "11111111-1111-4111-8111-111111111111",
            "items": [{"pack_size_id": 1, "ordered_qty_pkts": 10}],
        },
    )
    assert submit_attempt.status_code == 403

    # Supervisor cannot read customer orders
    sup_headers = login_and_get_headers(client, "supervisor")
    assert client.get("/api/v1/admin/orders", headers=sup_headers).status_code == 403
