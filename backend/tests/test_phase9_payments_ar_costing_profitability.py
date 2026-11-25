"""Comprehensive Phase 9 automated tests covering Customer Payments, Multi-Invoice Allocations,
Advances, Refunds, Payment Reversals, Credit Note Unwind, AR Ageing (due_date based),
Customer Statements, FIFO Production Batch Costing, Monthly Overhead Pools, Profitability,
DB Immutability Triggers, Strict RBAC, Concurrency, and Section 5 Benchmark Acceptance."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.main import app
from app.modules.inventory.models import Material
from app.modules.sales.models import Customer, PackSize
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


def _complete_and_post_run(
    client: TestClient,
    refs: dict[str, int],
    *,
    good_output_pkts: int = 188,
    rejected_output_pkts: int = 0,
    flour_wasted_kg: str = "0",
    damaged_pouches: str = "6",
    cartons_used: str = "9",
    batch_code: str = "MRK-P9-001",
    run_date: str | None = None,
) -> dict:
    """Create, issue materials, complete, and post a 1.0x batch run through Phase 7 endpoints."""
    supv = login_and_get_headers(client, "supervisor")
    create_payload: dict = {
        "pack_size_id": refs["mrk"],
        "batch_multiplier": "1.0",
        "plan_immediately": True,
    }
    if run_date:
        create_payload["run_date"] = run_date
    run_resp = client.post("/api/v1/production/runs", headers=supv, json=create_payload)
    assert run_resp.status_code == 201, run_resp.text
    rid = run_resp.json()["id"]

    issue_resp = client.post(
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
    assert issue_resp.status_code == 200, issue_resp.text

    consumed_flour = Decimal(40) - Decimal(flour_wasted_kg)
    complete_resp = client.post(
        f"/api/v1/production/runs/{rid}/complete",
        headers=supv,
        json={
            "good_output_pkts": good_output_pkts,
            "rejected_output_pkts": rejected_output_pkts,
            "batch_code": batch_code,
            "consumptions": [
                {
                    "material_id": refs["flr"],
                    "actual_consumed_qty": str(consumed_flour),
                    "wasted_qty": flour_wasted_kg,
                    "uom": "kg",
                },
                {"material_id": refs["oil"], "actual_consumed_qty": "10.5", "uom": "L"},
                {"material_id": refs["spc"], "actual_consumed_qty": "1.2", "uom": "kg"},
                {
                    "material_id": refs["pch"],
                    "actual_good_used_qty": str(good_output_pkts),
                    "damaged_packaging_qty": damaged_pouches,
                    "uom": "piece",
                },
                {
                    "material_id": refs["ctn"],
                    "actual_good_used_qty": cartons_used,
                    "damaged_packaging_qty": "0",
                    "uom": "piece",
                },
            ],
        },
    )
    assert complete_resp.status_code == 200, complete_resp.text
    post_resp = client.post(f"/api/v1/production/runs/{rid}/post", headers=supv)
    assert post_resp.status_code == 200, post_resp.text
    return post_resp.json()


def _submit_approve_and_issue_invoice(
    client: TestClient,
    *,
    salesman_user: str,
    customer_id: int,
    pack_size_id: int,
    qty_pkts: int,
    invoice_date: str | None = None,
) -> tuple[dict, dict]:
    """Run Salesman submit -> Admin approve -> Issue statutory GST invoice."""
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
    order = client.post(f"/api/v1/admin/orders/{ord_resp.json()['id']}/approve", headers=adm, json={}).json()
    inv_payload: dict = {"sales_order_id": order["id"], "issue_immediately": True}
    if invoice_date:
        inv_payload["invoice_date"] = invoice_date
    inv_resp = client.post("/api/v1/billing/invoices", headers=adm, json=inv_payload)
    assert inv_resp.status_code == 201, inv_resp.text
    return order, inv_resp.json()


def test_1_benchmark_12_step_e2e_costing_payments_ar_statement_and_profitability(
    client: TestClient, db_session: Session
) -> None:
    """Section 5 & Section 10 Cases 1, 2, 3, 12, 14: PRD-001 (₹30.90/pkt), Retailer A ₹7,875 - ₹4,000 = ₹3,875 -> ₹0."""
    refs = _refs(db_session)
    run = _complete_and_post_run(client, refs, good_output_pkts=188, damaged_pouches="6", cartons_used="9")
    rid = run["id"]

    adm = login_and_get_headers(client, "admin")
    supv = login_and_get_headers(client, "supervisor")

    # 1. Verify automatic PRELIMINARY Cost Summary v1 created on Production Post
    c1_resp = client.get(f"/api/v1/costing/runs/{rid}", headers=adm)
    assert c1_resp.status_code == 200, c1_resp.text
    c1 = c1_resp.json()
    s1 = c1["current_summary"]
    assert s1["snapshot_version"] == 1
    assert s1["is_current"] is True
    assert s1["cost_status"] == "PRELIMINARY"
    assert s1["raw_material_cost_paisa"] == 339000  # ₹1,680 + ₹1,470 + ₹240 = ₹3,390.00
    assert s1["damaged_packaging_cost_paisa"] == 1500  # 6 pouches * ₹2.50 = ₹15.00
    assert s1["packaging_cost_paisa"] == 62000  # ₹485 pouches + ₹135 cartons = ₹620.00
    assert s1["planned_total_cost_paisa"] == 397000  # Planned materials before shift overheads
    assert Decimal(s1["planned_cost_per_packet_paisa"]) == Decimal("1985.00")
    assert s1["total_cost_paisa"] == 401000  # ₹3,390 + ₹620 before overheads

    # 2. Supervisor finalizes run costing with Step 8 overheads: ₹1,200 Direct Labour + ₹600 Gas/Power
    fin_resp = client.post(
        f"/api/v1/costing/runs/{rid}/finalize",
        headers=supv,
        json={
            "overheads": [
                {"overhead_type": "DIRECT_LABOUR", "amount_paisa": 120000, "notes": "Batch shift labour"},
                {"overhead_type": "GAS_POWER", "amount_paisa": 60000, "notes": "Fryer gas & electricity"},
            ],
            "notes": "Section 5 final batch costing",
        },
    )
    assert fin_resp.status_code == 200, fin_resp.text
    c2 = fin_resp.json()
    s2 = c2["current_summary"]
    assert s2["snapshot_version"] == 2
    assert s2["is_current"] is True
    assert s2["cost_status"] == "FINALIZED"
    assert s2["planned_total_cost_paisa"] == 577000  # ₹3,970 + ₹1,800 = ₹5,770.00
    assert Decimal(s2["planned_cost_per_packet_paisa"]) == Decimal("2885.00")  # ₹28.85/pkt
    assert s2["direct_labour_paisa"] == 120000
    assert s2["gas_power_paisa"] == 60000
    assert s2["direct_overhead_paisa"] == 180000
    assert s2["total_cost_paisa"] == 581000  # ₹5,810.00 exact!
    assert s2["good_packets"] == 188
    assert s2["cost_per_packet_paisa"] == 3090  # ₹30.90/pkt exact ROUND_HALF_UP(581000/188)
    assert s2["selling_price_snapshot_paisa"] == 5000  # ₹50.00/pkt
    assert s2["gross_margin_per_pkt_paisa"] == 1910  # ₹19.10/pkt
    assert Decimal(s2["gross_margin_pct"]) == Decimal("38.20")
    assert len(c2["history_snapshots"]) == 2
    by_ver = {snap["snapshot_version"]: snap for snap in c2["history_snapshots"]}
    assert by_ver[1]["is_current"] is False
    assert by_ver[2]["is_current"] is True

    # 3. Submit + approve Retailer A 150 pkts -> Issue GST Invoice (₹7,875.00 = 787500 paise)
    order, inv = _submit_approve_and_issue_invoice(
        client,
        salesman_user="salesman_a",
        customer_id=refs["ret_a"],
        pack_size_id=refs["mrk"],
        qty_pkts=150,
    )
    assert inv["taxable_total_paisa"] == 750000
    assert inv["grand_total_paisa"] == 787500
    assert inv["payment_status"] == "UNPAID"
    assert inv["outstanding_paisa"] == 787500

    # Verify AR Customer Receivable created immediately upon Invoice issue
    ar_resp = client.get(f"/api/v1/finance/receivables?customer_id={refs['ret_a']}", headers=adm)
    assert ar_resp.status_code == 200
    ar_row = ar_resp.json()["items"][0]
    assert ar_row["total_invoiced_paisa"] == 787500
    assert ar_row["total_outstanding_paisa"] == 787500

    # 4. Partial Customer Payment: ₹4,000.00 (400000 paise) via UPI -> PARTIALLY_PAID, outstanding ₹3,875.00
    p1_resp = client.post(
        "/api/v1/finance/payments",
        headers=adm,
        json={
            "customer_id": refs["ret_a"],
            "amount_paisa": 400000,
            "payment_mode": "UPI",
            "reference_no": "UPI-BM-4000",
            "remarks": "First instalment from Retailer A",
            "client_payment_id": str(uuid4()),
            "allocations": [{"invoice_id": inv["id"], "allocated_paisa": 400000}],
        },
    )
    assert p1_resp.status_code == 201, p1_resp.text
    p1 = p1_resp.json()
    assert p1["payment_number"].startswith("PMT/")
    assert p1["allocated_paisa"] == 400000
    assert p1["unallocated_paisa"] == 0

    inv_mid = client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=adm).json()
    assert inv_mid["payment_status"] == "PARTIALLY_PAID"
    assert inv_mid["paid_paisa"] == 400000
    assert inv_mid["outstanding_paisa"] == 387500  # ₹3,875.00 exact!

    # Check PDF payment receipt generation
    pdf_resp = client.get(f"/api/v1/finance/payments/{p1['id']}/receipt-pdf", headers=adm)
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF-1.4")
    assert p1["payment_number"].encode("latin-1") in pdf_resp.content

    # Verify Salesman order readback shows live paid & balance
    sm_a = login_and_get_headers(client, "salesman_a")
    sm_order = client.get(f"/api/v1/orders/{order['id']}", headers=sm_a).json()
    assert sm_order["invoice_paid_paisa"] == 400000
    assert sm_order["invoice_outstanding_paisa"] == 387500
    assert sm_order["invoice_payment_status"] == "PARTIALLY_PAID"

    # 5. Second payment settles remaining ₹3,875.00 -> PAID, outstanding ₹0.00
    p2_resp = client.post(
        "/api/v1/finance/payments",
        headers=adm,
        json={
            "customer_id": refs["ret_a"],
            "amount_paisa": 387500,
            "payment_mode": "BANK_TRANSFER",
            "reference_no": "NEFT-BM-3875",
            "client_payment_id": str(uuid4()),
            "allocations": [{"invoice_id": inv["id"], "allocated_paisa": 387500}],
        },
    )
    assert p2_resp.status_code == 201, p2_resp.text

    inv_paid = client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=adm).json()
    assert inv_paid["payment_status"] == "PAID"
    assert inv_paid["paid_paisa"] == 787500
    assert inv_paid["outstanding_paisa"] == 0
    assert len(inv_paid["allocations"]) == 2

    # 6. Check Customer Statement running balance ends at 0
    stmt = client.get(f"/api/v1/finance/receivables/customers/{refs['ret_a']}/statement", headers=adm).json()
    assert stmt["total_invoiced_paisa"] == 787500
    assert stmt["total_payments_received_paisa"] == 787500
    assert stmt["total_outstanding_paisa"] == 0
    assert stmt["net_balance_paisa"] == 0
    assert stmt["entries"][-1]["running_balance_paisa"] == 0

    # 7. Dispatch 150 pkts -> Verify Profitability excludes GST (₹375) from Revenue and never double-counts cash!
    dsp = client.post(
        "/api/v1/billing/dispatches",
        headers=adm,
        json={
            "invoice_id": inv["id"],
            "post_immediately": True,
            "items": [{"invoice_item_id": inv["items"][0]["id"], "dispatched_qty_pkts": 150}],
        },
    )
    assert dsp.status_code == 201, dsp.text

    prof = client.get(f"/api/v1/finance/profitability?customer_id={refs['ret_a']}", headers=adm).json()
    assert prof["gross_revenue_paisa"] == 750000  # Excl. GST!
    assert prof["net_revenue_paisa"] == 750000
    assert prof["gst_collected_paisa"] == 37500
    assert prof["cash_received_paisa"] == 787500
    assert prof["outstanding_receivables_paisa"] == 0
    assert "Net Profit" in prof["disclaimer"]
    assert prof["by_order"][0]["net_revenue_paisa"] == 750000
    assert prof["by_order"][0]["total_cogs_paisa"] > 0


def test_2_multi_invoice_single_payment_and_split_allocations(
    client: TestClient, db_session: Session
) -> None:
    """Section 10 Case 4: Single ₹6,000.00 payment split across Inv 1 (₹5,250 PAID) and Inv 2 (₹3,150 -> ₹750 paid, ₹2,400 due)."""
    refs = _refs(db_session)
    _complete_and_post_run(client, refs, good_output_pkts=188)
    adm = login_and_get_headers(client, "admin")

    # Total FG = 50 + 188 = 238 -> Issue two invoices: 100 pkts (₹5,250) and 60 pkts (₹3,150)
    _, inv1 = _submit_approve_and_issue_invoice(
        client, salesman_user="salesman_a", customer_id=refs["ret_a"], pack_size_id=refs["mrk"], qty_pkts=100
    )
    _, inv2 = _submit_approve_and_issue_invoice(
        client, salesman_user="salesman_a", customer_id=refs["ret_a"], pack_size_id=refs["mrk"], qty_pkts=60
    )
    assert inv1["grand_total_paisa"] == 525000
    assert inv2["grand_total_paisa"] == 315000

    split_pmt = client.post(
        "/api/v1/finance/payments",
        headers=adm,
        json={
            "customer_id": refs["ret_a"],
            "amount_paisa": 600000,
            "payment_mode": "CHEQUE",
            "reference_no": "CHQ-889012",
            "client_payment_id": str(uuid4()),
            "allocations": [
                {"invoice_id": inv1["id"], "allocated_paisa": 525000},
                {"invoice_id": inv2["id"], "allocated_paisa": 75000},
            ],
        },
    )
    assert split_pmt.status_code == 201, split_pmt.text
    p = split_pmt.json()
    assert p["allocated_paisa"] == 600000
    assert p["unallocated_paisa"] == 0
    assert len(p["allocations"]) == 2

    i1_after = client.get(f"/api/v1/billing/invoices/{inv1['id']}", headers=adm).json()
    i2_after = client.get(f"/api/v1/billing/invoices/{inv2['id']}", headers=adm).json()
    assert i1_after["payment_status"] == "PAID" and i1_after["outstanding_paisa"] == 0
    assert i2_after["payment_status"] == "PARTIALLY_PAID" and i2_after["outstanding_paisa"] == 240000


def test_3_over_allocation_cross_customer_idempotency_and_duplicate_ref_guards(
    client: TestClient, db_session: Session
) -> None:
    """Section 10 Cases 5 & 7: Block over-allocation, over-invoice allocation, cross-customer allocation, duplicate refs, replay idempotency."""
    refs = _refs(db_session)
    _complete_and_post_run(client, refs, good_output_pkts=188)
    adm = login_and_get_headers(client, "admin")

    _, inv_a = _submit_approve_and_issue_invoice(
        client, salesman_user="salesman_a", customer_id=refs["ret_a"], pack_size_id=refs["mrk"], qty_pkts=40
    )
    _, inv_b = _submit_approve_and_issue_invoice(
        client, salesman_user="salesman_b", customer_id=refs["dist_b"], pack_size_id=refs["mrk"], qty_pkts=40
    )
    assert inv_a["grand_total_paisa"] == 210000

    # 1. Total allocations > payment amount blocked
    over_pmt = client.post(
        "/api/v1/finance/payments",
        headers=adm,
        json={
            "customer_id": refs["ret_a"],
            "amount_paisa": 100000,
            "payment_mode": "CASH",
            "client_payment_id": str(uuid4()),
            "allocations": [{"invoice_id": inv_a["id"], "allocated_paisa": 150000}],
        },
    )
    assert over_pmt.status_code in (409, 422)

    # 2. Allocation > invoice outstanding blocked
    over_inv = client.post(
        "/api/v1/finance/payments",
        headers=adm,
        json={
            "customer_id": refs["ret_a"],
            "amount_paisa": 500000,
            "payment_mode": "UPI",
            "reference_no": "UPI-OVER-INV",
            "client_payment_id": str(uuid4()),
            "allocations": [{"invoice_id": inv_a["id"], "allocated_paisa": 250000}],
        },
    )
    assert over_inv.status_code in (409, 422)

    # 3. Cross-customer invoice allocation blocked
    cross = client.post(
        "/api/v1/finance/payments",
        headers=adm,
        json={
            "customer_id": refs["ret_a"],
            "amount_paisa": 100000,
            "payment_mode": "UPI",
            "reference_no": "UPI-CROSS",
            "client_payment_id": str(uuid4()),
            "allocations": [{"invoice_id": inv_b["id"], "allocated_paisa": 100000}],
        },
    )
    assert cross.status_code in (409, 422)

    # 4. Idempotent replay on identical client_payment_id + duplicate reference_no block on new UUID
    idem_uuid = str(uuid4())
    payload = {
        "customer_id": refs["ret_a"],
        "amount_paisa": 100000,
        "payment_mode": "UPI",
        "reference_no": "UPI-UNIQ-101",
        "client_payment_id": idem_uuid,
        "allocations": [{"invoice_id": inv_a["id"], "allocated_paisa": 100000}],
    }
    first = client.post("/api/v1/finance/payments", headers=adm, json=payload)
    assert first.status_code == 201
    replay = client.post("/api/v1/finance/payments", headers=adm, json=payload)
    assert replay.status_code == 201
    assert replay.json()["id"] == first.json()["id"]
    assert client.get(f"/api/v1/billing/invoices/{inv_a['id']}", headers=adm).json()["paid_paisa"] == 100000

    dup_ref = client.post(
        "/api/v1/finance/payments",
        headers=adm,
        json={
            "customer_id": refs["ret_a"],
            "amount_paisa": 100000,
            "payment_mode": "UPI",
            "reference_no": "UPI-UNIQ-101",
            "client_payment_id": str(uuid4()),
            "allocations": [],
        },
    )
    assert dup_ref.status_code == 409


def test_4_advance_payment_late_allocation_and_advance_refund(
    client: TestClient, db_session: Session
) -> None:
    """Section 10 Cases 6 & 9: Advance ₹10,000 -> late allocate ₹4,000 -> refund ₹2,500 -> block over-refund & post-refund over-alloc."""
    refs = _refs(db_session)
    _complete_and_post_run(client, refs, good_output_pkts=188)
    adm = login_and_get_headers(client, "admin")

    # Record pure unallocated advance
    adv_resp = client.post(
        "/api/v1/finance/payments",
        headers=adm,
        json={
            "customer_id": refs["ret_a"],
            "amount_paisa": 1000000,  # ₹10,000
            "payment_mode": "NEFT",
            "reference_no": "NEFT-ADV-01",
            "remarks": "Festival advance deposit",
            "client_payment_id": str(uuid4()),
            "allocations": [],
        },
    )
    assert adv_resp.status_code == 201, adv_resp.text
    adv = adv_resp.json()
    assert adv["is_advance"] is True
    assert adv["unallocated_paisa"] == 1000000

    # Later create invoice and allocate ₹4,200 (80 pkts) against the existing advance
    _, inv = _submit_approve_and_issue_invoice(
        client, salesman_user="salesman_a", customer_id=refs["ret_a"], pack_size_id=refs["mrk"], qty_pkts=80
    )
    assert inv["grand_total_paisa"] == 420000

    alloc_resp = client.post(
        f"/api/v1/finance/payments/{adv['id']}/allocate",
        headers=adm,
        json={"allocations": [{"invoice_id": inv["id"], "allocated_paisa": 420000}]},
    )
    assert alloc_resp.status_code == 200, alloc_resp.text
    assert alloc_resp.json()["allocated_paisa"] == 420000
    assert alloc_resp.json()["unallocated_paisa"] == 580000

    # Issue partial advance refund ₹2,500 (RFD/2026-27/0001)
    ref_resp = client.post(
        f"/api/v1/finance/payments/{adv['id']}/refund",
        headers=adm,
        json={
            "amount_paisa": 250000,
            "refund_mode": "NEFT",
            "reference_no": "RFD-UTR-01",
            "reason": "Returning excess unused customer advance",
        },
    )
    assert ref_resp.status_code == 200, ref_resp.text
    r_data = ref_resp.json()
    assert r_data["refunded_paisa"] == 250000
    assert r_data["unallocated_paisa"] == 330000
    assert r_data["refunds"][0]["refund_number"].startswith("RFD/")

    # Over-refund beyond remaining unallocated ₹3,300 blocked
    over_ref = client.post(
        f"/api/v1/finance/payments/{adv['id']}/refund",
        headers=adm,
        json={
            "amount_paisa": 400000,
            "refund_mode": "CASH",
            "reason": "Invalid excess refund attempt",
        },
    )
    assert over_ref.status_code == 409


def test_5_allocation_reversal_payment_reversal_and_credit_note_unwind(
    client: TestClient, db_session: Session
) -> None:
    """Section 10 Cases 8 & 13: Reversing allocation, reversing payment, and Credit Note unwinding paid invoice -> advance."""
    refs = _refs(db_session)
    _complete_and_post_run(client, refs, good_output_pkts=188)
    adm = login_and_get_headers(client, "admin")

    _, inv = _submit_approve_and_issue_invoice(
        client, salesman_user="salesman_a", customer_id=refs["ret_a"], pack_size_id=refs["mrk"], qty_pkts=150
    )
    # Pay full ₹7,875.00
    p = client.post(
        "/api/v1/finance/payments",
        headers=adm,
        json={
            "customer_id": refs["ret_a"],
            "amount_paisa": 787500,
            "payment_mode": "UPI",
            "reference_no": "UPI-REV-1",
            "client_payment_id": str(uuid4()),
            "allocations": [{"invoice_id": inv["id"], "allocated_paisa": 787500}],
        },
    ).json()
    alloc_id = p["allocations"][0]["id"]

    # 1. Reverse single allocation -> invoice reverts to UNPAID, payment unallocated rises back to ₹7,875
    rev_alloc = client.post(
        f"/api/v1/finance/allocations/{alloc_id}/reverse",
        headers=adm,
        json={"reason": "Incorrect invoice selected during entry"},
    )
    assert rev_alloc.status_code == 200, rev_alloc.text
    assert rev_alloc.json()["unallocated_paisa"] == 787500
    inv_reopened = client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=adm).json()
    assert inv_reopened["payment_status"] == "UNPAID" and inv_reopened["outstanding_paisa"] == 787500

    # 2. Re-allocate ₹4,000, then reverse entire payment -> REVERSED, AR & invoice back to UNPAID ₹7,875
    re_alloc = client.post(
        f"/api/v1/finance/payments/{p['id']}/allocate",
        headers=adm,
        json={"allocations": [{"invoice_id": inv["id"], "allocated_paisa": 400000}]},
    )
    assert re_alloc.status_code == 200
    assert client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=adm).json()["payment_status"] == "PARTIALLY_PAID"

    rev_pmt = client.post(
        f"/api/v1/finance/payments/{p['id']}/reverse",
        headers=adm,
        json={"reason": "UPI settlement bounced on bank statement"},
    )
    assert rev_pmt.status_code == 200, rev_pmt.text
    assert rev_pmt.json()["status"] == "REVERSED"
    assert rev_pmt.json()["unallocated_paisa"] == 0
    assert client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=adm).json()["payment_status"] == "UNPAID"
    assert client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=adm).json()["outstanding_paisa"] == 787500

    # 3. Record full payment ₹7,875 -> dispatch 150 -> Credit Note for 20 damaged return -> payment allocation automatically unwound!
    p2 = client.post(
        "/api/v1/finance/payments",
        headers=adm,
        json={
            "customer_id": refs["ret_a"],
            "amount_paisa": 787500,
            "payment_mode": "BANK_TRANSFER",
            "reference_no": "NEFT-CN-UNWIND",
            "client_payment_id": str(uuid4()),
            "allocations": [{"invoice_id": inv["id"], "allocated_paisa": 787500}],
        },
    ).json()
    client.post(
        "/api/v1/billing/dispatches",
        headers=adm,
        json={
            "invoice_id": inv["id"],
            "post_immediately": True,
            "items": [{"invoice_item_id": inv["items"][0]["id"], "dispatched_qty_pkts": 150}],
        },
    )

    cn = client.post(
        "/api/v1/billing/credit-notes",
        headers=adm,
        json={
            "original_invoice_id": inv["id"],
            "note_type": "SALES_RETURN",
            "reason": "20 packets transit crushed return",
            "items": [
                {"invoice_item_id": inv["items"][0]["id"], "qty_pkts": 20, "return_disposition": "RESTOCK_SELLABLE"}
            ],
        },
    )
    assert cn.status_code == 201, cn.text
    cn_total = cn.json()["total_reversed_paisa"]  # 20 * 52.50 = ₹1,050.00 = 105000
    assert cn_total == 105000

    inv_after_cn = client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=adm).json()
    assert inv_after_cn["credited_paisa"] == 105000
    assert inv_after_cn["paid_paisa"] == 682500  # 787500 - 105000 automatically released!
    assert inv_after_cn["outstanding_paisa"] == 0
    assert inv_after_cn["payment_status"] == "PAID"

    p2_after_cn = client.get(f"/api/v1/finance/payments/{p2['id']}", headers=adm).json()
    assert p2_after_cn["allocated_paisa"] == 682500
    assert p2_after_cn["unallocated_paisa"] == 105000  # Available as Customer Advance!


def test_6_ageing_strictly_due_date_based_across_all_buckets(
    client: TestClient, db_session: Session
) -> None:
    """Section 10 Case 10: Invoice due_date vs as_of_date cleanly hits NOT_DUE, 0-30, 31-60, 61-90, and >90 buckets."""
    refs = _refs(db_session)
    _complete_and_post_run(client, refs, good_output_pkts=188)
    adm = login_and_get_headers(client, "admin")

    _, inv = _submit_approve_and_issue_invoice(
        client,
        salesman_user="salesman_a",
        customer_id=refs["ret_a"],
        pack_size_id=refs["mrk"],
        qty_pkts=100,
        invoice_date="2026-11-25",
    )
    due = date.fromisoformat(inv["due_date"])
    total = inv["outstanding_paisa"]
    assert total == 525000

    # Strictly verify bucket transitions as reporting as_of_date advances relative to due_date
    not_due = client.get(
        f"/api/v1/finance/receivables/ageing?as_of_date={(due - timedelta(days=1)).isoformat()}", headers=adm
    ).json()
    assert not_due["not_due_paisa"] == total and not_due["overdue_total_paisa"] == 0

    b_0_30 = client.get(
        f"/api/v1/finance/receivables/ageing?as_of_date={(due + timedelta(days=15)).isoformat()}", headers=adm
    ).json()
    assert b_0_30["overdue_1_30_paisa"] == total and b_0_30["invoices"][0]["days_past_due"] == 15

    b_31_60 = client.get(
        f"/api/v1/finance/receivables/ageing?as_of_date={(due + timedelta(days=45)).isoformat()}", headers=adm
    ).json()
    assert b_31_60["bucket_31_60_paisa"] == total and b_31_60["invoices"][0]["days_past_due"] == 45

    b_61_90 = client.get(
        f"/api/v1/finance/receivables/ageing?as_of_date={(due + timedelta(days=75)).isoformat()}", headers=adm
    ).json()
    assert b_61_90["bucket_61_90_paisa"] == total and b_61_90["invoices"][0]["days_past_due"] == 75

    b_90_plus = client.get(
        f"/api/v1/finance/receivables/ageing?as_of_date={(due + timedelta(days=110)).isoformat()}", headers=adm
    ).json()
    assert b_90_plus["bucket_90_plus_paisa"] == total and b_90_plus["invoices"][0]["days_past_due"] == 110


def test_7_costing_wastage_rejected_void_overhead_and_monthly_pool_allocation(
    client: TestClient, db_session: Session
) -> None:
    """Section 10 Cases 11 & 12: Wastage + rejected impact, voided overhead exclusion, largest-remainder monthly pool split."""
    refs = _refs(db_session)
    adm = login_and_get_headers(client, "admin")
    supv = login_and_get_headers(client, "supervisor")

    run_a = _complete_and_post_run(
        client,
        refs,
        good_output_pkts=180,
        rejected_output_pkts=10,
        flour_wasted_kg="2",
        damaged_pouches="6",
        cartons_used="9",
        batch_code="MRK-WASTE-A",
        run_date="2026-11-10",
    )
    run_b = _complete_and_post_run(
        client,
        refs,
        good_output_pkts=100,
        rejected_output_pkts=0,
        flour_wasted_kg="0",
        damaged_pouches="2",
        cartons_used="5",
        batch_code="MRK-CLEAN-B",
        run_date="2026-11-12",
    )

    c_a = client.get(f"/api/v1/costing/runs/{run_a['id']}", headers=adm).json()["current_summary"]
    assert c_a["raw_wastage_cost_paisa"] > 0
    assert c_a["damaged_packaging_cost_paisa"] == 1500
    assert c_a["rejected_packets"] == 10
    assert c_a["rejected_output_cost_impact_paisa"] > 0

    # Add direct overhead, then void it -> Supervisor blocked from void, Admin succeeds & v+1 excludes voided row
    oh = client.post(
        f"/api/v1/costing/runs/{run_a['id']}/overheads",
        headers=supv,
        json={"overhead_type": "DIRECT_LABOUR", "amount_paisa": 100000, "notes": "Wrong shift entry"},
    ).json()["overheads"][0]

    assert (
        client.post(
            f"/api/v1/costing/overheads/{oh['id']}/void",
            headers=supv,
            json={"reason": "Supervisor cannot void posted overhead"},
        ).status_code
        == 403
    )
    void_res = client.post(
        f"/api/v1/costing/overheads/{oh['id']}/void",
        headers=adm,
        json={"reason": "Duplicate shift overhead entry"},
    )
    assert void_res.status_code == 200
    c_a_after_void = client.get(f"/api/v1/costing/runs/{run_a['id']}", headers=adm).json()["current_summary"]
    assert c_a_after_void["direct_overhead_paisa"] == 0
    assert c_a_after_void["snapshot_version"] > c_a["snapshot_version"]

    # Add monthly pool ₹5,000.00 (500000 paise) for 2026-11 -> split exactly across 180 & 100 pkts with zero paisa lost!
    pool_resp = client.post(
        "/api/v1/costing/monthly-pools",
        headers=adm,
        json={"period_month": "2026-11", "overhead_type": "FACTORY_RENT", "amount_paisa": 500000},
    )
    assert pool_resp.status_code == 201, pool_resp.text
    realloc = client.post("/api/v1/costing/monthly-pools/2026-11/reallocate", headers=adm)
    assert realloc.status_code == 200
    assert realloc.json()["updated_runs_count"] == 2

    sum_a = client.get(f"/api/v1/costing/runs/{run_a['id']}", headers=adm).json()["current_summary"]
    sum_b = client.get(f"/api/v1/costing/runs/{run_b['id']}", headers=adm).json()["current_summary"]
    assert sum_a["allocated_overhead_paisa"] + sum_b["allocated_overhead_paisa"] == 500000


def test_8_immutability_triggers_strict_rbac_and_concurrent_allocation_lock(
    client: TestClient, db_session: Session
) -> None:
    """Section 10 Cases 15 & 16: DB triggers block DELETE/mutation; 5-role RBAC boundaries; concurrent full-alloc race = [201, 409]."""
    refs = _refs(db_session)
    run = _complete_and_post_run(client, refs, good_output_pkts=188)

    adm = login_and_get_headers(client, "admin")
    sm_a = login_and_get_headers(client, "salesman_a")
    sm_b = login_and_get_headers(client, "salesman_b")
    supv = login_and_get_headers(client, "supervisor")
    aud = login_and_get_headers(client, "auditor")
    own = login_and_get_headers(client, "owner")

    _, inv = _submit_approve_and_issue_invoice(
        client, salesman_user="salesman_a", customer_id=refs["ret_a"], pack_size_id=refs["mrk"], qty_pkts=100
    )

    # 1. Strict 5-role RBAC checks
    assert client.get("/api/v1/finance/my-customers/receivables", headers=sm_a).status_code == 200
    sm_a_ar = client.get("/api/v1/finance/my-customers/receivables", headers=sm_a).json()
    assert len(sm_a_ar) == 1 and sm_a_ar[0]["customer_id"] == refs["ret_a"]
    sm_b_ar = client.get("/api/v1/finance/my-customers/receivables", headers=sm_b).json()
    assert all(row["customer_id"] != refs["ret_a"] for row in sm_b_ar)

    # Salesman blocked from finance reports & ALL costing endpoints
    assert client.get("/api/v1/finance/dashboard", headers=sm_a).status_code == 403
    assert client.get("/api/v1/finance/profitability", headers=sm_a).status_code == 403
    assert client.get("/api/v1/costing/dashboard", headers=sm_a).status_code == 403
    assert client.get(f"/api/v1/costing/runs/{run['id']}", headers=sm_a).status_code == 403

    # Supervisor allowed on costing, blocked from ALL finance endpoints
    assert client.get(f"/api/v1/costing/runs/{run['id']}", headers=supv).status_code == 200
    assert client.get("/api/v1/finance/dashboard", headers=supv).status_code == 403
    assert client.get("/api/v1/finance/payments", headers=supv).status_code == 403
    assert client.get("/api/v1/finance/profitability", headers=supv).status_code == 403

    # Auditor & Owner have read-only oversight across both Finance & Costing
    assert client.get("/api/v1/finance/dashboard", headers=aud).status_code == 200
    assert client.get("/api/v1/finance/profitability", headers=own).status_code == 200
    assert client.get(f"/api/v1/costing/runs/{run['id']}", headers=aud).status_code == 200
    assert (
        client.post(
            "/api/v1/finance/payments",
            headers=aud,
            json={
                "customer_id": refs["ret_a"],
                "amount_paisa": 10000,
                "payment_mode": "CASH",
                "client_payment_id": str(uuid4()),
                "allocations": [],
            },
        ).status_code
        == 403
    )

    # 2. Concurrent simultaneous full payments against the same invoice -> strictly [201, 409]!
    def _race_pay() -> int:
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
                "/api/v1/finance/payments",
                headers=h,
                json={
                    "customer_id": refs["ret_a"],
                    "amount_paisa": inv["grand_total_paisa"],
                    "payment_mode": "UPI",
                    "reference_no": f"RACE-{uuid4().hex[:8]}",
                    "client_payment_id": str(uuid4()),
                    "allocations": [{"invoice_id": inv["id"], "allocated_paisa": inv["grand_total_paisa"]}],
                },
            )
            return r.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        race_codes = sorted(pool.map(lambda _: _race_pay(), range(2)))
    assert race_codes == [201, 409]

    def _restore_db():
        yield db_session

    app.dependency_overrides[get_db] = _restore_db
    db_session.expire_all()

    inv_final = client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=adm).json()
    assert inv_final["payment_status"] == "PAID" and inv_final["outstanding_paisa"] == 0

    # 3. Direct DB SQL DELETE / silent financial mutation blocked by PostgreSQL triggers!
    pmt = client.get("/api/v1/finance/payments", headers=adm).json()["items"][0]
    for bad_sql in [
        ("DELETE FROM finance.payments WHERE id = :id", {"id": pmt["id"]}),
        ("UPDATE finance.payments SET amount_paisa = 1 WHERE id = :id", {"id": pmt["id"]}),
        ("DELETE FROM finance.payment_allocations WHERE payment_id = :id", {"id": pmt["id"]}),
        ("DELETE FROM finance.customer_receivables WHERE customer_id = :id", {"id": refs["ret_a"]}),
        ("DELETE FROM costing.production_cost_summaries WHERE production_run_id = :id", {"id": run["id"]}),
        ("UPDATE costing.production_cost_summaries SET total_cost_paisa = 1 WHERE production_run_id = :id", {"id": run["id"]}),
    ]:
        try:
            db_session.execute(text(bad_sql[0]), bad_sql[1])
            db_session.commit()
            raise AssertionError(f"Expected trigger block for: {bad_sql[0]}")
        except DBAPIError:
            db_session.rollback()
