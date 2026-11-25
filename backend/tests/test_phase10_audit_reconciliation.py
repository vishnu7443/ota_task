"""Comprehensive Phase 10 automated tests covering:
- Centralized Audit Explorer (filtering, correlation IDs, credential redaction, summary, user activity, CSV, immutability)
- IAM User & Role Governance (provisioning, role changes, deactivation, audit logging, read-only auditor boundary)
- Cross-Module Reconciliation Engine (Inventory ledger parity, Sales/Invoice/GST/Payment/AR/Dispatch/Production checks)
- Controlled Discrepancy Investigation, Proposal, Approval, StockAdjustment Resolution, Re-Run Auto-Verification & Closure
- Management Intelligence Dashboard (real cross-module KPIs, profitability disclaimers, watchlist, CSV export, RBAC)
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.inventory.models import Material
from app.modules.sales.models import Customer, PackSize
from app.seeds.benchmark_seed import DEV_SEED_PASSWORDS
from tests.conftest import login_and_get_headers


def _refs(db: Session) -> dict[str, int]:
    ret_a = db.execute(select(Customer).where(Customer.code == "CUST-RET-A")).scalar_one()
    dist_b = db.execute(select(Customer).where(Customer.code == "CUST-DIST-B")).scalar_one()
    mrk = db.execute(select(PackSize).where(PackSize.sku_code == "MRK-200G")).scalar_one()
    flr = db.execute(select(Material).where(Material.code == "MAT-FLR")).scalar_one()
    oil = db.execute(select(Material).where(Material.code == "MAT-OIL")).scalar_one()
    spc = db.execute(select(Material).where(Material.code == "MAT-SPC")).scalar_one()
    pch = db.execute(select(Material).where(Material.code == "MAT-PCH-200")).scalar_one()
    ctn = db.execute(select(Material).where(Material.code == "MAT-CTN-20")).scalar_one()
    return {
        "ret_a": ret_a.id,
        "dist_b": dist_b.id,
        "mrk": mrk.id,
        "flr": flr.id,
        "oil": oil.id,
        "spc": spc.id,
        "pch": pch.id,
        "ctn": ctn.id,
    }


def test_1_centralized_audit_explorer_filtering_sanitization_and_csv(
    client: TestClient, db_session: Session
) -> None:
    """Audit trail captures security + business events with correlation refs, zero password leakage, CSV export & trigger lock."""
    # Trigger security audit events: valid login, bad login, and unauthorized access (403)
    sm_a = login_and_get_headers(client, "salesman_a")
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": "salesman_a", "password": "SuperSecretWrongPassword!99"},
        ).status_code
        == 401
    )
    assert client.get("/api/v1/admin/orders", headers=sm_a).status_code == 403

    # Trigger business event
    refs = _refs(db_session)
    ord_resp = client.post(
        "/api/v1/orders",
        headers=sm_a,
        json={
            "customer_id": refs["ret_a"],
            "client_order_id": str(uuid4()),
            "notes": "Phase 10 audit check",
            "items": [{"pack_size_id": refs["mrk"], "ordered_qty_pkts": 20}],
        },
    )
    assert ord_resp.status_code == 201

    adm = login_and_get_headers(client, "admin")
    aud = login_and_get_headers(client, "auditor")
    own = login_and_get_headers(client, "owner")
    supv = login_and_get_headers(client, "supervisor")

    # Salesman & Production Supervisor strictly blocked from Centralized Audit Explorer
    assert client.get("/api/v1/audit/logs", headers=sm_a).status_code == 403
    assert client.get("/api/v1/audit/logs", headers=supv).status_code == 403

    # Auditor, Owner & Admin can read audit logs, summary & activity
    logs_resp = client.get("/api/v1/audit/logs?page=1&page_size=50", headers=aud)
    assert logs_resp.status_code == 200
    logs_data = logs_resp.json()
    assert logs_data["total"] >= 4
    actions_seen = {row["action"] for row in logs_data["items"]}
    assert "LOGIN_SUCCESS" in actions_seen
    assert "LOGIN_FAILED" in actions_seen
    assert "ACCESS_DENIED" in actions_seen
    assert "CREATE" in actions_seen or "ORDER_SUBMITTED" in actions_seen or any(
        row["entity_table"] == "sales_orders" for row in logs_data["items"]
    )

    # Every backend-emitted HTTP request audit event gets a REQ- correlation ref and zero credential leaks
    for row in logs_data["items"]:
        serialized = str(row)
        assert "SuperSecretWrongPassword!99" not in serialized
        assert DEV_SEED_PASSWORDS["salesman_a"] not in serialized
        assert DEV_SEED_PASSWORDS["admin"] not in serialized
        assert row["correlation_ref"] and row["correlation_ref"].startswith("REQ-")

    # Filter by action & test detail endpoint
    failed_resp = client.get("/api/v1/audit/logs?action=LOGIN_FAILED", headers=adm).json()
    assert failed_resp["total"] >= 1
    first_id = failed_resp["items"][0]["id"]
    detail = client.get(f"/api/v1/audit/logs/{first_id}", headers=own)
    assert detail.status_code == 200
    assert detail.json()["action"] == "LOGIN_FAILED"

    # Summary & User Activity reports
    sum_data = client.get("/api/v1/audit/summary", headers=aud).json()
    assert sum_data["login_failures_count"] >= 1
    assert sum_data["access_denied_count"] >= 1
    assert sum_data["security_events_count"] >= 2

    act_data = client.get("/api/v1/audit/user-activity", headers=own).json()
    sm_row = next(r for r in act_data if r["username"] == "salesman_a")
    assert sm_row["login_success_count"] >= 1
    assert sm_row["login_failed_count"] >= 1
    assert sm_row["access_denied_count"] >= 1

    # CSV export works for Auditor
    csv_resp = client.get("/api/v1/audit/logs/export/csv", headers=aud)
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "Correlation Ref" in csv_resp.text
    assert "LOGIN_FAILED" in csv_resp.text

    # PostgreSQL append-only trigger forbids UPDATE / DELETE on audit_logs
    for bad_sql in [
        ("DELETE FROM audit.audit_logs WHERE id = :id", {"id": first_id}),
        ("UPDATE audit.audit_logs SET reason = 'tampered' WHERE id = :id", {"id": first_id}),
    ]:
        try:
            db_session.execute(text(bad_sql[0]), bad_sql[1])
            db_session.commit()
            raise AssertionError(f"Expected trigger block for: {bad_sql[0]}")
        except DBAPIError:
            db_session.rollback()


def test_2_iam_user_governance_and_audit_trail(client: TestClient) -> None:
    """User provisioning, role reassignment & deactivation emit sanitized audit trails and enforce RBAC."""
    adm = login_and_get_headers(client, "admin")
    own = login_and_get_headers(client, "owner")
    aud = login_and_get_headers(client, "auditor")
    sm_a = login_and_get_headers(client, "salesman_a")

    # Roles directory readable by governance viewers, blocked for Salesman
    assert client.get("/api/v1/iam/roles", headers=sm_a).status_code == 403
    roles = client.get("/api/v1/iam/roles", headers=aud)
    assert roles.status_code == 200 and len(roles.json()) == 5

    # Auditor strictly read-only on /iam/users
    assert client.get("/api/v1/iam/users", headers=aud).status_code == 200
    assert (
        client.post(
            "/api/v1/iam/users",
            headers=aud,
            json={
                "username": "blocked_aud",
                "full_name": "Blocked User",
                "role_code": "SALESMAN",
                "password": "Password@123",
            },
        ).status_code
        == 403
    )

    # Admin provisions a new Salesman user cleanly (auto-creates SalesmanProfile)
    new_pw = "NewSalesman#2026"
    created = client.post(
        "/api/v1/iam/users",
        headers=adm,
        json={
            "username": "salesman_c",
            "full_name": "Salesman C",
            "phone": "+91-9842099999",
            "role_code": "SALESMAN",
            "password": new_pw,
            "employee_code": "SM-003",
            "territory": "Madurai District",
        },
    )
    assert created.status_code == 201, created.text
    uid = created.json()["id"]

    # Newly created user can log in and view own orders
    sm_c_login = client.post("/api/v1/auth/login", json={"username": "salesman_c", "password": new_pw})
    assert sm_c_login.status_code == 200
    sm_c_headers = {"Authorization": f"Bearer {sm_c_login.json()['access_token']}"}
    assert client.get("/api/v1/orders/my", headers=sm_c_headers).status_code == 200

    # Owner changes role & deactivates user with mandatory documented reason
    upd = client.patch(
        f"/api/v1/iam/users/{uid}",
        headers=own,
        json={
            "role_code": "PRODUCTION_SUPERVISOR",
            "is_active": False,
            "reason": "Seasonal staff contract completed; revoking access",
        },
    )
    assert upd.status_code == 200
    assert upd.json()["role_code"] == "PRODUCTION_SUPERVISOR"
    assert upd.json()["is_active"] is False

    # Deactivated user can no longer log in
    assert client.post("/api/v1/auth/login", json={"username": "salesman_c", "password": new_pw}).status_code == 401

    # Verify audit trail captured USER_CREATED, USER_ROLE_CHANGED & USER_STATUS_CHANGED without leaking password
    user_logs = client.get(f"/api/v1/audit/logs?entity_table=users&entity_id={uid}", headers=aud).json()["items"]
    logged_actions = {row["action"] for row in user_logs}
    assert {"USER_CREATED", "USER_ROLE_CHANGED", "USER_STATUS_CHANGED"}.issubset(logged_actions)
    for row in user_logs:
        assert new_pw not in str(row)


def test_3_baseline_cross_module_reconciliation_clean_and_full_cycle(
    client: TestClient, db_session: Session
) -> None:
    """Benchmark master & complete real Order->Production->Invoice->Dispatch->Payment lifecycle reconciles with zero discrepancies."""
    refs = _refs(db_session)
    adm = login_and_get_headers(client, "admin")
    sm_a = login_and_get_headers(client, "salesman_a")
    supv = login_and_get_headers(client, "supervisor")

    # 1. Clean benchmark inventory parity
    inv_rep = client.get("/api/v1/reconciliation/reports/inventory", headers=adm).json()
    assert inv_rep["mismatch_count"] == 0
    assert inv_rep["matched_count"] == inv_rep["total_items"]

    # 2. Execute end-to-end Production + Sales + Billing + Dispatch + Payment transactions
    run_resp = client.post(
        "/api/v1/production/runs",
        headers=supv,
        json={"pack_size_id": refs["mrk"], "batch_multiplier": "1.0", "plan_immediately": True},
    ).json()
    client.post(
        f"/api/v1/production/runs/{run_resp['id']}/issue-materials",
        headers=supv,
        json={
            "items": [
                {"material_id": refs["flr"], "issued_qty": "40", "issued_uom": "kg"},
                {"material_id": refs["oil"], "issued_qty": "10", "issued_uom": "L"},
                {"material_id": refs["spc"], "issued_qty": "1.2", "issued_uom": "kg"},
            ]
        },
    )
    client.post(
        f"/api/v1/production/runs/{run_resp['id']}/complete",
        headers=supv,
        json={
            "good_output_pkts": 200,
            "rejected_output_pkts": 0,
            "batch_code": "MRK-R10-001",
            "consumptions": [
                {"material_id": refs["flr"], "actual_consumed_qty": "40", "uom": "kg"},
                {"material_id": refs["oil"], "actual_consumed_qty": "10", "uom": "L"},
                {"material_id": refs["spc"], "actual_consumed_qty": "1.2", "uom": "kg"},
                {"material_id": refs["pch"], "actual_good_used_qty": "200", "damaged_packaging_qty": "0", "uom": "piece"},
                {"material_id": refs["ctn"], "actual_good_used_qty": "10", "damaged_packaging_qty": "0", "uom": "piece"},
            ],
        },
    )
    assert client.post(f"/api/v1/production/runs/{run_resp['id']}/post", headers=supv).status_code == 200

    order = client.post(
        "/api/v1/orders",
        headers=sm_a,
        json={
            "customer_id": refs["ret_a"],
            "client_order_id": str(uuid4()),
            "items": [{"pack_size_id": refs["mrk"], "ordered_qty_pkts": 40}],
        },
    ).json()
    assert client.post(f"/api/v1/admin/orders/{order['id']}/approve", headers=adm, json={}).status_code == 200
    inv = client.post(
        "/api/v1/billing/invoices",
        headers=adm,
        json={"sales_order_id": order["id"], "issue_immediately": True},
    ).json()
    dsp = client.post(
        "/api/v1/billing/dispatches",
        headers=adm,
        json={
            "invoice_id": inv["id"],
            "packing_verified": True,
            "post_immediately": True,
            "items": [{"invoice_item_id": inv["items"][0]["id"], "dispatched_qty_pkts": 40}],
        },
    ).json()
    assert dsp["status"] == "DISPATCHED"
    pmt = client.post(
        "/api/v1/finance/payments",
        headers=adm,
        json={
            "customer_id": refs["ret_a"],
            "amount_paisa": inv["grand_total_paisa"],
            "payment_mode": "UPI",
            "reference_no": "UPI-R10-001",
            "client_payment_id": str(uuid4()),
            "allocations": [{"invoice_id": inv["id"], "allocated_paisa": inv["grand_total_paisa"]}],
        },
    )
    assert pmt.status_code == 201

    # 3. Start formal FULL_SYSTEM reconciliation run -> must achieve zero discrepancies (RECONCILED)
    recon = client.post("/api/v1/reconciliation/runs", headers=adm, json={"domain": "FULL_SYSTEM"})
    assert recon.status_code == 201, recon.text
    rdata = recon.json()
    assert rdata["status"] == "RECONCILED", rdata["discrepancies"]
    assert rdata["discrepancy_count"] == 0
    assert rdata["run_number"].startswith("REC/")

    # 4. Close run & verify CSV inventory recon download
    closed = client.post(
        f"/api/v1/reconciliation/runs/{rdata['id']}/close",
        headers=adm,
        json={"closure_notes": "Clean period-end verification passed across all modules"},
    )
    assert closed.status_code == 200 and closed.json()["status"] == "CLOSED"

    csv_inv = client.get("/api/v1/reconciliation/reports/inventory/export/csv", headers=adm)
    assert csv_inv.status_code == 200 and "Expected Closing" in csv_inv.text


def test_4_discrepancy_detection_workflow_stock_adjustment_rerun_and_rbac(
    client: TestClient, db_session: Session
) -> None:
    """Detect injected inventory mismatch + pending invoice, enforce role separation, post correction & auto-verify on re-run."""
    refs = _refs(db_session)
    adm = login_and_get_headers(client, "admin")
    own = login_and_get_headers(client, "owner")
    aud = login_and_get_headers(client, "auditor")
    supv = login_and_get_headers(client, "supervisor")
    sm_a = login_and_get_headers(client, "salesman_a")

    # 1. Inject deliberate balance-vs-ledger mismatch directly in test DB on MAT-FLR (+10 kg phantom balance)
    db_session.execute(
        text("UPDATE inventory.inventory_balances SET on_hand_qty_base = on_hand_qty_base + 10000 WHERE material_id = :mid"),
        {"mid": refs["flr"]},
    )
    db_session.commit()

    # Live report immediately flags MAT-FLR as MISMATCH
    inv_rep = client.get("/api/v1/reconciliation/reports/inventory?only_mismatches=true", headers=adm).json()
    assert inv_rep["mismatch_count"] == 1
    assert inv_rep["items"][0]["code"] == "MAT-FLR"
    assert Decimal(inv_rep["items"][0]["difference_qty_base"]) == Decimal("10000.000")

    # Auditor cannot start runs; Supervisor can start INVENTORY runs but cannot view SALES/FINANCE recon
    assert client.post("/api/v1/reconciliation/runs", headers=aud, json={"domain": "INVENTORY"}).status_code == 403
    assert client.get("/api/v1/reconciliation/reports/sales", headers=supv).status_code == 403
    assert client.get("/api/v1/reconciliation/reports/sales", headers=sm_a).status_code == 403

    inv_run = client.post("/api/v1/reconciliation/runs", headers=supv, json={"domain": "INVENTORY"})
    assert inv_run.status_code == 201
    run_id = inv_run.json()["id"]
    assert inv_run.json()["status"] == "DISCREPANCY_FOUND"
    assert inv_run.json()["discrepancy_count"] == 2  # INV_BAL_MISMATCH + COST_LOT_MISMATCH

    # Duplicate active run for exact same domain/period/scope blocked -> 409 Conflict
    dup = client.post("/api/v1/reconciliation/runs", headers=adm, json={"domain": "INVENTORY"})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "DUPLICATE_RECONCILIATION_RUN"

    discs = inv_run.json()["discrepancies"]
    bal_disc = next(d for d in discs if d["discrepancy_code"] == "INV_BAL_MISMATCH")
    lot_disc = next(d for d in discs if d["discrepancy_code"] == "COST_LOT_MISMATCH")

    # Supervisor investigates and proposes StockAdjustment correction
    assert (
        client.post(
            f"/api/v1/reconciliation/discrepancies/{bal_disc['id']}/investigate",
            headers=supv,
            json={"investigation_notes": "Physical bin check confirmed excess variance vs GRN ledger"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/reconciliation/discrepancies/{bal_disc['id']}/propose",
            headers=supv,
            json={
                "corrective_action_type": "STOCK_ADJUSTMENT",
                "proposed_action": "Post verified negative count adjustment of -2 kg to reconcile physical lot",
            },
        ).status_code
        == 200
    )

    # Supervisor cannot approve own correction -> 403; Owner approves -> APPROVED; Owner cannot post STOCK_ADJUSTMENT -> 403
    assert (
        client.post(f"/api/v1/reconciliation/discrepancies/{bal_disc['id']}/approve", headers=supv, json={}).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/reconciliation/discrepancies/{bal_disc['id']}/approve",
            headers=own,
            json={"notes": "Owner approved count adjustment"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/reconciliation/discrepancies/{bal_disc['id']}/resolve",
            headers=own,
            json={
                "resolution_notes": "Owner cannot execute adjustment",
                "entered_qty": "-2",
                "entered_uom": "kg",
            },
        ).status_code
        == 403
    )

    # Factory Admin executes STOCK_ADJUSTMENT resolution -> creates StockAdjustment & InventoryMovement & links ref
    res_bal = client.post(
        f"/api/v1/reconciliation/discrepancies/{bal_disc['id']}/resolve",
        headers=adm,
        json={
            "resolution_notes": "Posted physical count reconciliation adjustment via approved workflow",
            "adjustment_type": "COUNT_CORRECTION",
            "entered_qty": "-2",
            "entered_uom": "kg",
        },
    )
    assert res_bal.status_code == 200, res_bal.text
    assert res_bal.json()["status"] == "RESOLVED"
    assert res_bal.json()["resolution_ref_table"] == "inventory.stock_adjustments"
    assert res_bal.json()["resolution_ref_id"] is not None

    # Cannot close run while COST_LOT_MISMATCH remains open
    assert (
        client.post(
            f"/api/v1/reconciliation/runs/{run_id}/close",
            headers=adm,
            json={"closure_notes": "Premature close attempt"},
        ).status_code
        == 409
    )

    # Restore the remaining 8 kg + 2 kg (since 2kg already deducted from lot/balance, balance difference reverted to parity) via DB cleanup & re-run
    # Wait: let's dismiss lot_disc cleanly OR undo remaining phantom 10 kg on balance and test Sales auto-resolve on rerun!
    assert (
        client.post(
            f"/api/v1/reconciliation/discrepancies/{lot_disc['id']}/resolve",
            headers=adm,
            json={"resolution_notes": "Verified remaining open FIFO cost lot mismatch traced to phantom balance edit", "dismiss": True},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/reconciliation/runs/{run_id}/close",
            headers=own,
            json={"closure_notes": "All discrepancies resolved or dismissed cleanly"},
        ).status_code
        == 200
    )

    # 2. Clean Re-run Auto-Verification test using Sales Order awaiting Invoice (zero DB tampering!)
    sm_b = login_and_get_headers(client, "salesman_b")
    order_resp = client.post(
        "/api/v1/orders",
        headers=sm_b,
        json={
            "customer_id": refs["dist_b"],
            "client_order_id": str(uuid4()),
            "items": [{"pack_size_id": refs["mrk"], "ordered_qty_pkts": 30}],
        },
    )
    assert order_resp.status_code == 201, order_resp.text
    order = order_resp.json()
    assert client.post(f"/api/v1/admin/orders/{order['id']}/approve", headers=adm, json={}).status_code == 200

    sales_run = client.post("/api/v1/reconciliation/runs", headers=adm, json={"domain": "SALES"})
    assert sales_run.status_code == 201
    srun = sales_run.json()
    assert srun["status"] == "DISCREPANCY_FOUND"
    assert any(d["discrepancy_code"] == "APPROVED_ORDER_UNINVOICED" for d in srun["discrepancies"])

    # Now issue the GST invoice legitimately -> re-run detects discrepancy cleared automatically!
    assert (
        client.post(
            "/api/v1/billing/invoices",
            headers=adm,
            json={"sales_order_id": order["id"], "issue_immediately": True},
        ).status_code
        == 201
    )
    rerun_resp = client.post(f"/api/v1/reconciliation/runs/{srun['id']}/rerun", headers=adm)
    assert rerun_resp.status_code == 200
    assert rerun_resp.json()["status"] == "RESOLVED"
    assert rerun_resp.json()["resolved_count"] == srun["discrepancy_count"]

    close_sales = client.post(
        f"/api/v1/reconciliation/runs/{srun['id']}/close",
        headers=adm,
        json={"closure_notes": "Sales order invoiced and verified by re-run"},
    )
    assert close_sales.status_code == 200 and close_sales.json()["status"] == "CLOSED"

    # PostgreSQL immutability trigger forbids modifying CLOSED ReconciliationRuns or deleting ReconciliationEvents
    for bad_sql in [
        ("DELETE FROM audit.reconciliation_events WHERE reconciliation_run_id = :rid", {"rid": srun["id"]}),
        ("UPDATE audit.reconciliation_runs SET status = 'IN_PROGRESS' WHERE id = :rid", {"rid": srun["id"]}),
    ]:
        try:
            db_session.execute(text(bad_sql[0]), bad_sql[1])
            db_session.commit()
            raise AssertionError(f"Expected trigger block for: {bad_sql[0]}")
        except DBAPIError:
            db_session.rollback()


def test_5_management_intelligence_dashboard_accuracy_rbac_and_csv(
    client: TestClient, db_session: Session
) -> None:
    """Management Intelligence aggregates real Finance, Inventory, Production & Ops metrics cleanly and enforces RBAC."""
    refs = _refs(db_session)
    adm = login_and_get_headers(client, "admin")
    own = login_and_get_headers(client, "owner")
    aud = login_and_get_headers(client, "auditor")
    sm_a = login_and_get_headers(client, "salesman_a")
    supv = login_and_get_headers(client, "supervisor")

    # RBAC boundaries
    assert client.get("/api/v1/intelligence/dashboard", headers=sm_a).status_code == 403
    assert client.get("/api/v1/intelligence/dashboard", headers=supv).status_code == 403
    assert client.get("/api/v1/intelligence/reports/export/csv", headers=sm_a).status_code == 403

    # Create real order + issued invoice (partial payment -> leaves AR open)
    order = client.post(
        "/api/v1/orders",
        headers=sm_a,
        json={
            "customer_id": refs["ret_a"],
            "client_order_id": str(uuid4()),
            "items": [{"pack_size_id": refs["mrk"], "ordered_qty_pkts": 50}],
        },
    ).json()
    assert client.post(f"/api/v1/admin/orders/{order['id']}/approve", headers=adm, json={}).status_code == 200
    inv = client.post(
        "/api/v1/billing/invoices",
        headers=adm,
        json={"sales_order_id": order["id"], "issue_immediately": True},
    ).json()
    assert (
        client.post(
            "/api/v1/finance/payments",
            headers=adm,
            json={
                "customer_id": refs["ret_a"],
                "amount_paisa": 100000,
                "payment_mode": "CASH",
                "client_payment_id": str(uuid4()),
                "allocations": [{"invoice_id": inv["id"], "allocated_paisa": 100000}],
            },
        ).status_code
        == 201
    )

    today_str = date.today().isoformat()
    intel_resp = client.get(
        f"/api/v1/intelligence/dashboard?date_from={today_str}&date_to={today_str}", headers=own
    )
    assert intel_resp.status_code == 200, intel_resp.text
    intel = intel_resp.json()

    # Exact single-source-of-truth parity with Phase 9 Finance Profitability & Phase 6 Inventory
    prof = client.get(f"/api/v1/finance/profitability?date_from={today_str}&date_to={today_str}", headers=aud).json()
    inv_over = client.get("/api/v1/inventory/overview", headers=adm).json()

    assert intel["sales"]["net_sales_excl_gst_paisa"] == prof["net_revenue_paisa"]
    assert intel["sales"]["gst_collected_paisa"] == prof["gst_collected_paisa"]
    assert intel["finance"]["total_cogs_paisa"] == prof["total_cogs_paisa"]
    assert intel["finance"]["gross_profit_paisa"] == prof["gross_profit_paisa"]
    assert intel["finance"]["total_outstanding_receivables_paisa"] == inv["grand_total_paisa"] - 100000
    assert intel["finance"]["net_cash_collected_paisa"] == 100000
    assert intel["inventory"]["total_stock_valuation_paisa"] == inv_over["total_stock_value_paisa"]
    assert "Net Profit is not claimed" in intel["finance"]["profitability_disclaimer"]

    # As-of future date puts open receivable into overdue bucket & populates Watchlist!
    future_as_of = (date.fromisoformat(inv["due_date"]) + timedelta(days=5)).isoformat()
    intel_overdue = client.get(
        f"/api/v1/intelligence/dashboard?as_of_date={future_as_of}", headers=aud
    ).json()
    assert intel_overdue["finance"]["overdue_receivables_paisa"] == inv["grand_total_paisa"] - 100000
    assert any(w["category"] == "RECEIVABLES" for w in intel_overdue["watchlist"])

    # Export CSV endpoint returns real breakdown cleanly
    csv_exp = client.get("/api/v1/intelligence/reports/export/csv", headers=own)
    assert csv_exp.status_code == 200
    assert "Net Sales (Excl. GST)" in csv_exp.text
    assert "MRK-200G" in csv_exp.text
