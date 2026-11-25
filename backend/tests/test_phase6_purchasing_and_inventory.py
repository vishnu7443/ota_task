from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.main import app
from app.modules.audit.models import AuditLog
from app.modules.inventory.models import (
    CostLot,
    InventoryBalance,
    InventoryMovement,
    Material,
    StockAdjustment,
)
from app.modules.purchasing.models import PurchaseOrder, PurchaseReceipt, Supplier
from app.modules.sales.models import Customer, PackSize
from tests.conftest import TestSessionLocal, login_and_get_headers


def _get_seeded_refs(db: Session) -> dict[str, int]:
    sup = db.execute(select(Supplier).where(Supplier.code == "SUP-001")).scalar_one()
    flr = db.execute(select(Material).where(Material.code == "MAT-FLR")).scalar_one()
    oil = db.execute(select(Material).where(Material.code == "MAT-OIL")).scalar_one()
    spc = db.execute(select(Material).where(Material.code == "MAT-SPC")).scalar_one()
    pch = db.execute(select(Material).where(Material.code == "MAT-PCH-200")).scalar_one()
    ctn = db.execute(select(Material).where(Material.code == "MAT-CTN-20")).scalar_one()
    mrk = db.execute(select(PackSize).where(PackSize.sku_code == "MRK-200G")).scalar_one()
    ret_a = db.execute(select(Customer).where(Customer.code == "CUST-RET-A")).scalar_one()
    return {
        "sup_1": sup.id,
        "flr": flr.id,
        "oil": oil.id,
        "spc": spc.id,
        "pch": pch.id,
        "ctn": ctn.id,
        "mrk": mrk.id,
        "ret_a": ret_a.id,
    }


def _overview_map(client: TestClient, headers: dict[str, str]) -> dict[str, dict]:
    resp = client.get("/api/v1/inventory/overview", headers=headers)
    assert resp.status_code == 200, resp.text
    return {item["code"]: item for item in resp.json()["items"]}


def test_supplier_crud_validation_and_purchase_history(client: TestClient, db_session: Session) -> None:
    adm = login_and_get_headers(client, "admin")
    sup_list = client.get("/api/v1/purchasing/suppliers", headers=adm)
    assert sup_list.status_code == 200
    codes = [s["code"] for s in sup_list.json()]
    assert "SUP-001" in codes

    # Create a new supplier
    create_resp = client.post(
        "/api/v1/purchasing/suppliers",
        headers=adm,
        json={
            "code": "SUP-002",
            "name": "Madurai Edible Oils Pvt Ltd",
            "contact_person": "K. Meenakshi",
            "phone": "+919842100000",
            "email": "orders@maduraioils.example",
            "gstin": "33AAACM1234A1Z5",
            "state_name": "Tamil Nadu",
            "state_code": "33",
            "address": "19 Kappalur Industrial Estate, Madurai, TN - 625008",
            "is_active": True,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    sup2_id = create_resp.json()["id"]

    # Duplicate code rejected
    dup_resp = client.post(
        "/api/v1/purchasing/suppliers",
        headers=adm,
        json={
            "code": "SUP-002",
            "name": "Duplicate Supplier",
            "state_name": "Tamil Nadu",
            "state_code": "33",
            "address": "Trichy",
        },
    )
    assert dup_resp.status_code == 409

    # GSTIN prefix mismatch rejected
    bad_gstin = client.post(
        "/api/v1/purchasing/suppliers",
        headers=adm,
        json={
            "code": "SUP-003",
            "name": "Mismatch GSTIN Supplier",
            "gstin": "29AAACM1234A1Z5",
            "state_name": "Tamil Nadu",
            "state_code": "33",
            "address": "Trichy",
        },
    )
    assert bad_gstin.status_code == 422

    # Update supplier & deactivate/reactivate
    upd_resp = client.put(
        f"/api/v1/purchasing/suppliers/{sup2_id}",
        headers=adm,
        json={
            "name": "Madurai Gold Oils Ltd",
            "contact_person": "K. Meenakshi",
            "phone": "+919842199999",
            "email": "supply@maduraioils.example",
            "gstin": "33AAACM1234A1Z5",
            "state_name": "Tamil Nadu",
            "state_code": "33",
            "address": "19 Kappalur Industrial Estate, Madurai",
            "is_active": False,
        },
    )
    assert upd_resp.status_code == 200
    assert upd_resp.json()["name"] == "Madurai Gold Oils Ltd"
    assert upd_resp.json()["is_active"] is False

    # Inactive supplier filtered out when active_only=true
    active_list = client.get("/api/v1/purchasing/suppliers?active_only=true", headers=adm).json()
    assert all(s["code"] != "SUP-002" for s in active_list)

    # Supplier detail includes purchase history arrays
    detail = client.get(f"/api/v1/purchasing/suppliers/{sup2_id}", headers=adm)
    assert detail.status_code == 200
    assert detail.json()["purchase_orders"] == []
    assert detail.json()["purchase_receipts"] == []


def test_po_lifecycle_totals_and_po_alone_does_not_increase_stock(
    client: TestClient, db_session: Session
) -> None:
    refs = _get_seeded_refs(db_session)
    supv = login_and_get_headers(client, "supervisor")
    adm = login_and_get_headers(client, "admin")

    before = _overview_map(client, adm)
    assert Decimal(before["MAT-FLR"]["physical_qty_base"]) == Decimal("100000.000")
    assert Decimal(before["MAT-PCH-200"]["physical_qty_base"]) == Decimal("500.000")

    # Supervisor creates a DRAFT PO mixing Raw Material (Flour) + Packaging (Pouches)
    po_resp = client.post(
        "/api/v1/purchasing/orders",
        headers=supv,
        json={
            "supplier_id": refs["sup_1"],
            "order_date": "2026-11-25",
            "expected_date": "2026-11-27",
            "notes": "Weekly flour and pouch replenishment",
            "submit_immediately": False,
            "items": [
                {
                    "material_id": refs["flr"],
                    "entered_qty": "60",
                    "entered_uom": "kg",
                    "unit_rate_paisa": 4500,  # ₹45/kg -> ₹2,700
                    "gst_rate_bps": 500,
                },
                {
                    "material_id": refs["pch"],
                    "entered_qty": "200",
                    "entered_uom": "piece",
                    "unit_rate_paisa": 250,  # ₹2.50/pc -> ₹500
                    "gst_rate_bps": 1800,
                },
            ],
        },
    )
    assert po_resp.status_code == 201, po_resp.text
    po = po_resp.json()
    assert po["status"] == "DRAFT"
    assert po["subtotal_paisa"] == 320000  # 270000 + 50000
    assert po["tax_paisa"] == 22500  # 13500 + 9000
    assert po["total_paisa"] == 342500

    # Supervisor submits PO
    sub_resp = client.post(f"/api/v1/purchasing/orders/{po['id']}/submit", headers=supv)
    assert sub_resp.status_code == 200
    assert sub_resp.json()["status"] == "SUBMITTED"

    # Supervisor cannot approve PO (Admin only)
    forb = client.post(f"/api/v1/purchasing/orders/{po['id']}/approve", headers=supv)
    assert forb.status_code == 403

    # Admin approves PO
    app_resp = client.post(f"/api/v1/purchasing/orders/{po['id']}/approve", headers=adm)
    assert app_resp.status_code == 200
    assert app_resp.json()["status"] == "APPROVED"

    # Re-approve blocked
    reapp = client.post(f"/api/v1/purchasing/orders/{po['id']}/approve", headers=adm)
    assert reapp.status_code == 409

    # Rejecting an APPROVED PO blocked
    rej_after_app = client.post(
        f"/api/v1/purchasing/orders/{po['id']}/reject",
        headers=adm,
        json={"reason": "Should not reject approved PO"},
    )
    assert rej_after_app.status_code == 409

    # Critical invariant: Approving PO alone MUST NOT change inventory!
    after = _overview_map(client, adm)
    assert Decimal(after["MAT-FLR"]["physical_qty_base"]) == Decimal("100000.000")
    assert Decimal(after["MAT-PCH-200"]["physical_qty_base"]) == Decimal("500.000")

    # Separate PO rejection & cancellation checks
    po2 = client.post(
        "/api/v1/purchasing/orders",
        headers=supv,
        json={
            "supplier_id": refs["sup_1"],
            "submit_immediately": True,
            "items": [
                {
                    "material_id": refs["oil"],
                    "entered_qty": "20",
                    "entered_uom": "L",
                    "unit_rate_paisa": 14000,
                    "gst_rate_bps": 500,
                }
            ],
        },
    ).json()
    rej2 = client.post(
        f"/api/v1/purchasing/orders/{po2['id']}/reject",
        headers=adm,
        json={"reason": "Rate higher than approved seasonal contract"},
    )
    assert rej2.status_code == 200
    assert rej2.json()["status"] == "REJECTED"


def test_benchmark_final_acceptance_scenario_60kg_flour_and_exact_balances(
    client: TestClient, db_session: Session
) -> None:
    """NIT Trichy Section 5 + Phase 6 Final Acceptance Test:
    Opening: Flour 100 kg, Oil 30 L, Spice 5 kg, Pouches 500 pcs, Cartons 30 pcs, FG Murukku 50 pkts.
    PO + Goods Receipt: 60 kg Flour @ ₹45/kg -> Closing Flour = 160 kg (160,000 g).
    """
    refs = _get_seeded_refs(db_session)
    adm = login_and_get_headers(client, "admin")
    supv = login_and_get_headers(client, "supervisor")

    # Check exact seeded opening balances first
    start = _overview_map(client, adm)
    assert Decimal(start["MAT-FLR"]["physical_qty_base"]) == Decimal("100000.000")
    assert Decimal(start["MAT-OIL"]["physical_qty_base"]) == Decimal("30000.000")
    assert Decimal(start["MAT-SPC"]["physical_qty_base"]) == Decimal("5000.000")
    assert Decimal(start["MAT-PCH-200"]["physical_qty_base"]) == Decimal("500.000")
    assert Decimal(start["MAT-CTN-20"]["physical_qty_base"]) == Decimal("30.000")
    assert Decimal(start["MRK-200G"]["physical_qty_base"]) == Decimal("50.000")

    # 1. Create & submit PO for 60 kg Flour @ ₹45/kg
    po = client.post(
        "/api/v1/purchasing/orders",
        headers=supv,
        json={
            "supplier_id": refs["sup_1"],
            "order_date": "2026-11-25",
            "submit_immediately": True,
            "items": [
                {
                    "material_id": refs["flr"],
                    "entered_qty": "60",
                    "entered_uom": "kg",
                    "unit_rate_paisa": 4500,
                    "gst_rate_bps": 500,
                }
            ],
        },
    )
    assert po.status_code == 201, po.text
    po_data = po.json()
    po_item_id = po_data["items"][0]["id"]

    # 2. Admin approves PO
    app_po = client.post(f"/api/v1/purchasing/orders/{po_data['id']}/approve", headers=adm)
    assert app_po.status_code == 200

    # 3. Record Goods Receipt in kg (60 kg)
    client_gr_id = str(uuid4())
    gr_create = client.post(
        "/api/v1/purchasing/receipts",
        headers=supv,
        json={
            "client_receipt_id": client_gr_id,
            "purchase_order_id": po_data["id"],
            "supplier_bill_ref": "CAM-INV-2026-088",
            "receipt_date": "2026-11-25",
            "items": [
                {
                    "purchase_order_item_id": po_item_id,
                    "material_id": refs["flr"],
                    "entered_uom": "kg",
                    "received_qty_entered": "60",
                    "rejected_qty_entered": "0",
                    "batch_code": "FLR-LOT-202611",
                    "expiry_date": "2027-05-25",
                }
            ],
        },
    )
    assert gr_create.status_code == 201, gr_create.text
    gr = gr_create.json()
    assert gr["status"] == "DRAFT"
    assert Decimal(gr["items"][0]["accepted_qty_base"]) == Decimal("60000.000")
    assert Decimal(gr["items"][0]["unit_cost_paisa_per_base"]) == Decimal("4.500000")

    # Duplicate creation with same client_receipt_id returns 200 replay (zero duplicate row)
    gr_replay = client.post(
        "/api/v1/purchasing/receipts",
        headers=supv,
        json={
            "client_receipt_id": client_gr_id,
            "purchase_order_id": po_data["id"],
            "items": [
                {
                    "purchase_order_item_id": po_item_id,
                    "material_id": refs["flr"],
                    "entered_uom": "kg",
                    "received_qty_entered": "60",
                    "rejected_qty_entered": "0",
                }
            ],
        },
    )
    assert gr_replay.status_code == 200
    assert gr_replay.json()["id"] == gr["id"]
    assert gr_replay.json()["is_duplicate_replay"] is True

    # Before posting, Flour must still be 100 kg
    assert Decimal(_overview_map(client, adm)["MAT-FLR"]["physical_qty_base"]) == Decimal("100000.000")

    # 4. Submit -> Verify -> Post
    s1 = client.post(f"/api/v1/purchasing/receipts/{gr['id']}/submit", headers=supv)
    assert s1.status_code == 200 and s1.json()["status"] == "SUBMITTED"
    s2 = client.post(f"/api/v1/purchasing/receipts/{gr['id']}/verify", headers=adm)
    assert s2.status_code == 200 and s2.json()["status"] == "VERIFIED"
    s3 = client.post(f"/api/v1/purchasing/receipts/{gr['id']}/post", headers=adm)
    assert s3.status_code == 200
    assert s3.json()["status"] == "POSTED"

    # Duplicate post blocked!
    s3_dup = client.post(f"/api/v1/purchasing/receipts/{gr['id']}/post", headers=adm)
    assert s3_dup.status_code == 409

    # PO automatically transitions to RECEIVED
    po_final = client.get(f"/api/v1/purchasing/orders/{po_data['id']}", headers=adm).json()
    assert po_final["status"] == "RECEIVED"
    assert Decimal(po_final["items"][0]["remaining_qty_base"]) == Decimal("0.000")

    # Closing balances match Final Acceptance Scenario!
    end = _overview_map(client, adm)
    flr = end["MAT-FLR"]
    assert Decimal(flr["opening_qty_base"]) == Decimal("100000.000")
    assert Decimal(flr["received_qty_base"]) == Decimal("60000.000")
    assert Decimal(flr["physical_qty_base"]) == Decimal("160000.000")
    assert Decimal(flr["available_qty_base"]) == Decimal("160000.000")
    assert flr["open_lot_value_paisa"] == (100 * 4200) + (60 * 4500)  # 420000 + 270000 = 690000

    # Remaining benchmark items untouched
    assert Decimal(end["MAT-OIL"]["physical_qty_base"]) == Decimal("30000.000")
    assert Decimal(end["MAT-SPC"]["physical_qty_base"]) == Decimal("5000.000")
    assert Decimal(end["MAT-PCH-200"]["physical_qty_base"]) == Decimal("500.000")
    assert Decimal(end["MAT-CTN-20"]["physical_qty_base"]) == Decimal("30.000")
    assert Decimal(end["MRK-200G"]["physical_qty_base"]) == Decimal("50.000")

    # Inventory Ledger for Flour contains OPENING (+100 kg) and PURCHASE_IN (+60 kg)
    ledger_resp = client.get(
        f"/api/v1/inventory/ledger?material_id={refs['flr']}", headers=adm
    )
    assert ledger_resp.status_code == 200
    entries = ledger_resp.json()
    mtypes = [e["movement_type"] for e in entries]
    assert "PURCHASE_IN" in mtypes and "OPENING" in mtypes
    pur_entry = next(e for e in entries if e["movement_type"] == "PURCHASE_IN")
    assert Decimal(pur_entry["signed_qty_base"]) == Decimal("60000.000")
    assert pur_entry["total_cost_paisa"] == 270000

    # Supplier detail reflects PO + receipt history
    sup_detail = client.get(f"/api/v1/purchasing/suppliers/{refs['sup_1']}", headers=adm).json()
    assert sup_detail["po_count"] == 1
    assert sup_detail["receipt_count"] == 1
    assert sup_detail["total_purchased_paisa"] == 283500  # 270000 + 5% GST 13500

    # Verify two FIFO CostLots exist in DB for Flour (100 kg @ 4.20/g + 60 kg @ 4.50/g)
    lots = (
        db_session.execute(
            select(CostLot)
            .where(CostLot.material_id == refs["flr"])
            .order_by(CostLot.id.asc())
        )
        .scalars()
        .all()
    )
    assert len(lots) == 2
    assert Decimal(lots[0].remaining_qty_base) == Decimal("100000.000")
    assert Decimal(lots[0].unit_cost_paisa_per_base) == Decimal("4.200000")
    assert Decimal(lots[1].remaining_qty_base) == Decimal("60000.000")
    assert Decimal(lots[1].unit_cost_paisa_per_base) == Decimal("4.500000")

    # Verify DB rows cleanly linked
    assert db_session.execute(select(PurchaseOrder)).scalar_one().status == "RECEIVED"
    assert db_session.execute(select(PurchaseReceipt)).scalar_one().status == "POSTED"


def test_partial_receipt_damaged_rejection_and_excess_guard(
    client: TestClient, db_session: Session
) -> None:
    refs = _get_seeded_refs(db_session)
    adm = login_and_get_headers(client, "admin")
    supv = login_and_get_headers(client, "supervisor")

    # PO for 100 kg Flour
    po = client.post(
        "/api/v1/purchasing/orders",
        headers=adm,
        json={
            "supplier_id": refs["sup_1"],
            "submit_immediately": True,
            "items": [
                {
                    "material_id": refs["flr"],
                    "entered_qty": "100",
                    "entered_uom": "kg",
                    "unit_rate_paisa": 4500,
                    "gst_rate_bps": 500,
                }
            ],
        },
    ).json()
    client.post(f"/api/v1/purchasing/orders/{po['id']}/approve", headers=adm)
    po_item_id = po["items"][0]["id"]

    # Receipt 1: 50 kg received, 5 kg rejected due to moisture -> 45 kg accepted
    gr1 = client.post(
        "/api/v1/purchasing/receipts",
        headers=supv,
        json={
            "client_receipt_id": str(uuid4()),
            "purchase_order_id": po["id"],
            "submit_immediately": True,
            "items": [
                {
                    "purchase_order_item_id": po_item_id,
                    "material_id": refs["flr"],
                    "entered_uom": "kg",
                    "received_qty_entered": "50",
                    "rejected_qty_entered": "5",
                    "rejection_reason": "Two 2.5 kg sacks damp at lorry unloading",
                }
            ],
        },
    )
    assert gr1.status_code == 201, gr1.text
    gr1_id = gr1.json()["id"]
    client.post(f"/api/v1/purchasing/receipts/{gr1_id}/verify", headers=adm)
    client.post(f"/api/v1/purchasing/receipts/{gr1_id}/post", headers=adm)

    # Stock increases ONLY by accepted 45 kg (100 + 45 = 145 kg)!
    ov = _overview_map(client, adm)
    assert Decimal(ov["MAT-FLR"]["physical_qty_base"]) == Decimal("145000.000")

    # PO is now PARTIALLY_RECEIVED with 55 kg remaining (100 ordered - 45 accepted)
    po_mid = client.get(f"/api/v1/purchasing/orders/{po['id']}", headers=adm).json()
    assert po_mid["status"] == "PARTIALLY_RECEIVED"
    assert Decimal(po_mid["items"][0]["remaining_qty_base"]) == Decimal("55000.000")
    assert Decimal(po_mid["items"][0]["rejected_qty_base"]) == Decimal("5000.000")

    # Excess receipt blocked when remaining is 55 kg and user tries 60 kg without allow_excess
    excess = client.post(
        "/api/v1/purchasing/receipts",
        headers=supv,
        json={
            "client_receipt_id": str(uuid4()),
            "purchase_order_id": po["id"],
            "items": [
                {
                    "purchase_order_item_id": po_item_id,
                    "material_id": refs["flr"],
                    "entered_uom": "kg",
                    "received_qty_entered": "60",
                    "rejected_qty_entered": "0",
                    "allow_excess": False,
                }
            ],
        },
    )
    assert excess.status_code == 409
    assert excess.json()["error"]["code"] == "EXCESS_RECEIPT_QUANTITY"

    # Second receipt of remaining 55 kg entered in GRAMS (55000 g)! Tests UOM conversion too!
    gr2 = client.post(
        "/api/v1/purchasing/receipts",
        headers=supv,
        json={
            "client_receipt_id": str(uuid4()),
            "purchase_order_id": po["id"],
            "submit_immediately": True,
            "items": [
                {
                    "purchase_order_item_id": po_item_id,
                    "material_id": refs["flr"],
                    "entered_uom": "g",
                    "received_qty_entered": "55000",
                    "rejected_qty_entered": "0",
                    "unit_rate_paisa": 5,  # 5 paisa per gram = ₹50/kg explicit rate check
                }
            ],
        },
    )
    assert gr2.status_code == 201, gr2.text
    gr2_id = gr2.json()["id"]
    client.post(f"/api/v1/purchasing/receipts/{gr2_id}/verify", headers=adm)
    client.post(f"/api/v1/purchasing/receipts/{gr2_id}/post", headers=adm)

    po_done = client.get(f"/api/v1/purchasing/orders/{po['id']}", headers=adm).json()
    assert po_done["status"] == "RECEIVED"
    ov2 = _overview_map(client, adm)
    assert Decimal(ov2["MAT-FLR"]["physical_qty_base"]) == Decimal("200000.000")


def test_unit_conversion_and_incompatible_unit_rejected(client: TestClient, db_session: Session) -> None:
    refs = _get_seeded_refs(db_session)
    adm = login_and_get_headers(client, "admin")

    # Incompatible dimension: Liters ('L') for Flour ('MASS') rejected cleanly with 422
    bad_po = client.post(
        "/api/v1/purchasing/orders",
        headers=adm,
        json={
            "supplier_id": refs["sup_1"],
            "items": [
                {
                    "material_id": refs["flr"],
                    "entered_qty": "10",
                    "entered_uom": "L",
                    "unit_rate_paisa": 4500,
                }
            ],
        },
    )
    assert bad_po.status_code == 422

    # Valid fractional unit conversion on volume: 500 ml Oil adjusted out
    adj_resp = client.post(
        "/api/v1/inventory/adjustments",
        headers=adm,
        json={
            "item_type": "MATERIAL",
            "item_id": refs["oil"],
            "adjustment_type": "DAMAGED",
            "entered_qty": "-500",
            "entered_uom": "ml",
            "reason": "Leaking oil tin discarded after inspection",
            "post_immediately": True,
        },
    )
    assert adj_resp.status_code == 201, adj_resp.text
    assert Decimal(adj_resp.json()["delta_qty_base"]) == Decimal("-500.000")
    ov = _overview_map(client, adm)
    assert Decimal(ov["MAT-OIL"]["physical_qty_base"]) == Decimal("29500.000")  # 29.5 L


def test_stock_adjustments_approval_workflow_low_stock_and_reservation_safety(
    client: TestClient, db_session: Session
) -> None:
    refs = _get_seeded_refs(db_session)
    supv = login_and_get_headers(client, "supervisor")
    adm = login_and_get_headers(client, "admin")
    sm_a = login_and_get_headers(client, "salesman_a")

    # Supervisor requests adjustment (cannot self-post immediately!)
    forb_self_post = client.post(
        "/api/v1/inventory/adjustments",
        headers=supv,
        json={
            "item_type": "MATERIAL",
            "item_id": refs["flr"],
            "adjustment_type": "COUNT_CORRECTION",
            "entered_qty": "-5",
            "entered_uom": "kg",
            "reason": "Attempting immediate self post",
            "post_immediately": True,
        },
    )
    assert forb_self_post.status_code == 403

    # Supervisor creates PENDING_APPROVAL adjustment for 60 kg reduction on Flour (100 -> 40 < 50 reorder!)
    req_adj = client.post(
        "/api/v1/inventory/adjustments",
        headers=supv,
        json={
            "item_type": "MATERIAL",
            "item_id": refs["flr"],
            "adjustment_type": "SUPPLIER_RETURN",
            "entered_qty": "-60",
            "entered_uom": "kg",
            "reason": "Returning lumpy flour bags from old batch to supplier",
            "post_immediately": False,
        },
    )
    assert req_adj.status_code == 201, req_adj.text
    adj_id = req_adj.json()["id"]
    assert req_adj.json()["status"] == "PENDING_APPROVAL"

    # Admin approves & posts it
    app_adj = client.post(f"/api/v1/inventory/adjustments/{adj_id}/approve", headers=adm)
    assert app_adj.status_code == 200, app_adj.text
    assert app_adj.json()["status"] == "POSTED"

    ov = _overview_map(client, adm)
    flr = ov["MAT-FLR"]
    assert Decimal(flr["physical_qty_base"]) == Decimal("40000.000")
    assert Decimal(flr["adjusted_qty_base"]) == Decimal("-60000.000")
    assert flr["is_low_stock"] is True  # 40 kg < 50 kg reorder threshold!

    # Attempting adjustment exceeding physical stock is blocked cleanly (no negative stock)
    neg_adj = client.post(
        "/api/v1/inventory/adjustments",
        headers=adm,
        json={
            "item_type": "MATERIAL",
            "item_id": refs["flr"],
            "adjustment_type": "DAMAGED",
            "entered_qty": "-45",
            "entered_uom": "kg",
            "reason": "Exceeds physical stock of 40 kg",
            "post_immediately": True,
        },
    )
    assert neg_adj.status_code == 409
    assert neg_adj.json()["error"]["code"] == "INSUFFICIENT_STOCK"

    # Phase 5 Sales Order Reservation consistency check on FG Murukku (50 pkts physical):
    # Salesman creates & Admin approves 30 pkts order -> 30 reserved, 20 available
    order = client.post(
        "/api/v1/orders",
        headers=sm_a,
        json={
            "customer_id": refs["ret_a"],
            "client_order_id": str(uuid4()),
            "items": [{"pack_size_id": refs["mrk"], "ordered_qty_pkts": 30}],
        },
    ).json()
    client.post(f"/api/v1/admin/orders/{order['id']}/approve", headers=adm, json={})

    ov_fg = _overview_map(client, adm)["MRK-200G"]
    assert Decimal(ov_fg["physical_qty_base"]) == Decimal("50.000")
    assert Decimal(ov_fg["reserved_qty_base"]) == Decimal("30.000")
    assert Decimal(ov_fg["available_qty_base"]) == Decimal("20.000")

    # Trying to remove 25 pkts (above available 20 pkts) is blocked!
    fg_blocked = client.post(
        "/api/v1/inventory/adjustments",
        headers=adm,
        json={
            "item_type": "PACK_SIZE",
            "item_id": refs["mrk"],
            "adjustment_type": "DAMAGED",
            "entered_qty": "-25",
            "entered_uom": "packet",
            "reason": "Would breach 30-pkt active sales reservation",
            "post_immediately": True,
        },
    )
    assert fg_blocked.status_code == 409
    assert fg_blocked.json()["error"]["code"] == "INSUFFICIENT_AVAILABLE_STOCK"

    # Audit logs recorded supplier_return / stock_adjustment approval
    aud_rows = db_session.execute(
        select(AuditLog).where(AuditLog.entity_table == "stock_adjustments")
    ).scalars().all()
    assert len(aud_rows) >= 2

    # Supervisor creates another adjustment that Admin rejects -> balance unchanged
    req_rej = client.post(
        "/api/v1/inventory/adjustments",
        headers=supv,
        json={
            "item_type": "MATERIAL",
            "item_id": refs["oil"],
            "adjustment_type": "OTHER",
            "entered_qty": "-5",
            "entered_uom": "L",
            "reason": "Testing rejection leaves balance untouched",
        },
    )
    assert req_rej.status_code == 201
    rej_adj = client.post(
        f"/api/v1/inventory/adjustments/{req_rej.json()['id']}/reject",
        headers=adm,
        json={"reason": "Physical re-count confirmed oil tins intact"},
    )
    assert rej_adj.status_code == 200
    assert rej_adj.json()["status"] == "REJECTED"
    db_adj = db_session.execute(
        select(StockAdjustment).where(StockAdjustment.id == req_rej.json()["id"])
    ).scalar_one()
    assert db_adj.status == "REJECTED"
    assert Decimal(_overview_map(client, adm)["MAT-OIL"]["physical_qty_base"]) == Decimal("30000.000")


def test_ledger_immutability_and_db_negative_stock_constraints(db_session: Session) -> None:
    refs = _get_seeded_refs(db_session)
    mov = db_session.execute(
        select(InventoryMovement).where(InventoryMovement.material_id == refs["flr"]).limit(1)
    ).scalar_one()

    try:
        db_session.execute(
            text("UPDATE inventory.inventory_movements SET signed_qty_base = 999 WHERE id = :id"),
            {"id": mov.id},
        )
        db_session.commit()
        raise AssertionError("UPDATE on inventory_movements must be blocked")
    except DBAPIError:
        db_session.rollback()

    try:
        db_session.execute(
            text("DELETE FROM inventory.inventory_movements WHERE id = :id"),
            {"id": mov.id},
        )
        db_session.commit()
        raise AssertionError("DELETE on inventory_movements must be blocked")
    except DBAPIError:
        db_session.rollback()

    try:
        db_session.execute(
            text("UPDATE inventory.inventory_balances SET on_hand_qty_base = -1 WHERE material_id = :mid"),
            {"mid": refs["flr"]},
        )
        db_session.commit()
        raise AssertionError("Negative on_hand_qty_base must be blocked")
    except DBAPIError:
        db_session.rollback()


def test_rbac_boundaries_and_stock_reports_summary(client: TestClient, db_session: Session) -> None:
    refs = _get_seeded_refs(db_session)
    sm_a = login_and_get_headers(client, "salesman_a")
    aud = login_and_get_headers(client, "auditor")
    own = login_and_get_headers(client, "owner")
    supv = login_and_get_headers(client, "supervisor")

    # Salesman is strictly blocked from purchasing & inventory internals
    for url in [
        "/api/v1/purchasing/suppliers",
        "/api/v1/purchasing/orders",
        "/api/v1/purchasing/receipts",
        "/api/v1/inventory/overview",
        "/api/v1/inventory/ledger",
        "/api/v1/inventory/reports/summary",
    ]:
        assert client.get(url, headers=sm_a).status_code == 403

    # Supervisor is blocked from Sales Orders (RBAC separation) & Supplier create
    assert client.get("/api/v1/admin/orders", headers=supv).status_code == 403
    assert (
        client.post(
            "/api/v1/purchasing/suppliers",
            headers=supv,
            json={
                "code": "SUP-X",
                "name": "No Access",
                "state_name": "Tamil Nadu",
                "state_code": "33",
                "address": "Trichy",
            },
        ).status_code
        == 403
    )

    # Auditor & Owner have full read access & zero mutation rights
    for ro_headers in (aud, own):
        rep = client.get("/api/v1/inventory/reports/summary", headers=ro_headers)
        assert rep.status_code == 200
        body = rep.json()
        assert len(body["current_stock"]) == 6
        assert (
            client.post(
                "/api/v1/purchasing/orders",
                headers=ro_headers,
                json={
                    "supplier_id": refs["sup_1"],
                    "items": [
                        {
                            "material_id": refs["flr"],
                            "entered_qty": "10",
                            "entered_uom": "kg",
                            "unit_rate_paisa": 4500,
                        }
                    ],
                },
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/inventory/adjustments",
                headers=ro_headers,
                json={
                    "item_type": "MATERIAL",
                    "item_id": refs["flr"],
                    "adjustment_type": "DAMAGED",
                    "entered_qty": "-1",
                    "entered_uom": "kg",
                    "reason": "Readonly role blocked",
                },
            ).status_code
            == 403
        )


def test_concurrent_receipt_post_and_concurrent_adjustments_prevent_corruption(
    client: TestClient, db_session: Session
) -> None:
    refs = _get_seeded_refs(db_session)
    adm = login_and_get_headers(client, "admin")
    supv = login_and_get_headers(client, "supervisor")

    # Prepare one VERIFIED Goods Receipt (10 kg Oil) and two PENDING -20 kg Adjustments against 30 L Oil
    # Wait: use Flour (100 kg) for concurrent -70 kg reductions, and Oil for receipt double-post test!
    gr = client.post(
        "/api/v1/purchasing/receipts",
        headers=supv,
        json={
            "client_receipt_id": str(uuid4()),
            "supplier_id": refs["sup_1"],
            "submit_immediately": True,
            "items": [
                {
                    "material_id": refs["oil"],
                    "entered_uom": "L",
                    "received_qty_entered": "10",
                    "rejected_qty_entered": "0",
                    "unit_rate_paisa": 14500,
                }
            ],
        },
    ).json()
    client.post(f"/api/v1/purchasing/receipts/{gr['id']}/verify", headers=adm)

    adj1 = client.post(
        "/api/v1/inventory/adjustments",
        headers=supv,
        json={
            "item_type": "MATERIAL",
            "item_id": refs["flr"],
            "adjustment_type": "DAMAGED",
            "entered_qty": "-70",
            "entered_uom": "kg",
            "reason": "Concurrent adjustment check one",
        },
    ).json()
    adj2 = client.post(
        "/api/v1/inventory/adjustments",
        headers=supv,
        json={
            "item_type": "MATERIAL",
            "item_id": refs["flr"],
            "adjustment_type": "MISSING",
            "entered_qty": "-70",
            "entered_uom": "kg",
            "reason": "Concurrent adjustment check two",
        },
    ).json()
    db_session.commit()

    def thread_safe_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    prev_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = thread_safe_get_db
    try:
        def post_gr() -> int:
            with TestClient(app) as c:
                return c.post(f"/api/v1/purchasing/receipts/{gr['id']}/post", headers=adm).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(post_gr)
            f2 = pool.submit(post_gr)
            gr_statuses = sorted([f1.result(), f2.result()])

        assert gr_statuses == [200, 409], f"Expected [200, 409] on concurrent GR post, got {gr_statuses}"

        def approve_adj(aid: int) -> int:
            with TestClient(app) as c:
                return c.post(f"/api/v1/inventory/adjustments/{aid}/approve", headers=adm).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            a1 = pool.submit(approve_adj, adj1["id"])
            a2 = pool.submit(approve_adj, adj2["id"])
            adj_statuses = sorted([a1.result(), a2.result()])

        assert adj_statuses == [200, 409], f"Expected [200, 409] on competing reductions, got {adj_statuses}"
    finally:
        if prev_override is not None:
            app.dependency_overrides[get_db] = prev_override

    db_session.expire_all()
    oil_bal = db_session.execute(
        select(InventoryBalance).where(InventoryBalance.material_id == refs["oil"])
    ).scalar_one()
    flr_bal = db_session.execute(
        select(InventoryBalance).where(InventoryBalance.material_id == refs["flr"])
    ).scalar_one()
    assert Decimal(oil_bal.on_hand_qty_base) == Decimal("40000.000")  # 30 L + 10 L ONCE!
    assert Decimal(flr_bal.on_hand_qty_base) == Decimal("30000.000")  # 100 kg - 70 kg ONCE!

    pur_mov_count = db_session.execute(
        select(func.count(InventoryMovement.id)).where(
            InventoryMovement.material_id == refs["oil"],
            InventoryMovement.movement_type == "PURCHASE_IN",
        )
    ).scalar_one()
    assert pur_mov_count == 1
