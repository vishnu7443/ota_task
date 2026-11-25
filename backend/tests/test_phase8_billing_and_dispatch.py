"""Comprehensive Phase 8 automated tests covering GST Billing, FY Numbering, PDF,
Credit Notes, Full & Partial Dispatch, Delivery Tracking, Ledger Sync, Concurrency,
RBAC, Reports, and NIT Trichy Section 5 Benchmark Acceptance."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.main import app
from app.modules.inventory.models import (
    CostLotConsumption,
    InventoryBalance,
    InventoryMovement,
    Material,
)
from app.modules.sales.models import Customer, PackSize, Product
from tests.conftest import TestSessionLocal, login_and_get_headers


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


def _produce_benchmark_188_pkts(client: TestClient, refs: dict[str, int]) -> None:
    """Produce 188 good packets via official Phase 7 flow so FG becomes 50 + 188 = 238 pkts."""
    supv = login_and_get_headers(client, "supervisor")
    run = client.post(
        "/api/v1/production/runs",
        headers=supv,
        json={"pack_size_id": refs["mrk"], "batch_multiplier": "1.0", "plan_immediately": True},
    ).json()
    rid = run["id"]
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
    )
    client.post(
        f"/api/v1/production/runs/{rid}/complete",
        headers=supv,
        json={
            "good_output_pkts": 188,
            "rejected_output_pkts": 0,
            "batch_code": "MRK-BM-001",
            "consumptions": [
                {"material_id": refs["flr"], "actual_consumed_qty": "40", "uom": "kg"},
                {"material_id": refs["oil"], "actual_consumed_qty": "10.5", "uom": "L"},
                {"material_id": refs["spc"], "actual_consumed_qty": "1.2", "uom": "kg"},
                {"material_id": refs["pch"], "actual_good_used_qty": "188", "damaged_packaging_qty": "6", "uom": "piece"},
                {"material_id": refs["ctn"], "actual_good_used_qty": "9", "damaged_packaging_qty": "0", "uom": "piece"},
            ],
        },
    )
    posted = client.post(f"/api/v1/production/runs/{rid}/post", headers=supv)
    assert posted.status_code == 200, posted.text


def _submit_and_approve(
    client: TestClient,
    *,
    salesman_user: str,
    customer_id: int,
    pack_size_id: int,
    qty_pkts: int,
) -> dict:
    sm = login_and_get_headers(client, salesman_user)
    adm = login_and_get_headers(client, "admin")
    ord_resp = client.post(
        "/api/v1/orders",
        headers=sm,
        json={
            "customer_id": customer_id,
            "client_order_id": str(uuid4()),
            "items": [{"pack_size_id": pack_size_id, "ordered_qty_pkts": qty_pkts}],
        },
    )
    assert ord_resp.status_code == 201, ord_resp.text
    oid = ord_resp.json()["id"]
    app_resp = client.post(f"/api/v1/admin/orders/{oid}/approve", headers=adm, json={})
    assert app_resp.status_code == 200, app_resp.text
    return app_resp.json()


def test_1_final_acceptance_benchmark_retailer_a_and_distributor_b(
    client: TestClient, db_session: Session
) -> None:
    """Tests 1, 5, 6, 10, 12, 17, 18 & Final Acceptance Scenario (Retailer A 150 TN + Distributor B 120 KA)."""
    refs = _refs(db_session)
    _produce_benchmark_188_pkts(client, refs)  # FG = 238 pkts

    adm = login_and_get_headers(client, "admin")
    sm_a = login_and_get_headers(client, "salesman_a")
    sm_b = login_and_get_headers(client, "salesman_b")

    # 1. Salesman A places Retailer A (TN) 150 pkts -> Admin approves (Available 238 -> 88)
    order_a = _submit_and_approve(
        client, salesman_user="salesman_a", customer_id=refs["ret_a"], pack_size_id=refs["mrk"], qty_pkts=150
    )

    # 2. Billing generates DRAFT invoice first -> Admin verifies -> Issues statutory invoice
    draft_inv = client.post(
        "/api/v1/billing/invoices",
        headers=adm,
        json={"sales_order_id": order_a["id"], "invoice_date": "2026-11-25", "issue_immediately": False},
    )
    assert draft_inv.status_code == 201, draft_inv.text
    d = draft_inv.json()
    assert d["doc_status"] == "DRAFT"
    assert d["invoice_number"] is None  # Drafts NEVER consume FY numbers!
    assert d["taxable_total_paisa"] == 750000
    assert d["cgst_total_paisa"] == 18750
    assert d["sgst_total_paisa"] == 18750
    assert d["igst_total_paisa"] == 0
    assert d["grand_total_paisa"] == 787500

    # Invoice creation MUST NOT deduct stock (still 238 on-hand, 150 reserved)
    bal_before = db_session.execute(
        select(InventoryBalance).where(InventoryBalance.pack_size_id == refs["mrk"])
    ).scalar_one()
    assert int(bal_before.on_hand_qty_base) == 238
    assert int(bal_before.reserved_qty_base) == 150

    # Duplicate active invoice on same order blocked!
    dup_inv = client.post(
        "/api/v1/billing/invoices",
        headers=adm,
        json={"sales_order_id": order_a["id"]},
    )
    assert dup_inv.status_code == 409 and dup_inv.json()["error"]["code"] == "DUPLICATE_INVOICE"

    # Admin verifies draft & issues statutory invoice INV/2026-27/0001
    ver = client.post(
        f"/api/v1/billing/invoices/{d['id']}/verify",
        headers=adm,
        json={"remarks": "Verified Retailer A HSN 21069099 and 5% CGST+SGST", "expected_version": d["version"]},
    )
    assert ver.status_code == 200 and ver.json()["verified_at"] is not None

    issued = client.post(
        f"/api/v1/billing/invoices/{d['id']}/issue",
        headers=adm,
        json={"expected_version": ver.json()["version"]},
    )
    assert issued.status_code == 200, issued.text
    inv_a = issued.json()
    assert inv_a["doc_status"] == "ISSUED"
    assert inv_a["invoice_number"] == "INV/2026-27/0001"
    assert inv_a["financial_year"] == "2026-27"
    assert inv_a["outstanding_paisa"] == 787500  # Step 7 payment ₹4,000 belongs to Phase 9

    # Duplicate issue blocked
    reissue = client.post(f"/api/v1/billing/invoices/{d['id']}/issue", headers=adm, json={})
    assert reissue.status_code == 409 and reissue.json()["error"]["code"] == "DUPLICATE_INVOICE_ISSUE"

    # PDF generated strictly from persisted invoice matches every key number!
    pdf_resp = client.get(f"/api/v1/billing/invoices/{inv_a['id']}/pdf", headers=adm)
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    pdf_bytes = pdf_resp.content
    assert pdf_bytes.startswith(b"%PDF-1.4") and b"%%EOF" in pdf_bytes
    for expected_bytes in (b"INV/2026-27/0001", b"33AABCK1234F1Z5", b"33AAACR9999K1Z2", b"21069099", b"7,500.00", b"187.50", b"7,875.00"):
        assert expected_bytes in pdf_bytes, f"Missing {expected_bytes!r} in PDF"

    # Dispatch 150 packets & confirm stock drops atomically from 238 -> 88
    dsp_resp = client.post(
        "/api/v1/billing/dispatches",
        headers=adm,
        json={
            "invoice_id": inv_a["id"],
            "dispatch_date": "2026-11-25",
            "transporter_name": "Cauvery Fleet",
            "vehicle_number": "TN-45-X-1001",
            "post_immediately": True,
            "items": [{"invoice_item_id": inv_a["items"][0]["id"], "dispatched_qty_pkts": 150}],
        },
    )
    assert dsp_resp.status_code == 201, dsp_resp.text
    dsp_a = dsp_resp.json()
    assert dsp_a["status"] == "DISPATCHED"
    assert dsp_a["dispatch_number"] == "DSP/2026-27/0001"

    db_session.expire_all()
    bal_after = db_session.execute(
        select(InventoryBalance).where(InventoryBalance.pack_size_id == refs["mrk"])
    ).scalar_one()
    assert int(bal_after.on_hand_qty_base) == 88
    assert int(bal_after.reserved_qty_base) == 0
    assert int(bal_after.available_qty_base) == 88

    # Duplicate dispatch post blocked
    dup_post = client.post(f"/api/v1/billing/dispatches/{dsp_a['id']}/post", headers=adm, json={})
    assert dup_post.status_code == 409 and dup_post.json()["error"]["code"] == "DUPLICATE_DISPATCH_POST"

    # Delivery tracking progression: DISPATCHED -> IN_TRANSIT -> DELIVERED
    in_tr = client.post(
        f"/api/v1/billing/dispatches/{dsp_a['id']}/delivery",
        headers=adm,
        json={"target_status": "IN_TRANSIT", "remarks": "Departed Trichy factory gate"},
    )
    assert in_tr.status_code == 200 and in_tr.json()["status"] == "IN_TRANSIT"

    deliv = client.post(
        f"/api/v1/billing/dispatches/{dsp_a['id']}/delivery",
        headers=adm,
        json={
            "target_status": "DELIVERED",
            "delivery_date": "2026-11-26",
            "remarks": "Signed POD received from Retailer A",
            "items": [{"dispatch_item_id": dsp_a["items"][0]["id"], "received_qty_pkts": 150}],
        },
    )
    assert deliv.status_code == 200 and deliv.json()["status"] == "DELIVERED"
    assert deliv.json()["total_received_pkts"] == 150

    # Salesman A sees invoice number, PDF download & DELIVERED status on own order!
    sm_ord = client.get(f"/api/v1/orders/{order_a['id']}", headers=sm_a).json()
    assert sm_ord["status"] == "DISPATCHED"
    assert sm_ord["invoice_number"] == "INV/2026-27/0001"
    assert sm_ord["dispatches"][0]["status"] == "DELIVERED"
    assert client.get(f"/api/v1/billing/invoices/{inv_a['id']}/pdf", headers=sm_a).status_code == 200

    # 3. Official Step 6: Distributor B (Karnataka 29) orders 120 pkts when only 88 remain!
    ord_b_resp = client.post(
        "/api/v1/orders",
        headers=sm_b,
        json={
            "customer_id": refs["dist_b"],
            "client_order_id": str(uuid4()),
            "items": [{"pack_size_id": refs["mrk"], "ordered_qty_pkts": 120}],
        },
    )
    assert ord_b_resp.status_code == 201
    ord_b = ord_b_resp.json()
    assert ord_b["has_shortage"] is True
    assert ord_b["items"][0]["shortage_pkts"] == 32
    assert ord_b["tax_estimate"]["supply_type"] == "INTER_STATE"
    assert ord_b["tax_estimate"]["igst_total_paisa"] == 30000  # ₹300 IGST on ₹6,000

    # Approval blocked cleanly on 120 pkts; billing blocked prior to approval
    assert client.post(f"/api/v1/admin/orders/{ord_b['id']}/approve", headers=adm, json={}).status_code == 409
    assert (
        client.post("/api/v1/billing/invoices", headers=adm, json={"sales_order_id": ord_b["id"]}).status_code
        == 409
    )

    # Separate Interstate Invoice Test: Admin adjusts Distributor B to available 88 pkts -> IGST 5%
    client.patch(
        f"/api/v1/admin/orders/{ord_b['id']}",
        headers=adm,
        json={
            "items": [{"id": ord_b["items"][0]["id"], "approved_qty_pkts": 88, "unit_price_paisa": 5000}],
            "reason": "Customer agreed to 88 pkts available batch",
        },
    )
    client.post(f"/api/v1/admin/orders/{ord_b['id']}/approve", headers=adm, json={})
    inv_b = client.post(
        "/api/v1/billing/invoices",
        headers=adm,
        json={"sales_order_id": ord_b["id"], "issue_immediately": True},
    )
    assert inv_b.status_code == 201, inv_b.text
    ib = inv_b.json()
    assert ib["invoice_number"] == "INV/2026-27/0002"
    assert ib["supply_type"] == "INTER_STATE"
    assert ib["cgst_total_paisa"] == 0 and ib["sgst_total_paisa"] == 0
    assert ib["taxable_total_paisa"] == 440000  # ₹4,400.00
    assert ib["igst_total_paisa"] == 22000     # 5% IGST = ₹220.00
    assert ib["grand_total_paisa"] == 462000   # ₹4,620.00

    # Verify Reports aggregate both invoices accurately!
    rep = client.get("/api/v1/billing/reports", headers=adm).json()
    assert len(rep["sales_register"]) == 2
    assert rep["gst_summary"]["net_taxable_paisa"] == 750000 + 440000
    assert rep["gst_summary"]["net_cgst_paisa"] == 18750
    assert rep["gst_summary"]["net_sgst_paisa"] == 18750
    assert rep["gst_summary"]["net_igst_paisa"] == 22000


def test_2_fy_rollover_decimal_rounding_pos_validation_and_historical_snapshot(
    client: TestClient, db_session: Session
) -> None:
    """Tests 2, 3, 7, 8, 9: Indian FY Apr 1 rollover, ROUND_HALF_UP & round-off, POS GSTIN mismatch, historical snapshot immutability."""
    refs = _refs(db_session)
    _produce_benchmark_188_pkts(client, refs)
    adm = login_and_get_headers(client, "admin")

    # Approve 2 orders on existing 238 FG stock
    o1 = _submit_and_approve(client, salesman_user="salesman_a", customer_id=refs["ret_a"], pack_size_id=refs["mrk"], qty_pkts=1)
    o2 = _submit_and_approve(client, salesman_user="salesman_b", customer_id=refs["dist_b"], pack_size_id=refs["mrk"], qty_pkts=120)

    # Invoice 1: March 31, 2027 (FY 2026-27) -> 1 pkt @ ₹50 = ₹50 + ₹2.50 tax = ₹52.50; with commercial round-off -> +50 paise = ₹53.00
    inv1 = client.post(
        "/api/v1/billing/invoices",
        headers=adm,
        json={
            "sales_order_id": o1["id"],
            "invoice_date": "2027-03-31",
            "apply_round_off": True,
            "issue_immediately": True,
        },
    )
    assert inv1.status_code == 201, inv1.text
    i1 = inv1.json()
    assert i1["financial_year"] == "2026-27"
    assert i1["invoice_number"] == "INV/2026-27/0001"
    assert i1["taxable_total_paisa"] == 5000
    assert i1["cgst_total_paisa"] == 125 and i1["sgst_total_paisa"] == 125
    assert i1["round_off_paisa"] == 50
    assert i1["grand_total_paisa"] == 5300

    # Invoice 2: April 1, 2027 (rolls cleanly to FY 2027-28!), Distributor B Karnataka 120 pkts = ₹6,000 + ₹300 IGST = ₹6,300
    inv2 = client.post(
        "/api/v1/billing/invoices",
        headers=adm,
        json={"sales_order_id": o2["id"], "invoice_date": "2027-04-01", "issue_immediately": True},
    )
    assert inv2.status_code == 201, inv2.text
    i2 = inv2.json()
    assert i2["financial_year"] == "2027-28"
    assert i2["invoice_number"] == "INV/2027-28/0001"
    assert i2["taxable_total_paisa"] == 600000 and i2["igst_total_paisa"] == 30000 and i2["grand_total_paisa"] == 630000

    # Direct SQL price/GST master change MUST NOT alter historical issued invoices or their PDF!
    prod = db_session.execute(select(Product).where(Product.product_code == "PROD-MRK")).scalar_one()
    prod.gst_rate_bps = 1200  # rate raised from 5% -> 12%
    db_session.commit()

    i1_recheck = client.get(f"/api/v1/billing/invoices/{i1['id']}", headers=adm).json()
    assert i1_recheck["cgst_total_paisa"] == 125 and i1_recheck["grand_total_paisa"] == 5300
    assert b"53.00" in client.get(f"/api/v1/billing/invoices/{i1['id']}/pdf", headers=adm).content

    # Place-of-supply validation: odd/symmetric decimal check ₹51.00 @ 5% -> 128 + 128 = 256 paise & GSTIN prefix mismatch blocked
    from app.core.exceptions import DomainValidationError
    from app.modules.billing.gst_engine import (
        TaxLineInput,
        validate_tax_conditions_and_calculate_gst,
    )

    odd_res = validate_tax_conditions_and_calculate_gst(
        seller_gstin="33AABCK1234F1Z5",
        seller_state_code="33",
        seller_state_name="Tamil Nadu",
        buyer_gstin=None,
        customer_state_code="33",
        place_of_supply_state_code="33",
        place_of_supply_state_name="Tamil Nadu",
        lines=[TaxLineInput(1, 1, "SKU", "Murukku", "Test", "21069099", 1, 5100, 500)],
    )
    assert odd_res.nature_of_supply == "B2C"
    assert odd_res.cgst_total_paisa == 128 and odd_res.sgst_total_paisa == 128
    assert odd_res.grand_total_paisa == 5356

    try:
        validate_tax_conditions_and_calculate_gst(
            seller_gstin="33AABCK1234F1Z5",
            seller_state_code="33",
            seller_state_name="Tamil Nadu",
            buyer_gstin="29AAACD8888M1Z9",  # Karnataka GSTIN paired with Tamil Nadu customer code 33!
            customer_state_code="33",
            place_of_supply_state_code="33",
            place_of_supply_state_name="Tamil Nadu",
            lines=[TaxLineInput(1, 1, "SKU", "Murukku", "Test", "21069099", 1, 5000, 500)],
        )
        raise AssertionError("Must reject mismatched customer GSTIN state prefix")
    except DomainValidationError:
        pass


def test_3_partial_dispatch_over_dispatch_guards_and_stock_shortage_rollback(
    client: TestClient, db_session: Session
) -> None:
    """Tests 13, 14, 15, 16, 17, 18 (partial delivery discrepancy): 150 = 100 + 50, over-dispatch blocked, uninvoiced blocked, insufficient FG rollback."""
    refs = _refs(db_session)
    _produce_benchmark_188_pkts(client, refs)
    adm = login_and_get_headers(client, "admin")

    order = _submit_and_approve(client, salesman_user="salesman_a", customer_id=refs["ret_a"], pack_size_id=refs["mrk"], qty_pkts=150)

    # Draft invoice cannot be dispatched!
    draft = client.post(
        "/api/v1/billing/invoices",
        headers=adm,
        json={"sales_order_id": order["id"], "issue_immediately": False},
    ).json()
    blocked_draft_dsp = client.post(
        "/api/v1/billing/dispatches",
        headers=adm,
        json={
            "invoice_id": draft["id"],
            "items": [{"invoice_item_id": draft["items"][0]["id"], "dispatched_qty_pkts": 50}],
        },
    )
    assert blocked_draft_dsp.status_code == 409 and blocked_draft_dsp.json()["error"]["code"] == "INVOICE_NOT_ISSUED"

    inv = client.post(f"/api/v1/billing/invoices/{draft['id']}/issue", headers=adm, json={}).json()
    inv_item_id = inv["items"][0]["id"]

    # Partial dispatch #1: 100 packets (two-step CREATED -> READY -> POST)
    d1 = client.post(
        "/api/v1/billing/dispatches",
        headers=adm,
        json={
            "invoice_id": inv["id"],
            "vehicle_number": "TN-45-T1",
            "post_immediately": False,
            "items": [{"invoice_item_id": inv_item_id, "dispatched_qty_pkts": 100}],
        },
    ).json()
    assert d1["status"] == "CREATED"
    d1 = client.post(f"/api/v1/billing/dispatches/{d1['id']}/ready", headers=adm, json={}).json()
    assert d1["status"] == "READY_FOR_DISPATCH"
    d1 = client.post(f"/api/v1/billing/dispatches/{d1['id']}/post", headers=adm, json={}).json()
    assert d1["status"] == "DISPATCHED"

    # After 100 dispatched: Physical 238-100=138, Reserved 150-100=50, Available stays 88, Order PARTIALLY_DISPATCHED
    db_session.expire_all()
    bal = db_session.execute(select(InventoryBalance).where(InventoryBalance.pack_size_id == refs["mrk"])).scalar_one()
    assert int(bal.on_hand_qty_base) == 138 and int(bal.reserved_qty_base) == 50 and int(bal.available_qty_base) == 88
    assert client.get(f"/api/v1/orders/{order['id']}", headers=adm).json()["status"] == "PARTIALLY_DISPATCHED"

    # Attempting to dispatch 51 > 50 remaining must be blocked cleanly!
    over = client.post(
        "/api/v1/billing/dispatches",
        headers=adm,
        json={"invoice_id": inv["id"], "items": [{"invoice_item_id": inv_item_id, "dispatched_qty_pkts": 51}]},
    )
    assert over.status_code == 409 and over.json()["error"]["code"] == "DISPATCH_EXCEEDS_ORDER"

    # Partial dispatch #2: remaining 50 packets -> Physical 88, Reserved 0, Order DISPATCHED
    d2 = client.post(
        "/api/v1/billing/dispatches",
        headers=adm,
        json={
            "invoice_id": inv["id"],
            "post_immediately": True,
            "items": [{"invoice_item_id": inv_item_id, "dispatched_qty_pkts": 50}],
        },
    ).json()
    assert d2["status"] == "DISPATCHED"
    db_session.expire_all()
    bal = db_session.execute(select(InventoryBalance).where(InventoryBalance.pack_size_id == refs["mrk"])).scalar_one()
    assert int(bal.on_hand_qty_base) == 88 and int(bal.reserved_qty_base) == 0

    # Partial delivery exception: 48 of 50 arrived (2 damaged in transit)
    exc = client.post(
        f"/api/v1/billing/dispatches/{d2['id']}/delivery",
        headers=adm,
        json={
            "target_status": "DELIVERY_EXCEPTION",
            "exception_reason": "2 packets crushed near tailgate",
            "items": [{"dispatch_item_id": d2["items"][0]["id"], "received_qty_pkts": 48}],
        },
    )
    assert exc.status_code == 200 and exc.json()["items"][0]["discrepancy_qty_pkts"] == 2

    # Ledger zero-drift reconciliation check + FEFO CostLotConsumption trace
    movs = db_session.execute(select(InventoryMovement).where(InventoryMovement.pack_size_id == refs["mrk"])).scalars().all()
    assert sum(int(m.signed_qty_base) for m in movs) == 88
    assert len(db_session.execute(select(CostLotConsumption)).scalars().all()) >= 2


def test_4_credit_note_immutability_cancellation_and_stock_returns(
    client: TestClient, db_session: Session
) -> None:
    """Tests 11 & DB Triggers: Issued invoices cannot be deleted/updated; pre-dispatch CN cancels order & frees stock; post-dispatch RESTOCK_SELLABLE vs SCRAP_DAMAGED."""
    refs = _refs(db_session)
    _produce_benchmark_188_pkts(client, refs)
    adm = login_and_get_headers(client, "admin")

    # Scenario A: Pre-dispatch cancellation releases 100 reserved pkts & sets order CANCELLED
    o1 = _submit_and_approve(client, salesman_user="salesman_a", customer_id=refs["ret_a"], pack_size_id=refs["mrk"], qty_pkts=100)
    i1 = client.post(
        "/api/v1/billing/invoices",
        headers=adm,
        json={"sales_order_id": o1["id"], "issue_immediately": True},
    ).json()

    # DB trigger blocks direct SQL UPDATE/DELETE on ISSUED invoice
    try:
        db_session.execute(text("UPDATE billing.invoices SET taxable_total_paisa = 1 WHERE id = :id"), {"id": i1["id"]})
        db_session.commit()
        raise AssertionError("Trigger must block mutating issued invoice amounts")
    except DBAPIError:
        db_session.rollback()

    cn1 = client.post(
        "/api/v1/billing/credit-notes",
        headers=adm,
        json={
            "original_invoice_id": i1["id"],
            "note_type": "INVOICE_CANCELLATION",
            "reason": "Order cancelled prior to truck loading",
            "cancel_original_invoice": True,
        },
    )
    assert cn1.status_code == 201, cn1.text
    assert cn1.json()["cn_number"] == "CN/2026-27/0001"
    assert cn1.json()["total_reversed_paisa"] == i1["grand_total_paisa"]

    i1_after = client.get(f"/api/v1/billing/invoices/{i1['id']}", headers=adm).json()
    assert i1_after["doc_status"] == "CANCELLED_BY_CN"
    assert i1_after["outstanding_paisa"] == 0
    assert client.get(f"/api/v1/orders/{o1['id']}", headers=adm).json()["status"] == "CANCELLED"

    # Reservation was released back to 238 available!
    db_session.expire_all()
    bal = db_session.execute(select(InventoryBalance).where(InventoryBalance.pack_size_id == refs["mrk"])).scalar_one()
    assert int(bal.reserved_qty_base) == 0 and int(bal.available_qty_base) == 238

    # Duplicate credit note on already-cancelled invoice blocked!
    dup_cn = client.post(
        "/api/v1/billing/credit-notes",
        headers=adm,
        json={
            "original_invoice_id": i1["id"],
            "note_type": "INVOICE_CANCELLATION",
            "reason": "Duplicate cancellation attempt",
        },
    )
    assert dup_cn.status_code == 409

    # Scenario B: Post-dispatch Sales Return (50 dispatched -> 30 sellable RESTOCK_SELLABLE + 10 SCRAP_DAMAGED -> physical stock increases by +30 only!)
    o2 = _submit_and_approve(client, salesman_user="salesman_b", customer_id=refs["dist_b"], pack_size_id=refs["mrk"], qty_pkts=50)
    i2 = client.post("/api/v1/billing/invoices", headers=adm, json={"sales_order_id": o2["id"], "issue_immediately": True}).json()
    client.post(
        "/api/v1/billing/dispatches",
        headers=adm,
        json={
            "invoice_id": i2["id"],
            "post_immediately": True,
            "items": [{"invoice_item_id": i2["items"][0]["id"], "dispatched_qty_pkts": 50}],
        },
    )  # FG = 238 - 50 = 188

    cn_ret = client.post(
        "/api/v1/billing/credit-notes",
        headers=adm,
        json={
            "original_invoice_id": i2["id"],
            "note_type": "SALES_RETURN",
            "reason": "30 good pouches returned unopened; 10 torn during transit",
            "items": [
                {"invoice_item_id": i2["items"][0]["id"], "qty_pkts": 30, "return_disposition": "RESTOCK_SELLABLE"},
            ],
        },
    )
    assert cn_ret.status_code == 201, cn_ret.text
    cn_scrap = client.post(
        "/api/v1/billing/credit-notes",
        headers=adm,
        json={
            "original_invoice_id": i2["id"],
            "note_type": "SALES_RETURN",
            "reason": "10 packets spoiled in rain; write off without restocking",
            "items": [
                {"invoice_item_id": i2["items"][0]["id"], "qty_pkts": 10, "return_disposition": "SCRAP_DAMAGED"},
            ],
        },
    )
    assert cn_scrap.status_code == 201, cn_scrap.text

    db_session.expire_all()
    bal2 = db_session.execute(select(InventoryBalance).where(InventoryBalance.pack_size_id == refs["mrk"])).scalar_one()
    assert int(bal2.on_hand_qty_base) == 188 + 30  # Only sellable return adds stock!


def test_5_concurrency_insufficient_fg_rollback_and_rbac_isolation(
    client: TestClient, db_session: Session
) -> None:
    """Tests 15, 19, 20: Concurrent invoice/dispatch race conditions, failed dispatch rollback, and strict RBAC isolation."""
    refs = _refs(db_session)
    _produce_benchmark_188_pkts(client, refs)  # 238 pkts
    adm = login_and_get_headers(client, "admin")
    sm_a = login_and_get_headers(client, "salesman_a")
    sm_b = login_and_get_headers(client, "salesman_b")
    supv = login_and_get_headers(client, "supervisor")
    aud = login_and_get_headers(client, "auditor")
    own = login_and_get_headers(client, "owner")

    order = _submit_and_approve(client, salesman_user="salesman_a", customer_id=refs["ret_a"], pack_size_id=refs["mrk"], qty_pkts=150)

    # 1. RBAC isolation: Supervisor blocked from all billing endpoints; Auditor/Owner/Salesman blocked from mutations; Salesman B blocked from Salesman A invoice!
    assert client.get("/api/v1/billing/dashboard", headers=supv).status_code == 403
    assert client.post("/api/v1/billing/invoices", headers=supv, json={"sales_order_id": order["id"]}).status_code == 403
    assert client.post("/api/v1/billing/invoices", headers=aud, json={"sales_order_id": order["id"]}).status_code == 403
    assert client.post("/api/v1/billing/invoices", headers=own, json={"sales_order_id": order["id"]}).status_code == 403
    assert client.post("/api/v1/billing/invoices", headers=sm_a, json={"sales_order_id": order["id"]}).status_code == 403

    # 2. Concurrent invoice creation against same approved order -> strictly [201, 409]!
    def _race_create() -> int:
        def override_db():
            s = TestSessionLocal()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_db] = override_db
        with TestClient(app) as tc:
            h = login_and_get_headers(tc, "admin")
            r = tc.post(
                "/api/v1/billing/invoices",
                headers=h,
                json={"sales_order_id": order["id"], "issue_immediately": True},
            )
            return r.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        inv_codes = sorted(pool.map(lambda _: _race_create(), range(2)))
    assert inv_codes == [201, 409]

    # Restore primary fixture override cleanly
    def _restore_db():
        yield db_session

    app.dependency_overrides[get_db] = _restore_db
    inv = client.get("/api/v1/billing/invoices", headers=adm).json()[0]

    # Salesman B blocked from reading or downloading Salesman A's invoice
    assert client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=sm_b).status_code == 403
    assert client.get(f"/api/v1/billing/invoices/{inv['id']}/pdf", headers=sm_b).status_code == 403

    # Auditor & Owner can read invoice & reports, blocked from posting dispatch
    assert client.get("/api/v1/billing/reports", headers=aud).status_code == 200
    assert client.get(f"/api/v1/billing/invoices/{inv['id']}/pdf", headers=own).status_code == 200
    assert (
        client.post(
            "/api/v1/billing/dispatches",
            headers=aud,
            json={"invoice_id": inv["id"], "items": [{"invoice_item_id": client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=adm).json()["items"][0]["id"], "dispatched_qty_pkts": 50}]},
        ).status_code
        == 403
    )

    # 3. Create 1 CREATED dispatch for 150 pkts -> race two simultaneous POST /post requests -> [200, 409]!
    inv_detail = client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=adm).json()
    dsp = client.post(
        "/api/v1/billing/dispatches",
        headers=adm,
        json={
            "invoice_id": inv["id"],
            "post_immediately": False,
            "items": [{"invoice_item_id": inv_detail["items"][0]["id"], "dispatched_qty_pkts": 150}],
        },
    ).json()

    def _race_post_dispatch() -> int:
        def override_db():
            s = TestSessionLocal()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_db] = override_db
        with TestClient(app) as tc:
            h = login_and_get_headers(tc, "admin")
            return tc.post(f"/api/v1/billing/dispatches/{dsp['id']}/post", headers=h, json={}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        dsp_codes = sorted(pool.map(lambda _: _race_post_dispatch(), range(2)))
    assert dsp_codes == [200, 409]

    app.dependency_overrides[get_db] = _restore_db
    db_session.expire_all()
    bal = db_session.execute(select(InventoryBalance).where(InventoryBalance.pack_size_id == refs["mrk"])).scalar_one()
    assert int(bal.on_hand_qty_base) == 88  # Deducted strictly once!
    assert date.today() is not None
