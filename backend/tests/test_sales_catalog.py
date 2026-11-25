from fastapi.testclient import TestClient

from tests.conftest import login_and_get_headers


def test_salesman_customer_scoping(client: TestClient) -> None:
    sm_a_headers = login_and_get_headers(client, "salesman_a")
    resp_a = client.get("/api/v1/sales/customers", headers=sm_a_headers)
    assert resp_a.status_code == 200
    customers_a = resp_a.json()
    codes_a = {c["code"] for c in customers_a}
    assert "CUST-RET-A" in codes_a
    assert "CUST-DIST-B" not in codes_a

    # Admin sees all active customers
    adm_headers = login_and_get_headers(client, "admin")
    resp_all = client.get("/api/v1/sales/customers", headers=adm_headers)
    assert resp_all.status_code == 200
    codes_all = {c["code"] for c in resp_all.json()}
    assert {"CUST-RET-A", "CUST-DIST-B"}.issubset(codes_all)


def test_product_retrieval_returns_authoritative_price_and_stock(client: TestClient) -> None:
    sm_a_headers = login_and_get_headers(client, "salesman_a")
    resp = client.get("/api/v1/sales/products", headers=sm_a_headers)
    assert resp.status_code == 200
    products = resp.json()
    murukku = next(p for p in products if p["sku_code"] == "MRK-200G")
    assert murukku["display_name"] == "Murukku 200 g"
    assert murukku["selling_price_paisa"] == 5000  # ₹50.00
    assert murukku["gst_rate_bps"] == 500  # 5.00%
    assert murukku["packets_per_carton"] == 20
    assert murukku["available_stock_pkts"] == 50  # Seeded opening stock
