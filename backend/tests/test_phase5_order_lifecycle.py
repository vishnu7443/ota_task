from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.main import app
from app.modules.inventory import service as inventory_service
from app.modules.inventory.models import InventoryBalance, StockReservation
from app.modules.orders.models import SalesOrderStatusHistory
from app.modules.sales.models import Customer, PackSize
from tests.conftest import TestSessionLocal, login_and_get_headers


def _ids(db: Session) -> dict[str, int]:
    ret_a = db.execute(select(Customer).where(Customer.code == "CUST-RET-A")).scalar_one()
    dist_b = db.execute(select(Customer).where(Customer.code == "CUST-DIST-B")).scalar_one()
    mrk = db.execute(select(PackSize).where(PackSize.sku_code == "MRK-200G")).scalar_one()
    return {"ret_a": ret_a.id, "dist_b": dist_b.id, "mrk": mrk.id}


def _grant_controlled_test_stock(db: Session, *, admin_id: int, pack_size_id: int, add_pkts: int) -> None:
    """Seed additional isolated test inventory (never marked as production output)."""
    inventory_service.seed_opening_finished_goods(
        db,
        batch_ref=f"TEST-STOCK-{uuid4().hex[:8]}",
        pack_size_id=pack_size_id,
        opening_qty_pkts=add_pkts,
        unit_cost_paisa=2885,
        as_of_date=date(2026, 11, 25),
        created_by=admin_id,
    )
    db.commit()


def _create_order(
    client: TestClient,
    headers: dict[str, str],
    *,
    customer_id: int,
    pack_size_id: int,
    qty_pkts: int,
    notes: str = "Test order",
) -> dict:
    resp = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "customer_id": customer_id,
            "client_order_id": str(uuid4()),
            "notes": notes,
            "items": [{"pack_size_id": pack_size_id, "ordered_qty_pkts": qty_pkts}],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_valid_approval_sufficient_stock_and_reservation_math(
    client: TestClient, db_session: Session
) -> None:
    ids = _ids(db_session)
    sm_a = login_and_get_headers(client, "salesman_a")
    adm = login_and_get_headers(client, "admin")
    admin_me = client.get("/api/v1/auth/me", headers=adm).json()

    # Opening seed is 50 pkts; add +150 controlled test stock -> 200 physical on-hand
    _grant_controlled_test_stock(db_session, admin_id=admin_me["id"], pack_size_id=ids["mrk"], add_pkts=150)

    order1 = _create_order(client, sm_a, customer_id=ids["ret_a"], pack_size_id=ids["mrk"], qty_pkts=150)

    # Approve Order 1 cleanly
    approve_resp = client.post(
        f"/api/v1/admin/orders/{order1['id']}/approve",
        headers=adm,
        json={"admin_remarks": "Stock verified for morning dispatch"},
    )
    assert approve_resp.status_code == 200, approve_resp.text
    approved = approve_resp.json()
    assert approved["status"] == "APPROVED"
    assert approved["has_shortage"] is False
    assert approved["admin_remarks"] == "Stock verified for morning dispatch"
    assert approved["approved_by_name"] == "Factory Admin"
    assert approved["items"][0]["approved_qty_pkts"] == 150
    assert approved["items"][0]["shortage_pkts"] == 0
    assert len(approved["reservations"]) == 1
    assert approved["reservations"][0]["status"] == "ACTIVE"
    assert approved["reservations"][0]["reserved_qty_pkts"] == 150

    # Verify PostgreSQL inventory_balances: physical on_hand stays 200, reserved=150, available=50
    bal = db_session.execute(
        select(InventoryBalance).where(InventoryBalance.pack_size_id == ids["mrk"])
    ).scalar_one()
    assert int(bal.on_hand_qty_base) == 200
    assert int(bal.reserved_qty_base) == 150
    assert int(bal.available_qty_base) == 50


def test_insufficient_stock_blocks_approval_and_prevents_negative_stock(
    client: TestClient, db_session: Session
) -> None:
    ids = _ids(db_session)
    sm_a = login_and_get_headers(client, "salesman_a")
    sm_b = login_and_get_headers(client, "salesman_b")
    adm = login_and_get_headers(client, "admin")
    admin_me = client.get("/api/v1/auth/me", headers=adm).json()

    # Give total 120 pkts physical, reserve 50 via Order 1 -> leaves strictly 70 available
    _grant_controlled_test_stock(db_session, admin_id=admin_me["id"], pack_size_id=ids["mrk"], add_pkts=70)
    ord1 = _create_order(client, sm_a, customer_id=ids["ret_a"], pack_size_id=ids["mrk"], qty_pkts=50)
    assert client.post(f"/api/v1/admin/orders/{ord1['id']}/approve", headers=adm, json={}).status_code == 200

    # Salesman B orders 100 pkts; physical is 120, but available is 70 -> 30 short!
    ord2 = _create_order(client, sm_b, customer_id=ids["dist_b"], pack_size_id=ids["mrk"], qty_pkts=100)
    fail_approve = client.post(
        f"/api/v1/admin/orders/{ord2['id']}/approve",
        headers=adm,
        json={},
    )
    assert fail_approve.status_code == 409
    err = fail_approve.json()["error"]
    assert err["code"] == "INSUFFICIENT_STOCK"
    assert err["details"]["items"][0]["requested_qty_pkts"] == 100
    assert err["details"]["items"][0]["on_hand_qty_pkts"] == 120
    assert err["details"]["items"][0]["reserved_qty_pkts"] == 50
    assert err["details"]["items"][0]["available_qty_pkts"] == 70
    assert err["details"]["items"][0]["shortage_pkts"] == 30

    # Verify zero corruption of reserved stock and order stays SUBMITTED
    bal = db_session.execute(
        select(InventoryBalance).where(InventoryBalance.pack_size_id == ids["mrk"])
    ).scalar_one()
    assert int(bal.reserved_qty_base) == 50
    assert int(bal.available_qty_base) == 70

    # Admin marks UNDER_REVIEW holding for production
    hold_resp = client.post(
        f"/api/v1/admin/orders/{ord2['id']}/review",
        headers=adm,
        json={"admin_remarks": "Short by 30 pkts; awaiting Batch PRD-002"},
    )
    assert hold_resp.status_code == 200
    assert hold_resp.json()["status"] == "UNDER_REVIEW"
    assert hold_resp.json()["has_shortage"] is True


def test_order_rejection_and_terminal_invalid_transitions(
    client: TestClient, db_session: Session
) -> None:
    ids = _ids(db_session)
    sm_a = login_and_get_headers(client, "salesman_a")
    adm = login_and_get_headers(client, "admin")

    order = _create_order(client, sm_a, customer_id=ids["ret_a"], pack_size_id=ids["mrk"], qty_pkts=20)

    # Rejection without valid reason (>=5 chars) blocked 422
    bad_reject = client.post(
        f"/api/v1/admin/orders/{order['id']}/reject",
        headers=adm,
        json={"reason": "no"},
    )
    assert bad_reject.status_code == 422

    # Valid rejection
    rej_resp = client.post(
        f"/api/v1/admin/orders/{order['id']}/reject",
        headers=adm,
        json={"reason": "Customer credit hold exceeded limit"},
    )
    assert rej_resp.status_code == 200
    rej = rej_resp.json()
    assert rej["status"] == "REJECTED"
    assert rej["rejection_reason"] == "Customer credit hold exceeded limit"

    # Prevent approving already rejected order
    reapprove = client.post(f"/api/v1/admin/orders/{order['id']}/approve", headers=adm, json={})
    assert reapprove.status_code == 409
    assert reapprove.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    # Prevent modifying already rejected order
    edit_rej = client.patch(
        f"/api/v1/admin/orders/{order['id']}",
        headers=adm,
        json={
            "items": [{"id": order["items"][0]["id"], "approved_qty_pkts": 10, "unit_price_paisa": 5000}],
            "reason": "Trying post-reject edit",
        },
    )
    assert edit_rej.status_code == 409

    # DB constraint prevents duplicate identical-state status history row
    try:
        db_session.execute(
            text(
                "INSERT INTO sales.sales_order_status_history (sales_order_id, from_status, to_status, changed_by, reason) "
                "VALUES (:oid, 'REJECTED', 'REJECTED', :uid, 'noop')"
            ),
            {"oid": order["id"], "uid": 1},
        )
        raise AssertionError("Expected PostgreSQL constraint to forbid from_status == to_status")
    except DBAPIError:
        db_session.rollback()


def test_duplicate_approval_and_post_approval_edit_lock(
    client: TestClient, db_session: Session
) -> None:
    ids = _ids(db_session)
    sm_a = login_and_get_headers(client, "salesman_a")
    adm = login_and_get_headers(client, "admin")

    order = _create_order(client, sm_a, customer_id=ids["ret_a"], pack_size_id=ids["mrk"], qty_pkts=40)
    first = client.post(f"/api/v1/admin/orders/{order['id']}/approve", headers=adm, json={})
    assert first.status_code == 200

    # Duplicate approval request must return 409 without double-reserving
    second = client.post(f"/api/v1/admin/orders/{order['id']}/approve", headers=adm, json={})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    bal = db_session.execute(
        select(InventoryBalance).where(InventoryBalance.pack_size_id == ids["mrk"])
    ).scalar_one()
    assert int(bal.reserved_qty_base) == 40

    # Editing after APPROVED is blocked
    edit_after = client.patch(
        f"/api/v1/admin/orders/{order['id']}",
        headers=adm,
        json={
            "items": [{"id": order["items"][0]["id"], "approved_qty_pkts": 30, "unit_price_paisa": 5000}],
            "reason": "Post-approval qty tweak",
        },
    )
    assert edit_after.status_code == 409

    # Duplicate status history count check
    hist_cnt = db_session.execute(
        select(func.count(SalesOrderStatusHistory.id)).where(
            SalesOrderStatusHistory.sales_order_id == order["id"],
            SalesOrderStatusHistory.to_status == "APPROVED",
        )
    ).scalar_one()
    assert hist_cnt == 1


def test_qty_and_price_modifications_recalculate_totals_and_preserve_originals(
    client: TestClient, db_session: Session
) -> None:
    ids = _ids(db_session)
    sm_a = login_and_get_headers(client, "salesman_a")
    sm_b = login_and_get_headers(client, "salesman_b")
    adm = login_and_get_headers(client, "admin")

    # Retail A (TN intra-state): 150 pkts @ ₹50.00 ordered; stock is 50 pkts
    ord_a = _create_order(client, sm_a, customer_id=ids["ret_a"], pack_size_id=ids["mrk"], qty_pkts=150)
    item_id = ord_a["items"][0]["id"]

    # Modifying qty or price without >=5 char reason rejected (422)
    no_reason = client.patch(
        f"/api/v1/admin/orders/{ord_a['id']}",
        headers=adm,
        json={
            "items": [{"id": item_id, "approved_qty_pkts": 50, "unit_price_paisa": 4800}],
            "reason": "x",
        },
    )
    assert no_reason.status_code == 422

    # Valid Admin modification: reduce qty 150 -> 50 (covers stock) AND unit price ₹50 -> ₹48 (4800 paise)
    mod_resp = client.patch(
        f"/api/v1/admin/orders/{ord_a['id']}",
        headers=adm,
        json={
            "items": [{"id": item_id, "approved_qty_pkts": 50, "unit_price_paisa": 4800}],
            "admin_remarks": "Adjusted to available 50 pkts with festival discount ₹2/pkt",
            "reason": "Customer agreed to 50 pkts at Rs 48 promotional rate",
        },
    )
    assert mod_resp.status_code == 200, mod_resp.text
    mod = mod_resp.json()
    assert mod["status"] == "UNDER_REVIEW"
    assert mod["has_shortage"] is False
    item = mod["items"][0]
    # Original salesman ordered qty (150) and original price (5000) remain preserved!
    assert item["ordered_qty_pkts"] == 150
    assert item["approved_qty_pkts"] == 50
    assert item["effective_qty_pkts"] == 50
    assert item["original_unit_price_paisa"] == 5000
    assert item["unit_price_paisa"] == 4800
    assert item["is_qty_modified"] is True
    assert item["is_price_modified"] is True
    # 50 * 4800 = 240,000 paise (₹2,400.00); 2.5% CGST = 6,000; 2.5% SGST = 6,000; grand = 252,000
    assert mod["taxable_total_paisa"] == 240000
    assert mod["tax_estimate"]["cgst_total_paisa"] == 6000
    assert mod["tax_estimate"]["sgst_total_paisa"] == 6000
    assert mod["tax_estimate"]["igst_total_paisa"] == 0
    assert mod["tax_estimate"]["grand_total_paisa"] == 252000

    # Now approve revised order cleanly (50 available >= 50 requested)
    ok_approve = client.post(f"/api/v1/admin/orders/{ord_a['id']}/approve", headers=adm, json={})
    assert ok_approve.status_code == 200
    assert ok_approve.json()["status"] == "APPROVED"

    # Also verify Distributor B (KA inter-state) recalculates IGST properly when qty adjusted
    ord_b = _create_order(client, sm_b, customer_id=ids["dist_b"], pack_size_id=ids["mrk"], qty_pkts=100)
    mod_b = client.patch(
        f"/api/v1/admin/orders/{ord_b['id']}",
        headers=adm,
        json={
            "items": [{"id": ord_b["items"][0]["id"], "approved_qty_pkts": 40, "unit_price_paisa": 5000}],
            "reason": "Partial stock quote pending",
        },
    ).json()
    # 40 * 5000 = 200,000; 5% IGST = 10,000; grand = 210,000
    assert mod_b["tax_estimate"]["supply_type"] == "INTER_STATE"
    assert mod_b["tax_estimate"]["cgst_total_paisa"] == 0
    assert mod_b["tax_estimate"]["sgst_total_paisa"] == 0
    assert mod_b["tax_estimate"]["igst_total_paisa"] == 10000
    assert mod_b["tax_estimate"]["grand_total_paisa"] == 210000


def test_unauthorized_modifications_blocked_across_roles(
    client: TestClient, db_session: Session
) -> None:
    ids = _ids(db_session)
    sm_a = login_and_get_headers(client, "salesman_a")
    sm_b = login_and_get_headers(client, "salesman_b")
    aud = login_and_get_headers(client, "auditor")
    own = login_and_get_headers(client, "owner")
    sup = login_and_get_headers(client, "supervisor")

    order = _create_order(client, sm_a, customer_id=ids["ret_a"], pack_size_id=ids["mrk"], qty_pkts=10)
    oid = order["id"]
    item_id = order["items"][0]["id"]

    # No salesman, auditor, owner, or supervisor can mutate/approve/reject/edit prices
    for headers in (sm_a, sm_b, aud, own, sup):
        assert client.post(f"/api/v1/admin/orders/{oid}/approve", headers=headers, json={}).status_code == 403
        assert (
            client.post(
                f"/api/v1/admin/orders/{oid}/reject",
                headers=headers,
                json={"reason": "Unauthorized reject"},
            ).status_code
            == 403
        )
        assert (
            client.patch(
                f"/api/v1/admin/orders/{oid}",
                headers=headers,
                json={
                    "items": [{"id": item_id, "approved_qty_pkts": 5, "unit_price_paisa": 100}],
                    "reason": "Unauthorized price override",
                },
            ).status_code
            == 403
        )

    # Salesman A cannot view internal factory audit trail or reservation IDs
    sm_detail = client.get(f"/api/v1/orders/{oid}", headers=sm_a).json()
    assert sm_detail["audit_trail"] == []
    assert sm_detail["reservations"] == []


def test_concurrent_approval_attempts_prevent_overselling_and_duplicate_history(
    client: TestClient, db_session: Session
) -> None:
    ids = _ids(db_session)
    sm_a = login_and_get_headers(client, "salesman_a")
    sm_b = login_and_get_headers(client, "salesman_b")
    adm = login_and_get_headers(client, "admin")
    admin_me = client.get("/api/v1/auth/me", headers=adm).json()

    # Set total physical stock to 100 pkts (50 seed + 50 controlled test stock)
    _grant_controlled_test_stock(db_session, admin_id=admin_me["id"], pack_size_id=ids["mrk"], add_pkts=50)

    # Order 1 wants 80, Order 2 wants 70 (150 total > 100 physical!)
    ord1 = _create_order(client, sm_a, customer_id=ids["ret_a"], pack_size_id=ids["mrk"], qty_pkts=80)
    ord2 = _create_order(client, sm_b, customer_id=ids["dist_b"], pack_size_id=ids["mrk"], qty_pkts=70)
    db_session.commit()

    def thread_safe_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    # Temporarily route requests to independent pooled sessions per thread
    prev_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = thread_safe_get_db
    try:
        def approve_order(order_id: int) -> int:
            with TestClient(app) as c:
                r = c.post(f"/api/v1/admin/orders/{order_id}/approve", headers=adm, json={})
                return r.status_code

        # A) Two competing orders sharing scarce 100-pkt stock simultaneously
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(approve_order, ord1["id"])
            f2 = pool.submit(approve_order, ord2["id"])
            statuses_ab = sorted([f1.result(), f2.result()])

        assert statuses_ab == [200, 409], f"Expected one 200 and one 409 conflict, got {statuses_ab}"

        # B) Two simultaneous approval requests for the SAME newly created 15-pkt order
        ord3 = _create_order(client, sm_a, customer_id=ids["ret_a"], pack_size_id=ids["mrk"], qty_pkts=15)
        with ThreadPoolExecutor(max_workers=2) as pool:
            s1 = pool.submit(approve_order, ord3["id"])
            s2 = pool.submit(approve_order, ord3["id"])
            same_statuses = sorted([s1.result(), s2.result()])

        assert same_statuses == [200, 409], f"Expected single approval and conflict, got {same_statuses}"
    finally:
        if prev_override is not None:
            app.dependency_overrides[get_db] = prev_override

    db_session.expire_all()
    bal = db_session.execute(
        select(InventoryBalance).where(InventoryBalance.pack_size_id == ids["mrk"])
    ).scalar_one()
    # Reserved must NEVER exceed physical 100 (either 80+15=95 or 70+15=85)
    assert int(bal.reserved_qty_base) in {85, 95}
    assert int(bal.reserved_qty_base) <= int(bal.on_hand_qty_base)

    # Active reservations on ord3 must be strictly 1
    res_count = db_session.execute(
        select(func.count(StockReservation.id)).where(
            StockReservation.sales_order_id == ord3["id"],
            StockReservation.status == "ACTIVE",
        )
    ).scalar_one()
    assert res_count == 1


def test_salesman_correction_resubmit_sync_audit_trail_and_cancel_release(
    client: TestClient, db_session: Session
) -> None:
    ids = _ids(db_session)
    sm_a = login_and_get_headers(client, "salesman_a")
    sm_b = login_and_get_headers(client, "salesman_b")
    adm = login_and_get_headers(client, "admin")
    aud = login_and_get_headers(client, "auditor")

    # Salesman A submits 100 pkts (stock is 50 -> flagged shortage)
    order = _create_order(client, sm_a, customer_id=ids["ret_a"], pack_size_id=ids["mrk"], qty_pkts=100)
    oid = order["id"]

    # Admin requests correction from salesman
    corr_resp = client.post(
        f"/api/v1/admin/orders/{oid}/request-correction",
        headers=adm,
        json={"reason": "Only 50 pkts available today; please confirm 50 pkts with shop"},
    )
    assert corr_resp.status_code == 200
    assert corr_resp.json()["status"] == "CORRECTION_REQUESTED"

    # Salesman A polls My Orders / Detail and immediately sees CORRECTION_REQUESTED + admin remarks
    sm_view = client.get(f"/api/v1/orders/{oid}", headers=sm_a).json()
    assert sm_view["status"] == "CORRECTION_REQUESTED"
    assert "Only 50 pkts available" in (sm_view["admin_remarks"] or "")

    # Salesman B cannot resubmit Salesman A's order
    forbidden_resub = client.put(
        f"/api/v1/orders/{oid}",
        headers=sm_b,
        json={"items": [{"pack_size_id": ids["mrk"], "ordered_qty_pkts": 50}]},
    )
    assert forbidden_resub.status_code == 403

    # Salesman A updates quantity to 50 and resubmits cleanly (price spoof ignored)
    resub_resp = client.put(
        f"/api/v1/orders/{oid}",
        headers=sm_a,
        json={
            "notes": "Confirmed 50 pkts immediate drop with Retailer A",
            "items": [{"pack_size_id": ids["mrk"], "ordered_qty_pkts": 50, "unit_price_paisa": 1}],
        },
    )
    assert resub_resp.status_code == 200, resub_resp.text
    resub = resub_resp.json()
    assert resub["status"] == "SUBMITTED"
    assert resub["has_shortage"] is False
    assert resub["items"][0]["unit_price_paisa"] == 5000  # Server-side price enforced!

    # Admin filters & approves 50 pkts
    summary = client.get("/api/v1/admin/orders/summary", headers=adm).json()
    assert summary["submitted_count"] == 1
    assert summary["pending_verification_count"] == 1

    filt = client.get(
        f"/api/v1/admin/orders?customer_id={ids['ret_a']}&salesman_id={resub['salesman_id']}&search={resub['order_number']}",
        headers=adm,
    ).json()
    assert filt["total"] == 1

    app_resp = client.post(
        f"/api/v1/admin/orders/{oid}/approve",
        headers=adm,
        json={"admin_remarks": "Cleared 50 pkts for evening truck"},
    )
    assert app_resp.status_code == 200
    assert app_resp.json()["status"] == "APPROVED"

    # Salesman refreshes mobile view -> immediately sees APPROVED & remarks without resubmitting
    sm_synced = client.get(f"/api/v1/orders/{oid}", headers=sm_a).json()
    assert sm_synced["status"] == "APPROVED"
    assert sm_synced["admin_remarks"] == "Cleared 50 pkts for evening truck"
    assert [h["to_status"] for h in sm_synced["status_history"]] == [
        "SUBMITTED",
        "CORRECTION_REQUESTED",
        "SUBMITTED",
        "APPROVED",
    ]

    # Pre-invoice cancellation by Admin releases reservation cleanly
    # (First check Salesman cannot cancel an APPROVED order!)
    assert (
        client.post(
            f"/api/v1/orders/{oid}/cancel",
            headers=sm_a,
            json={"reason": "Trying salesman cancel post-approval"},
        ).status_code
        == 409
    )

    cancel_resp = client.post(
        f"/api/v1/admin/orders/{oid}/cancel",
        headers=adm,
        json={"reason": "Customer shop closed due to local bandh"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"

    bal = db_session.execute(
        select(InventoryBalance).where(InventoryBalance.pack_size_id == ids["mrk"])
    ).scalar_one()
    assert int(bal.reserved_qty_base) == 0
    assert int(bal.available_qty_base) == 50

    # Verify Auditor sees full immutable audit trail including stock reserve & release
    aud_detail = client.get(f"/api/v1/admin/orders/{oid}", headers=aud).json()
    actions = [a["action"] for a in aud_detail["audit_trail"]]
    for expected_action in (
        "ORDER_SUBMITTED",
        "ORDER_CORRECTION_REQ",
        "ORDER_RESUBMITTED",
        "ORDER_APPROVED",
        "STOCK_RESERVED",
        "ORDER_CANCELLED",
        "STOCK_RESERVATION_RELEASED",
    ):
        assert expected_action in actions


def test_phase5_12_step_final_acceptance_scenario_end_to_end(
    client: TestClient, db_session: Session
) -> None:
    """Execute the exact 12-step Phase 5 Final Acceptance Scenario with controlled stock."""
    ids = _ids(db_session)
    adm = login_and_get_headers(client, "admin")
    admin_me = client.get("/api/v1/auth/me", headers=adm).json()

    # Controlled test inventory sufficient for approving 150 packets (50 opening + 150 controlled test)
    _grant_controlled_test_stock(
        db_session, admin_id=admin_me["id"], pack_size_id=ids["mrk"], add_pkts=150
    )

    # Steps 1-3: Salesman A logs in, selects Retailer A, submits 150 Murukku 200 g packets
    sm_a = login_and_get_headers(client, "salesman_a")
    sm_customers = client.get("/api/v1/sales/customers", headers=sm_a).json()
    assert any(c["id"] == ids["ret_a"] and c["name"] == "Retailer A" for c in sm_customers)
    order = _create_order(
        client,
        sm_a,
        customer_id=ids["ret_a"],
        pack_size_id=ids["mrk"],
        qty_pkts=150,
        notes="Acceptance scenario delivery",
    )
    oid = order["id"]
    assert order["status"] == "SUBMITTED"
    assert order["has_shortage"] is False

    # Steps 4-7: Admin logs in, sees incoming order, opens details & checks all fields/stock
    queue = client.get("/api/v1/admin/orders?pending_verification=true", headers=adm).json()
    assert queue["total"] == 1
    assert queue["items"][0]["order_number"] == order["order_number"]

    detail = client.get(f"/api/v1/admin/orders/{oid}", headers=adm).json()
    assert detail["customer_name"] == "Retailer A"
    assert detail["salesman_name"] == "Salesman A"
    assert detail["items"][0]["ordered_qty_pkts"] == 150
    assert detail["items"][0]["unit_price_paisa"] == 5000
    assert detail["items"][0]["live_on_hand_pkts"] == 200
    assert detail["items"][0]["live_available_pkts"] == 200

    # Steps 8-9: Admin approves with remark after modifying optional verified quantity (150 -> 140)
    mod = client.patch(
        f"/api/v1/admin/orders/{oid}",
        headers=adm,
        json={
            "items": [{"id": detail["items"][0]["id"], "approved_qty_pkts": 140, "unit_price_paisa": 5000}],
            "admin_remarks": "Packed 7 cartons (140 pkts) for afternoon dispatch",
            "reason": "Rounded to 7 full cartons per Retailer A call",
            "expected_version": detail["version"],
        },
    ).json()
    approved = client.post(
        f"/api/v1/admin/orders/{oid}/approve",
        headers=adm,
        json={
            "admin_remarks": "Packed 7 cartons (140 pkts) for afternoon dispatch",
            "reason": "Stock covered and approved",
            "expected_version": mod["version"],
        },
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    # Steps 10-11: Salesman A refreshes mobile My Orders & Detail views without resubmitting
    sm_list = client.get("/api/v1/orders/my", headers=sm_a).json()
    assert sm_list["items"][0]["status"] == "APPROVED"
    assert sm_list["items"][0]["total_packets"] == 140

    sm_detail = client.get(f"/api/v1/orders/{oid}", headers=sm_a).json()
    assert sm_detail["status"] == "APPROVED"
    assert sm_detail["admin_remarks"] == "Packed 7 cartons (140 pkts) for afternoon dispatch"
    assert sm_detail["items"][0]["ordered_qty_pkts"] == 150
    assert sm_detail["items"][0]["approved_qty_pkts"] == 140

    # Step 12: Complete PostgreSQL order history, active reservation & audit trail
    db_detail = client.get(f"/api/v1/admin/orders/{oid}", headers=adm).json()
    assert [h["to_status"] for h in db_detail["status_history"]] == [
        "SUBMITTED",
        "UNDER_REVIEW",
        "APPROVED",
    ]
    assert db_detail["reservations"][0]["reserved_qty_pkts"] == 140
    assert db_detail["reservations"][0]["status"] == "ACTIVE"
    audit_actions = [a["action"] for a in db_detail["audit_trail"]]
    for expected in ("ORDER_SUBMITTED", "ORDER_QTY_MODIFIED", "ORDER_APPROVED", "STOCK_RESERVED"):
        assert expected in audit_actions

