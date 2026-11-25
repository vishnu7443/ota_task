"""Phase 11 Final Acceptance, Full 19-Step System Integration, Official Section 5 Benchmark,
Security / RBAC / SQLi Negative Controls, Sales Master Data CRUD & DB Integrity Tests."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.inventory.models import InventoryBalance, InventoryMovement, Material
from app.modules.purchasing.models import Supplier
from app.modules.sales.models import Customer, PackSize
from app.seeds.benchmark_seed import DEV_SEED_PASSWORDS
from tests.conftest import login_and_get_headers


def _refs(db: Session) -> dict[str, int]:
    ret_a = db.execute(select(Customer).where(Customer.code == "CUST-RET-A")).scalar_one()
    dist_b = db.execute(select(Customer).where(Customer.code == "CUST-DIST-B")).scalar_one()
    mrk = db.execute(select(PackSize).where(PackSize.sku_code == "MRK-200G")).scalar_one()
    sup = db.execute(select(Supplier).where(Supplier.code == "SUP-001")).scalar_one()
    flr = db.execute(select(Material).where(Material.code == "MAT-FLR")).scalar_one()
    oil = db.execute(select(Material).where(Material.code == "MAT-OIL")).scalar_one()
    spc = db.execute(select(Material).where(Material.code == "MAT-SPC")).scalar_one()
    pch = db.execute(select(Material).where(Material.code == "MAT-PCH-200")).scalar_one()
    ctn = db.execute(select(Material).where(Material.code == "MAT-CTN-20")).scalar_one()
    return {
        "ret_a": ret_a.id,
        "dist_b": dist_b.id,
        "mrk": mrk.id,
        "sup": sup.id,
        "flr": flr.id,
        "oil": oil.id,
        "spc": spc.id,
        "pch": pch.id,
        "ctn": ctn.id,
    }


def _inventory_map(client: TestClient, headers: dict[str, str]) -> dict[str, dict]:
    resp = client.get("/api/v1/inventory/overview", headers=headers)
    assert resp.status_code == 200, resp.text
    return {row["code"]: row for row in resp.json()["items"]}


def _assert_inventory_ledger_invariants(db: Session) -> None:
    """Assert non-negative stock and exact balance == SUM(movements) across every item."""
    balances = db.execute(select(InventoryBalance)).scalars().all()
    assert len(balances) >= 6
    for bal in balances:
        assert bal.on_hand_qty_base >= Decimal(0)
        assert bal.reserved_qty_base >= Decimal(0)
        if bal.material_id is not None:
            ledger_sum = db.execute(
                select(func.coalesce(func.sum(InventoryMovement.signed_qty_base), 0)).where(
                    InventoryMovement.material_id == bal.material_id
                )
            ).scalar_one()
        else:
            ledger_sum = db.execute(
                select(func.coalesce(func.sum(InventoryMovement.signed_qty_base), 0)).where(
                    InventoryMovement.pack_size_id == bal.pack_size_id
                )
            ).scalar_one()
        assert Decimal(bal.on_hand_qty_base) == Decimal(ledger_sum), (
            f"Ledger drift on InventoryBalance id={bal.id}: persisted={bal.on_hand_qty_base}, sum={ledger_sum}"
        )


def test_1_full_19_step_integrated_order_to_audit_lifecycle(
    client: TestClient, db_session: Session
) -> None:
    """Verify all 19 end-to-end business workflow steps operate seamlessly as one connected ERP."""
    refs = _refs(db_session)
    today_str = date.today().isoformat()

    # Step 1-3: Salesman A logs in, selects CUST-RET-A, places order for 80 pkts (> opening 50 pkts)
    sm_a = login_and_get_headers(client, "salesman_a")
    customers = client.get("/api/v1/sales/customers", headers=sm_a)
    assert customers.status_code == 200
    assert any(c["code"] == "CUST-RET-A" for c in customers.json())

    ord_resp = client.post(
        "/api/v1/orders",
        headers=sm_a,
        json={
            "customer_id": refs["ret_a"],
            "client_order_id": str(uuid4()),
            "notes": "Phase 11 integrated 19-step workflow",
            "items": [{"pack_size_id": refs["mrk"], "ordered_qty_pkts": 80}],
        },
    )
    assert ord_resp.status_code == 201, ord_resp.text
    order = ord_resp.json()
    assert order["has_shortage"] is True
    assert order["items"][0]["shortage_pkts"] == 30

    # Step 4-6: Admin sees order, attempts approval, and shortage blocks approval cleanly
    adm = login_and_get_headers(client, "admin")
    supv = login_and_get_headers(client, "supervisor")
    aud = login_and_get_headers(client, "auditor")
    own = login_and_get_headers(client, "owner")

    assert client.post(f"/api/v1/admin/orders/{order['id']}/approve", headers=adm, json={}).status_code == 409

    # Step 7: Required materials purchased (PO -> Approve -> GRN Receive -> Verify -> Post)
    po = client.post(
        "/api/v1/purchasing/orders",
        headers=supv,
        json={
            "supplier_id": refs["sup"],
            "order_date": today_str,
            "submit_immediately": True,
            "items": [
                {
                    "material_id": refs["flr"],
                    "entered_qty": "60",
                    "entered_uom": "kg",
                    "unit_rate_paisa": 4500,
                    "gst_rate_bps": 0,
                }
            ],
        },
    )
    assert po.status_code == 201, po.text
    po_data = po.json()
    assert client.post(f"/api/v1/purchasing/orders/{po_data['id']}/approve", headers=adm).status_code == 200

    gr = client.post(
        "/api/v1/purchasing/receipts",
        headers=supv,
        json={
            "client_receipt_id": str(uuid4()),
            "purchase_order_id": po_data["id"],
            "supplier_bill_ref": "CAM-P11-001",
            "receipt_date": today_str,
            "submit_immediately": True,
            "items": [
                {
                    "purchase_order_item_id": po_data["items"][0]["id"],
                    "material_id": refs["flr"],
                    "entered_uom": "kg",
                    "received_qty_entered": "60",
                    "rejected_qty_entered": "0",
                    "batch_code": "FLR-P11-LOT",
                }
            ],
        },
    )
    assert gr.status_code == 201, gr.text
    gr_id = gr.json()["id"]
    assert client.post(f"/api/v1/purchasing/receipts/{gr_id}/verify", headers=adm).status_code == 200
    assert client.post(f"/api/v1/purchasing/receipts/{gr_id}/post", headers=adm).status_code == 200
    assert Decimal(_inventory_map(client, adm)["MAT-FLR"]["physical_qty_base"]) == Decimal("160000.000")

    # Step 8-11: Production planned via BOM -> Raw materials issued -> Completed -> Posted to FG
    run = client.post(
        "/api/v1/production/runs",
        headers=supv,
        json={"pack_size_id": refs["mrk"], "batch_multiplier": "1.0", "run_date": today_str, "plan_immediately": True},
    ).json()
    rid = run["id"]
    assert (
        client.post(
            f"/api/v1/production/runs/{rid}/issue-materials",
            headers=supv,
            json={
                "items": [
                    {"material_id": refs["flr"], "issued_qty": "40", "issued_uom": "kg"},
                    {"material_id": refs["oil"], "issued_qty": "10.5", "issued_uom": "L"},
                    {"material_id": refs["spc"], "issued_qty": "1.2", "issued_uom": "kg"},
                ]
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/production/runs/{rid}/complete",
            headers=supv,
            json={
                "good_output_pkts": 188,
                "rejected_output_pkts": 0,
                "batch_code": "MRK-P11-001",
                "consumptions": [
                    {"material_id": refs["flr"], "actual_consumed_qty": "40", "uom": "kg"},
                    {"material_id": refs["oil"], "actual_consumed_qty": "10.5", "uom": "L"},
                    {"material_id": refs["spc"], "actual_consumed_qty": "1.2", "uom": "kg"},
                    {
                        "material_id": refs["pch"],
                        "actual_good_used_qty": "188",
                        "damaged_packaging_qty": "6",
                        "uom": "piece",
                    },
                    {
                        "material_id": refs["ctn"],
                        "actual_good_used_qty": "9",
                        "damaged_packaging_qty": "0",
                        "uom": "piece",
                    },
                ],
            },
        ).status_code
        == 200
    )
    assert client.post(f"/api/v1/production/runs/{rid}/post", headers=supv).status_code == 200
    assert Decimal(_inventory_map(client, adm)["MRK-200G"]["physical_qty_base"]) == Decimal("238.000")

    fin_cost = client.post(
        f"/api/v1/costing/runs/{rid}/finalize",
        headers=supv,
        json={
            "overheads": [
                {"overhead_type": "DIRECT_LABOUR", "amount_paisa": 120000, "notes": "Batch labour"},
                {"overhead_type": "GAS_POWER", "amount_paisa": 60000, "notes": "Batch power"},
            ],
            "notes": "Finalized batch cost",
        },
    )
    assert fin_cost.status_code == 200
    assert fin_cost.json()["current_summary"]["cost_per_packet_paisa"] == 3090

    # Step 5 re-run: Admin now approves Salesman A's 80-pkt order cleanly
    app_ord = client.post(f"/api/v1/admin/orders/{order['id']}/approve", headers=adm, json={})
    assert app_ord.status_code == 200, app_ord.text
    assert app_ord.json()["status"] == "APPROVED"

    # Step 12-13: Invoice generated & verified & issued with CGST/SGST + valid PDF
    inv = client.post(
        "/api/v1/billing/invoices",
        headers=adm,
        json={"sales_order_id": order["id"], "invoice_date": today_str, "issue_immediately": True},
    )
    assert inv.status_code == 201, inv.text
    inv_data = inv.json()
    assert inv_data["taxable_total_paisa"] == 400000
    assert inv_data["cgst_total_paisa"] == 10000
    assert inv_data["sgst_total_paisa"] == 10000
    assert inv_data["grand_total_paisa"] == 420000

    pdf_resp = client.get(f"/api/v1/billing/invoices/{inv_data['id']}/pdf", headers=adm)
    assert pdf_resp.status_code == 200
    assert pdf_resp.content.startswith(b"%PDF-1.4")
    assert inv_data["invoice_number"].encode("latin-1") in pdf_resp.content

    # Step 14: Dispatch & complete delivery tracking (DISPATCHED -> IN_TRANSIT -> DELIVERED)
    dsp = client.post(
        "/api/v1/billing/dispatches",
        headers=adm,
        json={
            "invoice_id": inv_data["id"],
            "dispatch_date": today_str,
            "transporter_name": "Cauvery Fleet",
            "vehicle_number": "TN-45-P-1100",
            "post_immediately": True,
            "items": [{"invoice_item_id": inv_data["items"][0]["id"], "dispatched_qty_pkts": 80}],
        },
    )
    assert dsp.status_code == 201, dsp.text
    dsp_data = dsp.json()
    assert (
        client.post(
            f"/api/v1/billing/dispatches/{dsp_data['id']}/delivery",
            headers=adm,
            json={"target_status": "IN_TRANSIT", "remarks": "En route"},
        ).status_code
        == 200
    )
    deliv = client.post(
        f"/api/v1/billing/dispatches/{dsp_data['id']}/delivery",
        headers=adm,
        json={
            "target_status": "DELIVERED",
            "delivery_date": today_str,
            "remarks": "Delivered clean",
            "items": [{"dispatch_item_id": dsp_data["items"][0]["id"], "received_qty_pkts": 80}],
        },
    )
    assert deliv.status_code == 200 and deliv.json()["status"] == "DELIVERED"

    # Step 15-17: Partial payment ₹2,000 + Final payment ₹2,200 -> AR settled to ₹0
    p1 = client.post(
        "/api/v1/finance/payments",
        headers=adm,
        json={
            "customer_id": refs["ret_a"],
            "amount_paisa": 200000,
            "payment_mode": "UPI",
            "reference_no": "UPI-P11-2000",
            "client_payment_id": str(uuid4()),
            "allocations": [{"invoice_id": inv_data["id"], "allocated_paisa": 200000}],
        },
    )
    assert p1.status_code == 201
    assert client.get(f"/api/v1/finance/payments/{p1.json()['id']}/receipt-pdf", headers=adm).content.startswith(b"%PDF-1.4")

    p2 = client.post(
        "/api/v1/finance/payments",
        headers=adm,
        json={
            "customer_id": refs["ret_a"],
            "amount_paisa": 220000,
            "payment_mode": "BANK_TRANSFER",
            "reference_no": "NEFT-P11-2200",
            "client_payment_id": str(uuid4()),
            "allocations": [{"invoice_id": inv_data["id"], "allocated_paisa": 220000}],
        },
    )
    assert p2.status_code == 201
    inv_final = client.get(f"/api/v1/billing/invoices/{inv_data['id']}", headers=adm).json()
    assert inv_final["payment_status"] == "PAID"
    assert inv_final["outstanding_paisa"] == 0

    stmt = client.get(f"/api/v1/finance/receivables/customers/{refs['ret_a']}/statement", headers=adm).json()
    assert stmt["net_balance_paisa"] == 0

    # Step 18: Audit logs & Full-System Reconciliation run -> RECONCILED & Closed
    audit_tables = {
        row["entity_table"]
        for row in client.get("/api/v1/audit/logs?page=1&page_size=100", headers=aud).json()["items"]
    }
    for expected_table in ("sales_orders", "purchase_orders", "purchase_receipts", "production_runs", "invoices", "dispatches", "payments"):
        assert expected_table in audit_tables, f"Missing audit events for {expected_table}"

    inv_recon = client.post("/api/v1/reconciliation/runs", headers=adm, json={"domain": "INVENTORY"})
    assert inv_recon.status_code == 201 and inv_recon.json()["status"] == "RECONCILED"
    assert (
        client.post(
            f"/api/v1/reconciliation/runs/{inv_recon.json()['id']}/close",
            headers=adm,
            json={"closure_notes": "Inventory ledger parity verified"},
        ).status_code
        == 200
    )

    recon = client.post("/api/v1/reconciliation/runs", headers=adm, json={"domain": "FULL_SYSTEM"})
    assert recon.status_code == 201, recon.text
    rdata = recon.json()
    assert all(d["discrepancy_code"] == "BOM_CONSUMPTION_VARIANCE" for d in rdata["discrepancies"]), rdata["discrepancies"]
    for disc in rdata["discrepancies"]:
        assert (
            client.post(
                f"/api/v1/reconciliation/discrepancies/{disc['id']}/resolve",
                headers=adm,
                json={"resolution_notes": "Expected benchmark batch variance acknowledged", "dismiss": True},
            ).status_code
            == 200
        )
    assert (
        client.post(
            f"/api/v1/reconciliation/runs/{rdata['id']}/close",
            headers=adm,
            json={"closure_notes": "Phase 11 full 19-step acceptance reconciled cleanly"},
        ).status_code
        == 200
    )

    # Step 19: Management Intelligence KPIs align with exact Finance/Inventory single sources
    intel = client.get(f"/api/v1/intelligence/dashboard?date_from={today_str}&date_to={today_str}", headers=own).json()
    assert intel["sales"]["net_sales_excl_gst_paisa"] == 400000
    assert intel["sales"]["gst_collected_paisa"] == 20000
    assert intel["finance"]["net_cash_collected_paisa"] == 420000
    assert intel["finance"]["total_outstanding_receivables_paisa"] == 0
    _assert_inventory_ledger_invariants(db_session)


def test_2_official_section5_benchmark_all_11_checks_exact(
    client: TestClient, db_session: Session
) -> None:
    """Validate ALL 11 Official NIT Trichy CDI Section 5 Benchmark Expected Check Values verbatim."""
    refs = _refs(db_session)
    today_str = date.today().isoformat()
    adm = login_and_get_headers(client, "admin")
    supv = login_and_get_headers(client, "supervisor")
    sm_a = login_and_get_headers(client, "salesman_a")
    sm_b = login_and_get_headers(client, "salesman_b")
    own = login_and_get_headers(client, "owner")

    # Step 1: Receive 60 kg Flour @ ₹45/kg -> 160 kg Flour
    gr = client.post(
        "/api/v1/purchasing/receipts",
        headers=supv,
        json={
            "client_receipt_id": str(uuid4()),
            "supplier_id": refs["sup"],
            "supplier_bill_ref": "CAM-BM-FINAL",
            "receipt_date": today_str,
            "submit_immediately": True,
            "items": [
                {
                    "material_id": refs["flr"],
                    "entered_uom": "kg",
                    "received_qty_entered": "60",
                    "rejected_qty_entered": "0",
                    "unit_rate_paisa": 4500,
                    "gst_rate_bps": 0,
                    "batch_code": "FLR-BM-LOT",
                }
            ],
        },
    ).json()
    assert client.post(f"/api/v1/purchasing/receipts/{gr['id']}/verify", headers=adm).status_code == 200
    assert client.post(f"/api/v1/purchasing/receipts/{gr['id']}/post", headers=adm).status_code == 200

    # Steps 2-3: Batch PRD-001 -> Issue 40 kg Flour, 10.5 L Oil, 1.2 kg Spice; Output 188 pkts + 6 damaged pouches + 9 cartons
    rid = client.post(
        "/api/v1/production/runs",
        headers=supv,
        json={"pack_size_id": refs["mrk"], "batch_multiplier": "1.0", "run_date": today_str, "plan_immediately": True},
    ).json()["id"]
    assert (
        client.post(
            f"/api/v1/production/runs/{rid}/issue-materials",
            headers=supv,
            json={
                "items": [
                    {"material_id": refs["flr"], "issued_qty": "40", "issued_uom": "kg"},
                    {"material_id": refs["oil"], "issued_qty": "10.5", "issued_uom": "L"},
                    {"material_id": refs["spc"], "issued_qty": "1.2", "issued_uom": "kg"},
                ]
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/production/runs/{rid}/complete",
            headers=supv,
            json={
                "good_output_pkts": 188,
                "rejected_output_pkts": 0,
                "batch_code": "PRD-001",
                "consumptions": [
                    {"material_id": refs["flr"], "actual_consumed_qty": "40", "uom": "kg"},
                    {"material_id": refs["oil"], "actual_consumed_qty": "10.5", "uom": "L"},
                    {"material_id": refs["spc"], "actual_consumed_qty": "1.2", "uom": "kg"},
                    {
                        "material_id": refs["pch"],
                        "actual_good_used_qty": "188",
                        "damaged_packaging_qty": "6",
                        "uom": "piece",
                    },
                    {
                        "material_id": refs["ctn"],
                        "actual_good_used_qty": "9",
                        "damaged_packaging_qty": "0",
                        "uom": "piece",
                    },
                ],
            },
        ).status_code
        == 200
    )
    posted_run = client.post(f"/api/v1/production/runs/{rid}/post", headers=supv).json()

    # Check 1, 2, 3, 4a: Exact raw/packaging/FG post-production balances
    ov_mid = _inventory_map(client, adm)
    assert Decimal(ov_mid["MAT-FLR"]["physical_qty_base"]) == Decimal("120000.000")  # Check 1: 120 kg
    assert Decimal(ov_mid["MAT-OIL"]["physical_qty_base"]) == Decimal("19500.000")   # Check 2: 19.5 L
    assert Decimal(ov_mid["MAT-PCH-200"]["physical_qty_base"]) == Decimal("306.000") # Check 3: 306 pcs
    assert Decimal(ov_mid["MAT-CTN-20"]["physical_qty_base"]) == Decimal("21.000")   # 21 cartons
    assert Decimal(ov_mid["MAT-SPC"]["physical_qty_base"]) == Decimal("3800.000")    # 3.8 kg
    assert Decimal(ov_mid["MRK-200G"]["physical_qty_base"]) == Decimal("238.000")    # Check 4a: 238 pkts

    # Check 5 & 6: Exact Yield (-6.00% Flagged) and Oil (+5.00% Flagged) variances
    v_map = {(v["variance_scope"], v["material_code"]): v for v in posted_run["variances"]}
    assert Decimal(v_map[("YIELD", None)]["variance_pct"]) == Decimal("-6.00")
    assert v_map[("YIELD", None)]["is_flagged"] is True
    assert Decimal(v_map[("RAW_CONSUMPTION", "MAT-OIL")]["variance_pct"]) == Decimal("5.00")
    assert v_map[("RAW_CONSUMPTION", "MAT-OIL")]["is_flagged"] is True

    # Step 8 & Check 11: Finalize production cost with ₹1,200 labour + ₹600 gas/power -> ₹30.90/pkt
    cost = client.post(
        f"/api/v1/costing/runs/{rid}/finalize",
        headers=supv,
        json={
            "overheads": [
                {"overhead_type": "DIRECT_LABOUR", "amount_paisa": 120000},
                {"overhead_type": "GAS_POWER", "amount_paisa": 60000},
            ],
            "notes": "Benchmark batch overheads",
        },
    ).json()["current_summary"]
    assert cost["total_cost_paisa"] == 581000
    assert cost["cost_per_packet_paisa"] == 3090  # Check 11: ₹30.90/pkt
    assert cost["gross_margin_per_pkt_paisa"] == 1910
    assert Decimal(cost["gross_margin_pct"]) == Decimal("38.20")

    # Steps 4-5: Retailer A orders 150 pkts -> Approve -> Issue INV-1 (₹7,875) -> Dispatch 150 pkts -> FG = 88 pkts
    ord_a = client.post(
        "/api/v1/orders",
        headers=sm_a,
        json={
            "customer_id": refs["ret_a"],
            "client_order_id": str(uuid4()),
            "items": [{"pack_size_id": refs["mrk"], "ordered_qty_pkts": 150}],
        },
    ).json()
    assert client.post(f"/api/v1/admin/orders/{ord_a['id']}/approve", headers=adm, json={}).status_code == 200
    inv_a = client.post(
        "/api/v1/billing/invoices",
        headers=adm,
        json={"sales_order_id": ord_a["id"], "invoice_date": today_str, "issue_immediately": True},
    ).json()

    # Check 7: Exact Invoice Total ₹7,875.00 (CGST ₹187.50 + SGST ₹187.50)
    assert inv_a["supply_type"] == "INTRA_STATE"
    assert inv_a["taxable_total_paisa"] == 750000
    assert inv_a["cgst_total_paisa"] == 18750
    assert inv_a["sgst_total_paisa"] == 18750
    assert inv_a["igst_total_paisa"] == 0
    assert inv_a["grand_total_paisa"] == 787500

    dsp_a = client.post(
        "/api/v1/billing/dispatches",
        headers=adm,
        json={
            "invoice_id": inv_a["id"],
            "dispatch_date": today_str,
            "post_immediately": True,
            "items": [{"invoice_item_id": inv_a["items"][0]["id"], "dispatched_qty_pkts": 150}],
        },
    )
    assert dsp_a.status_code == 201
    # Check 4b: Closing FG inventory = 88 pkts
    assert Decimal(_inventory_map(client, adm)["MRK-200G"]["physical_qty_base"]) == Decimal("88.000")

    # Step 7 & Check 8: Record ₹4,000 payment -> Outstanding Receivable = ₹3,875.00
    pmt_a = client.post(
        "/api/v1/finance/payments",
        headers=adm,
        json={
            "customer_id": refs["ret_a"],
            "amount_paisa": 400000,
            "payment_mode": "UPI",
            "reference_no": "UPI-BM-STEP7",
            "client_payment_id": str(uuid4()),
            "allocations": [{"invoice_id": inv_a["id"], "allocated_paisa": 400000}],
        },
    )
    assert pmt_a.status_code == 201
    inv_a_post_pmt = client.get(f"/api/v1/billing/invoices/{inv_a['id']}", headers=adm).json()
    assert inv_a_post_pmt["payment_status"] == "PARTIALLY_PAID"
    assert inv_a_post_pmt["outstanding_paisa"] == 387500  # Check 8: ₹3,875.00

    ar_summary = client.get(f"/api/v1/finance/receivables?customer_id={refs['ret_a']}", headers=adm).json()
    assert ar_summary["items"][0]["total_outstanding_paisa"] == 387500

    # Step 6 & Checks 9-10: Distributor B (KA) orders 120 pkts vs 88 avail -> Shortage 32 pkts + IGST 5%
    ord_b = client.post(
        "/api/v1/orders",
        headers=sm_b,
        json={
            "customer_id": refs["dist_b"],
            "client_order_id": str(uuid4()),
            "items": [{"pack_size_id": refs["mrk"], "ordered_qty_pkts": 120}],
        },
    ).json()
    assert ord_b["has_shortage"] is True
    assert ord_b["items"][0]["shortage_pkts"] == 32        # Check 9: Shortage = 32 pkts
    assert ord_b["tax_estimate"]["supply_type"] == "INTER_STATE"
    assert ord_b["tax_estimate"]["igst_total_paisa"] == 30000  # Check 10: 5% IGST on ₹6,000 = ₹300
    assert ord_b["tax_estimate"]["cgst_total_paisa"] == 0
    assert ord_b["tax_estimate"]["sgst_total_paisa"] == 0
    assert client.post(f"/api/v1/admin/orders/{ord_b['id']}/approve", headers=adm, json={}).status_code == 409

    # Adjust Distributor B order to 88 pkts and confirm statutory IGST invoice
    assert (
        client.patch(
            f"/api/v1/admin/orders/{ord_b['id']}",
            headers=adm,
            json={
                "items": [{"id": ord_b["items"][0]["id"], "approved_qty_pkts": 88, "unit_price_paisa": 5000}],
                "reason": "Partial fulfill remaining 88 pkts",
            },
        ).status_code
        == 200
    )
    assert client.post(f"/api/v1/admin/orders/{ord_b['id']}/approve", headers=adm, json={}).status_code == 200
    inv_b = client.post(
        "/api/v1/billing/invoices",
        headers=adm,
        json={"sales_order_id": ord_b["id"], "invoice_date": today_str, "issue_immediately": True},
    ).json()
    assert inv_b["supply_type"] == "INTER_STATE"
    assert inv_b["cgst_total_paisa"] == 0 and inv_b["sgst_total_paisa"] == 0
    assert inv_b["igst_total_paisa"] == 22000  # 5% of ₹4,400 = ₹220
    assert inv_b["grand_total_paisa"] == 462000

    # Verify Inventory Reconciliation = RECONCILED (0 drift) and Full System shows only expected BOM variance flag
    inv_rec = client.post("/api/v1/reconciliation/runs", headers=adm, json={"domain": "INVENTORY"})
    assert inv_rec.status_code == 201 and inv_rec.json()["status"] == "RECONCILED"
    full_rec = client.post("/api/v1/reconciliation/runs", headers=adm, json={"domain": "FULL_SYSTEM"})
    assert full_rec.status_code == 201
    assert all(
        d["discrepancy_code"] == "BOM_CONSUMPTION_VARIANCE" for d in full_rec.json()["discrepancies"]
    ), full_rec.json()["discrepancies"]
    intel = client.get("/api/v1/intelligence/dashboard", headers=own)
    assert intel.status_code == 200
    assert intel.json()["finance"]["total_outstanding_receivables_paisa"] == 387500 + 462000
    _assert_inventory_ledger_invariants(db_session)


def test_3_sales_master_data_security_rbac_validation_and_db_invariants(
    client: TestClient, db_session: Session
) -> None:
    """Validate Phase 11 Customer/Price APIs, 5-role RBAC boundaries, SQLi/JWT security,
    idempotency keys, business error guards, and PostgreSQL immutability triggers."""
    refs = _refs(db_session)
    adm = login_and_get_headers(client, "admin")
    sm_a = login_and_get_headers(client, "salesman_a")
    supv = login_and_get_headers(client, "supervisor")
    aud = login_and_get_headers(client, "auditor")
    own = login_and_get_headers(client, "owner")

    # 1. Authentication & JWT negative controls
    assert client.get("/api/v1/orders/my").status_code == 401
    assert client.get("/api/v1/admin/orders", headers={"Authorization": "Bearer invalid.jwt.token"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "Wrong!Password"}).status_code == 401

    # Deactivated user login blocked
    temp_pw = "TempSecUser@2026!"
    temp_u = client.post(
        "/api/v1/iam/users",
        headers=adm,
        json={
            "username": "temp_p11",
            "full_name": "Temp Phase 11",
            "role_code": "SALESMAN",
            "password": temp_pw,
            "employee_code": "SM-P11",
            "territory": "Test",
        },
    ).json()
    assert (
        client.patch(
            f"/api/v1/iam/users/{temp_u['id']}",
            headers=own,
            json={"is_active": False, "reason": "Phase 11 security check"},
        ).status_code
        == 200
    )
    assert client.post("/api/v1/auth/login", json={"username": "temp_p11", "password": temp_pw}).status_code == 401

    # 2. Customer Creation & GSTIN/state validation + RBAC
    new_cust_payload = {
        "code": "CUST-MUM-1",
        "name": "Mumbai Snacks Hub",
        "customer_type": "DISTRIBUTOR",
        "gstin": "27AABCM1234K1Z2",
        "primary_state_name": "Maharashtra",
        "primary_state_code": "27",
        "phone": "9820012345",
        "credit_days": 30,
        "address_line1": "Plot 14, APMC Market Vashi",
        "city": "Navi Mumbai",
        "pincode": "400703",
    }
    for blocked_hdr in (sm_a, supv, aud, own):
        assert client.post("/api/v1/sales/customers", headers=blocked_hdr, json=new_cust_payload).status_code == 403

    # Mismatched GSTIN state prefix (33 GSTIN with state 27) rejected
    bad_gstin = {**new_cust_payload, "code": "CUST-BAD-1", "gstin": "33AABCM1234K1Z2"}
    assert client.post("/api/v1/sales/customers", headers=adm, json=bad_gstin).status_code == 422

    cust_ok = client.post("/api/v1/sales/customers", headers=adm, json=new_cust_payload)
    assert cust_ok.status_code == 201, cust_ok.text
    cust_id = cust_ok.json()["id"]
    assert client.post("/api/v1/sales/customers", headers=adm, json=new_cust_payload).status_code == 409

    # 3. Historical Invoice vs Price Update Isolation + RBAC
    # Issue a benchmark order at original ₹50.00 price first
    o_hist = client.post(
        "/api/v1/orders",
        headers=sm_a,
        json={
            "customer_id": refs["ret_a"],
            "client_order_id": str(uuid4()),
            "items": [{"pack_size_id": refs["mrk"], "ordered_qty_pkts": 10}],
        },
    ).json()
    assert client.post(f"/api/v1/admin/orders/{o_hist['id']}/approve", headers=adm, json={}).status_code == 200
    inv_hist = client.post(
        "/api/v1/billing/invoices",
        headers=adm,
        json={"sales_order_id": o_hist["id"], "issue_immediately": True},
    ).json()
    assert inv_hist["grand_total_paisa"] == 52500

    for blocked_hdr in (sm_a, supv, aud, own):
        assert (
            client.patch(
                f"/api/v1/sales/products/{refs['mrk']}/price",
                headers=blocked_hdr,
                json={"unit_price_paisa": 5500, "reason": "Unauthorized rate hike"},
            ).status_code
            == 403
        )

    price_upd = client.patch(
        f"/api/v1/sales/products/{refs['mrk']}/price",
        headers=adm,
        json={"unit_price_paisa": 5500, "reason": "Sesame oil seasonal revision"},
    )
    assert price_upd.status_code == 200, price_upd.text
    assert price_upd.json()["selling_price_paisa"] == 5500

    # Existing issued invoice remains ₹525.00 untouched while new interstate customer order uses ₹55.00 + 5% IGST!
    inv_hist_recheck = client.get(f"/api/v1/billing/invoices/{inv_hist['id']}", headers=adm).json()
    assert inv_hist_recheck["grand_total_paisa"] == 52500

    # Verify idempotent order submission & new price (10 pkts @ ₹55 = ₹550 + ₹27.50 IGST)
    idem_key = str(uuid4())
    o_new = client.post(
        "/api/v1/orders",
        headers=sm_a,
        json={
            "customer_id": cust_id,
            "client_order_id": idem_key,
            "items": [{"pack_size_id": refs["mrk"], "ordered_qty_pkts": 10}],
        },
    )
    assert o_new.status_code == 201
    o_new_data = o_new.json()
    assert o_new_data["taxable_total_paisa"] == 55000
    assert o_new_data["tax_estimate"]["supply_type"] == "INTER_STATE"
    assert o_new_data["tax_estimate"]["igst_total_paisa"] == 2750

    o_replay = client.post(
        "/api/v1/orders",
        headers=sm_a,
        json={
            "customer_id": cust_id,
            "client_order_id": idem_key,
            "items": [{"pack_size_id": refs["mrk"], "ordered_qty_pkts": 10}],
        },
    )
    assert o_replay.status_code in (200, 201)
    assert o_replay.json()["id"] == o_new_data["id"]

    # 4. Over-dispatch, over-allocation payment & invalid credit-note quantity guards
    assert (
        client.post(
            "/api/v1/billing/dispatches",
            headers=adm,
            json={
                "invoice_id": inv_hist["id"],
                "post_immediately": True,
                "items": [{"invoice_item_id": inv_hist["items"][0]["id"], "dispatched_qty_pkts": 99}],
            },
        ).status_code
        in (409, 422)
    )
    assert (
        client.post(
            "/api/v1/finance/payments",
            headers=adm,
            json={
                "customer_id": refs["ret_a"],
                "amount_paisa": 100000,
                "payment_mode": "CASH",
                "client_payment_id": str(uuid4()),
                "allocations": [{"invoice_id": inv_hist["id"], "allocated_paisa": 99999}],
            },
        ).status_code
        in (409, 422)
    )
    assert (
        client.post(
            "/api/v1/billing/credit-notes",
            headers=adm,
            json={
                "original_invoice_id": inv_hist["id"],
                "note_type": "SALES_RETURN",
                "reason": "Excess return test",
                "items": [
                    {"invoice_item_id": inv_hist["items"][0]["id"], "qty_pkts": 50, "return_disposition": "RESTOCK_SELLABLE"}
                ],
            },
        ).status_code
        in (409, 422)
    )

    # 5. Parameterized SQLi string safety in search endpoints + audit password redaction check
    for bad_q in ("' OR '1'='1", "x'; DROP TABLE sales.customers;--", "%' UNION SELECT password_hash FROM iam.users--"):
        r_cust = client.get(f"/api/v1/sales/customers?search={bad_q}", headers=sm_a)
        assert r_cust.status_code == 200
        assert r_cust.json() == []
        r_aud = client.get(f"/api/v1/audit/logs?search={bad_q}", headers=aud)
        assert r_aud.status_code == 200

    aud_logs = client.get("/api/v1/audit/logs?page=1&page_size=100", headers=aud).json()["items"]
    actions = {row["action"] for row in aud_logs}
    assert "CUSTOMER_CREATED" in actions
    assert "PRICE_UPDATED" in actions
    assert "ACCESS_DENIED" in actions
    for row in aud_logs:
        s = str(row)
        assert "Wrong!Password" not in s
        assert DEV_SEED_PASSWORDS["admin"] not in s
        assert temp_pw not in s

    # 6. Database append-only immutability triggers remain armed
    for sql_stmt in (
        "DELETE FROM audit.audit_logs",
        "DELETE FROM inventory.inventory_movements",
        "DELETE FROM sales.sales_order_status_history",
    ):
        try:
            db_session.execute(text(sql_stmt))
            db_session.commit()
            raise AssertionError(f"Append-only trigger failed to block: {sql_stmt}")
        except DBAPIError:
            db_session.rollback()

    _assert_inventory_ledger_invariants(db_session)
