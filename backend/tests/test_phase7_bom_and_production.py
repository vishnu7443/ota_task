"""Comprehensive Phase 7 automated tests for BOM Management, BOM Calculation, Production Execution,
Atomic Posting, Variance Analysis, Inventory Integration, Concurrency, Rollback, RBAC, and Benchmark Validation."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
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
from app.modules.production.models import ProductionRun
from app.modules.purchasing.models import Supplier
from app.modules.sales.models import PackSize, Product
from tests.conftest import TestSessionLocal, login_and_get_headers


def _refs(db: Session) -> dict[str, int]:
    sup = db.execute(select(Supplier).where(Supplier.code == "SUP-001")).scalar_one()
    prod = db.execute(select(Product).where(Product.product_code == "PROD-MRK")).scalar_one()
    mrk = db.execute(select(PackSize).where(PackSize.sku_code == "MRK-200G")).scalar_one()
    flr = db.execute(select(Material).where(Material.code == "MAT-FLR")).scalar_one()
    oil = db.execute(select(Material).where(Material.code == "MAT-OIL")).scalar_one()
    spc = db.execute(select(Material).where(Material.code == "MAT-SPC")).scalar_one()
    pch = db.execute(select(Material).where(Material.code == "MAT-PCH-200")).scalar_one()
    ctn = db.execute(select(Material).where(Material.code == "MAT-CTN-20")).scalar_one()
    return {
        "sup": sup.id,
        "prod": prod.id,
        "mrk": mrk.id,
        "flr": flr.id,
        "oil": oil.id,
        "spc": spc.id,
        "pch": pch.id,
        "ctn": ctn.id,
    }


def _ov_map(client: TestClient, headers: dict[str, str]) -> dict[str, dict]:
    resp = client.get("/api/v1/inventory/overview", headers=headers)
    assert resp.status_code == 200, resp.text
    return {item["code"]: item for item in resp.json()["items"]}


def test_1_bom_creation_pack_size_extensibility_and_version_immutability(
    client: TestClient, db_session: Session
) -> None:
    """Tests 1, 2 & DB-level immutability: Create Murukku 500 g sharing product, draft BOM edit, activation, and immutability."""
    refs = _refs(db_session)
    supv = login_and_get_headers(client, "supervisor")
    adm = login_and_get_headers(client, "admin")

    # Seeded Murukku 200 g BOM v1 is already active
    boms = client.get("/api/v1/production/bom", headers=supv)
    assert boms.status_code == 200, boms.text
    bom_200 = next(b for b in boms.json() if b["sku_code"] == "MRK-200G")
    assert bom_200["active_version"]["version_no"] == 1
    assert bom_200["active_version"]["expected_yield_pkts"] == 200
    assert bom_200["active_version"]["is_locked"] is True

    # Live interview scenario readiness: add Murukku 500 g pack size & 500 g pouch sharing same Murukku product
    ps_500 = client.post(
        "/api/v1/production/catalog/pack-sizes",
        headers=adm,
        json={
            "product_id": refs["prod"],
            "sku_code": "MRK-500G",
            "display_name": "Murukku 500 g",
            "pack_weight_g": 500,
            "packets_per_carton": 10,
            "base_selling_price_paisa": 12000,
        },
    )
    assert ps_500.status_code == 201, ps_500.text
    ps500_id = ps_500.json()["id"]

    pch_500 = client.post(
        "/api/v1/production/catalog/materials",
        headers=supv,
        json={
            "code": "MAT-PCH-500",
            "name": "500 g pouch",
            "material_category": "PACKAGING_MATERIAL",
            "unit_dimension": "COUNT",
            "display_uom": "piece",
            "reorder_level_display": "100",
        },
    )
    assert pch_500.status_code == 201, pch_500.text
    pch500_id = pch_500.json()["id"]

    # Create DRAFT BOM v1 for Murukku 500 g (sharing cooking base yield 40 kg -> 80 packets of 500 g)
    catalog = client.get("/api/v1/production/catalog", headers=supv).json()
    tpl_id = catalog["recipe_templates"][0]["id"]

    v1_draft = client.post(
        "/api/v1/production/bom/versions",
        headers=supv,
        json={
            "pack_size_id": ps500_id,
            "recipe_template_id": tpl_id,
            "expected_yield_pkts": 80,
            "notes": "Initial 500 g draft recipe",
            "activate": False,
            "components": [
                {"material_id": refs["flr"], "input_role": "COOKING_RAW", "display_qty": "40", "display_uom": "kg"},
                {"material_id": refs["oil"], "input_role": "COOKING_RAW", "display_qty": "10", "display_uom": "L"},
                {"material_id": refs["spc"], "input_role": "COOKING_RAW", "display_qty": "1200", "display_uom": "g"},
                {"material_id": pch500_id, "input_role": "PACKAGING", "display_qty": "80", "display_uom": "piece"},
                {"material_id": refs["ctn"], "input_role": "PACKAGING", "display_qty": "8", "display_uom": "piece"},
            ],
        },
    )
    assert v1_draft.status_code == 201, v1_draft.text
    draft_id = v1_draft.json()["id"]
    assert v1_draft.json()["status"] == "DRAFT"

    # DRAFT BOM version can be edited cleanly
    draft_edit = client.put(
        f"/api/v1/production/bom/versions/{draft_id}",
        headers=supv,
        json={
            "expected_yield_pkts": 80,
            "notes": "Updated draft note",
            "components": [
                {"material_id": refs["flr"], "input_role": "COOKING_RAW", "display_qty": "40", "display_uom": "kg"},
                {"material_id": refs["oil"], "input_role": "COOKING_RAW", "display_qty": "10", "display_uom": "L"},
                {"material_id": refs["spc"], "input_role": "COOKING_RAW", "display_qty": "1.2", "display_uom": "kg"},
                {"material_id": pch500_id, "input_role": "PACKAGING", "display_qty": "80", "display_uom": "piece"},
                {"material_id": refs["ctn"], "input_role": "PACKAGING", "display_qty": "8", "display_uom": "piece"},
            ],
        },
    )
    assert draft_edit.status_code == 200, draft_edit.text
    assert draft_edit.json()["notes"] == "Updated draft note"

    # Activate DRAFT BOM v1
    act_resp = client.post(f"/api/v1/production/bom/versions/{draft_id}/activate", headers=supv)
    assert act_resp.status_code == 200, act_resp.text
    assert act_resp.json()["status"] == "ACTIVE"
    assert act_resp.json()["is_locked"] is True

    # Editing or deleting an ACTIVE BOM version is strictly blocked!
    upd_blocked = client.put(
        f"/api/v1/production/bom/versions/{draft_id}",
        headers=supv,
        json={
            "expected_yield_pkts": 85,
            "components": [
                {"material_id": refs["flr"], "input_role": "COOKING_RAW", "display_qty": "40", "display_uom": "kg"},
            ],
        },
    )
    assert upd_blocked.status_code == 409
    assert upd_blocked.json()["error"]["code"] == "IMMUTABLE_BOM_VERSION"

    del_blocked = client.delete(f"/api/v1/production/bom/versions/{draft_id}", headers=supv)
    assert del_blocked.status_code == 409

    # PostgreSQL trigger also blocks direct SQL modification on ACTIVE/SUPERSEDED BOM versions!
    try:
        db_session.execute(
            text("UPDATE production.bom_versions SET expected_yield_pkts = 999 WHERE id = :vid"),
            {"vid": draft_id},
        )
        db_session.commit()
        raise AssertionError("Trigger must forbid direct UPDATE of active BOM version")
    except DBAPIError:
        db_session.rollback()


def test_2_bom_calculator_scaling_unit_conversions_and_rounding(
    client: TestClient, db_session: Session
) -> None:
    """Tests 3, 4, 5: Decimal scaling, unit conversions (1.2 kg == 1200 g), incompatible unit reject, indivisible carton ceiling rounding."""
    refs = _refs(db_session)
    supv = login_and_get_headers(client, "supervisor")

    # Test scaling to target 150 packets (0.75 batch multiplier on 200-pkt BOM):
    # Raw: 30 kg Flour, 7.5 L Oil, 0.9 kg Spice
    # Packaging: 150 pouches exact, Cartons: 10 * 0.75 = 7.5 -> rounded UP to 8 indivisible cartons!
    calc = client.post(
        "/api/v1/production/bom/calculate",
        headers=supv,
        json={"pack_size_id": refs["mrk"], "target_output_pkts": 150},
    )
    assert calc.status_code == 200, calc.text
    c = calc.json()
    assert Decimal(c["batch_multiplier"]) == Decimal("0.7500")
    assert c["expected_output_pkts"] == 150
    by_code = {r["material_code"]: r for r in c["requirements"]}
    assert Decimal(by_code["MAT-FLR"]["standard_qty_base"]) == Decimal("30000.000")
    assert Decimal(by_code["MAT-OIL"]["standard_qty_base"]) == Decimal("7500.000")
    assert Decimal(by_code["MAT-SPC"]["standard_qty_base"]) == Decimal("900.000")
    assert Decimal(by_code["MAT-PCH-200"]["standard_qty_base"]) == Decimal("150.000")
    assert by_code["MAT-CTN-20"]["was_rounded_up"] is True
    assert Decimal(by_code["MAT-CTN-20"]["exact_scaled_qty_base"]) == Decimal("7.500")
    assert Decimal(by_code["MAT-CTN-20"]["standard_qty_base"]) == Decimal("8.000")
    assert c["has_shortages"] is False

    # Test massive scale (4 batches = 800 packets): triggers exact material shortages against opening stock!
    # Flour need 160 kg vs 100 kg avail -> short 60 kg; Oil need 40 L vs 30 L -> short 10 L
    calc_big = client.get(
        f"/api/v1/production/bom/{refs['mrk']}/calculate?batch_multiplier=4.0",
        headers=supv,
    )
    assert calc_big.status_code == 200, calc_big.text
    big = calc_big.json()
    assert big["has_shortages"] is True
    big_map = {r["material_code"]: r for r in big["requirements"]}
    assert big_map["MAT-FLR"]["is_shortage"] is True
    assert Decimal(big_map["MAT-FLR"]["additional_required_base"]) == Decimal("60000.000")
    assert big_map["MAT-OIL"]["is_shortage"] is True
    assert Decimal(big_map["MAT-OIL"]["additional_required_base"]) == Decimal("10000.000")

    # Cross-dimension unit mismatch in BOM creation (Flour measured in 'L' instead of MASS) rejected cleanly!
    bad_uom = client.post(
        "/api/v1/production/bom/versions",
        headers=supv,
        json={
            "pack_size_id": refs["mrk"],
            "expected_yield_pkts": 200,
            "components": [
                {"material_id": refs["flr"], "input_role": "COOKING_RAW", "display_qty": "40", "display_uom": "L"},
            ],
        },
    )
    assert bad_uom.status_code == 422


def test_3_benchmark_end_to_end_purchase_production_posting_variance_and_ledger(
    client: TestClient, db_session: Session
) -> None:
    """Tests 6, 7, 8, 10, 11, 12, 13, 14 & Official NIT Trichy Benchmark Steps 1-3 + Variance Validation."""
    refs = _refs(db_session)
    adm = login_and_get_headers(client, "admin")
    supv = login_and_get_headers(client, "supervisor")

    # Benchmark Step 1: Record purchase of 60 kg Flour @ ₹45/kg -> Flour = 160 kg
    gr = client.post(
        "/api/v1/purchasing/receipts",
        headers=supv,
        json={
            "client_receipt_id": str(uuid4()),
            "supplier_id": refs["sup"],
            "supplier_bill_ref": "CAM-BM-001",
            "receipt_date": "2026-11-25",
            "submit_immediately": True,
            "items": [
                {
                    "material_id": refs["flr"],
                    "entered_uom": "kg",
                    "received_qty_entered": "60",
                    "rejected_qty_entered": "0",
                    "unit_rate_paisa": 4500,
                    "gst_rate_bps": 0,
                    "batch_code": "FLR-LOT-2",
                }
            ],
        },
    ).json()
    client.post(f"/api/v1/purchasing/receipts/{gr['id']}/verify", headers=adm)
    client.post(f"/api/v1/purchasing/receipts/{gr['id']}/post", headers=adm)
    assert Decimal(_ov_map(client, adm)["MAT-FLR"]["physical_qty_base"]) == Decimal("160000.000")

    # Benchmark Step 2: Plan production run (DRAFT -> PLANNED)
    draft_run = client.post(
        "/api/v1/production/runs",
        headers=supv,
        json={
            "pack_size_id": refs["mrk"],
            "batch_multiplier": "1.0",
            "run_date": "2026-11-25",
            "notes": "Benchmark batch PRD-001",
            "plan_immediately": False,
        },
    )
    assert draft_run.status_code == 201, draft_run.text
    run_id = draft_run.json()["id"]
    assert draft_run.json()["status"] == "DRAFT"
    assert draft_run.json()["expected_output_pkts"] == 200

    # Cannot issue materials from DRAFT before planning
    premature_issue = client.post(
        f"/api/v1/production/runs/{run_id}/issue-materials",
        headers=supv,
        json={"items": [{"material_id": refs["flr"], "issued_qty": "40", "issued_uom": "kg"}]},
    )
    assert premature_issue.status_code == 409

    planned = client.post(f"/api/v1/production/runs/{run_id}/plan", headers=supv)
    assert planned.status_code == 200 and planned.json()["status"] == "PLANNED"

    # Start Production & Issue Raw Materials + Packaging (or raw at Start, packaging at completion — test raw + exact pkg split)
    # Using exact gram/kg unit mixing (1200 g == 1.2 kg for Spice mix!)
    started = client.post(
        f"/api/v1/production/runs/{run_id}/issue-materials",
        headers=supv,
        json={
            "items": [
                {"material_id": refs["flr"], "issued_qty": "40", "issued_uom": "kg"},
                {"material_id": refs["oil"], "issued_qty": "10.5", "issued_uom": "L"},
                {"material_id": refs["spc"], "issued_qty": "1200", "issued_uom": "g"},
            ]
        },
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "IN_PROGRESS"

    # Double material issue strictly prevented!
    double_issue = client.post(
        f"/api/v1/production/runs/{run_id}/issue-materials",
        headers=supv,
        json={"items": [{"material_id": refs["flr"], "issued_qty": "40", "issued_uom": "kg"}]},
    )
    assert double_issue.status_code == 409
    assert double_issue.json()["error"]["code"] == "DOUBLE_MATERIAL_ISSUE"

    # Benchmark Step 3: Record execution completion -> 188 good packets, 6 damaged pouches, 9 cartons used!
    completed = client.post(
        f"/api/v1/production/runs/{run_id}/complete",
        headers=supv,
        json={
            "good_output_pkts": 188,
            "rejected_output_pkts": 0,
            "batch_code": "MRK-20261125-01",
            "expiry_date": "2027-02-25",
            "quality_remarks": "Heat sealer jammed on 6 empty pouches; 0 rejected finished goods",
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
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["actual_good_output_pkts"] == 188
    assert completed.json()["rejected_output_pkts"] == 0

    # Before final Posting, Finished Goods must STILL be opening 50 packets!
    assert Decimal(_ov_map(client, adm)["MRK-200G"]["physical_qty_base"]) == Decimal("50.000")

    # Atomic Production Posting (COMPLETED -> POSTED)
    posted = client.post(f"/api/v1/production/runs/{run_id}/post", headers=supv)
    assert posted.status_code == 200, posted.text
    run_data = posted.json()
    assert run_data["status"] == "POSTED"

    # Duplicate posting strictly prevented!
    dup_post = client.post(f"/api/v1/production/runs/{run_id}/post", headers=supv)
    assert dup_post.status_code == 409
    assert dup_post.json()["error"]["code"] == "DUPLICATE_POST"

    # Verify EXACT Section 5 Benchmark Closing Balances!
    ov = _ov_map(client, adm)
    assert Decimal(ov["MAT-FLR"]["physical_qty_base"]) == Decimal("120000.000")  # 120 kg (100 + 60 - 40)
    assert Decimal(ov["MAT-OIL"]["physical_qty_base"]) == Decimal("19500.000")   # 19.5 L (30 - 10.5)
    assert Decimal(ov["MAT-SPC"]["physical_qty_base"]) == Decimal("3800.000")    # 3.8 kg (5 - 1.2)
    assert Decimal(ov["MAT-PCH-200"]["physical_qty_base"]) == Decimal("306.000") # 306 pcs (500 - 188 - 6)
    assert Decimal(ov["MAT-CTN-20"]["physical_qty_base"]) == Decimal("21.000")   # 21 pcs (30 - 9)
    assert Decimal(ov["MRK-200G"]["physical_qty_base"]) == Decimal("238.000")    # 238 pkts (50 + 188)

    # Verify FIFO CostLot value matches opening lot consumption first (40 kg @ ₹42 = ₹1,680 left, 60 kg @ ₹42 + 60 kg @ ₹45 remain = ₹5,220)
    assert ov["MAT-FLR"]["open_lot_value_paisa"] == (60 * 4200) + (60 * 4500)  # 522000 paisa = ₹5,220

    # Verify EXACT Yield (-6.00% FLAGGED), Oil (+5.00% FLAGGED), Pouches Output-Scaled (+3.19% FLAGGED) Variances!
    v_by_key = {(v["variance_scope"], v["material_code"]): v for v in run_data["variances"]}
    assert Decimal(v_by_key[("YIELD", None)]["variance_pct"]) == Decimal("-6.00")
    assert v_by_key[("YIELD", None)]["is_flagged"] is True

    assert Decimal(v_by_key[("RAW_CONSUMPTION", "MAT-OIL")]["variance_pct"]) == Decimal("5.00")
    assert v_by_key[("RAW_CONSUMPTION", "MAT-OIL")]["is_flagged"] is True

    assert Decimal(v_by_key[("RAW_CONSUMPTION", "MAT-FLR")]["variance_pct"]) == Decimal("0.00")
    assert v_by_key[("RAW_CONSUMPTION", "MAT-FLR")]["is_flagged"] is False

    assert Decimal(v_by_key[("PACKAGING_OUTPUT_SCALED", "MAT-PCH-200")]["variance_pct"]) == Decimal("3.19")
    assert v_by_key[("PACKAGING_OUTPUT_SCALED", "MAT-PCH-200")]["is_flagged"] is True

    assert Decimal(v_by_key[("PACKAGING_OUTPUT_SCALED", "MAT-CTN-20")]["variance_pct"]) == Decimal("0.00")
    assert Decimal(v_by_key[("PACKAGING_BATCH_BOM", "MAT-CTN-20")]["variance_pct"]) == Decimal("-10.00")

    # Verify Production Ledger Movements linked strictly to production_run_id + CostLotConsumption recorded
    movs = db_session.execute(
        select(InventoryMovement).where(InventoryMovement.production_run_id == run_id)
    ).scalars().all()
    mtypes = {m.movement_type for m in movs}
    assert {"PROD_ISSUE_OUT", "PACKAGING_DAMAGE_OUT", "PROD_OUTPUT_IN"}.issubset(mtypes)
    for m in movs:
        assert m.source_doc_type == "PRODUCTION_RUN"
        assert m.reference_code == run_data["run_number"]

    clc_count = db_session.execute(select(CostLotConsumption)).scalars().all()
    assert len(clc_count) >= 5

    # Verify VarianceAlerts created & visible on Production Dashboard
    dash = client.get("/api/v1/production/dashboard", headers=adm).json()
    assert dash["posted_count"] == 1
    assert dash["total_good_output_pkts"] == 188
    assert dash["flagged_variance_count"] == 1
    assert dash["open_alerts_count"] == 3  # Yield -6%, Oil +5%, Pouches +3.19%
    alert_id = dash["open_alerts"][0]["id"]
    ack = client.post(
        f"/api/v1/production/alerts/{alert_id}/acknowledge",
        headers=adm,
        json={"note": "Reviewed oil over-issue and heat-sealer calibration scheduled"},
    )
    assert ack.status_code == 200 and ack.json()["status"] == "ACKNOWLEDGED"

    # Zero drift reconciliation between Ledger SUM and InventoryBalance
    for mat_id in (refs["flr"], refs["oil"], refs["spc"], refs["pch"], refs["ctn"]):
        bal = db_session.execute(select(InventoryBalance).where(InventoryBalance.material_id == mat_id)).scalar_one()
        mov_sum = sum(
            Decimal(m.signed_qty_base)
            for m in db_session.execute(select(InventoryMovement).where(InventoryMovement.material_id == mat_id)).scalars().all()
        )
        assert Decimal(bal.on_hand_qty_base) == mov_sum


def test_4_unused_material_returns_and_rejected_output_excluded_from_fg_stock(
    client: TestClient, db_session: Session
) -> None:
    """Tests 9, 10, 11: Issuing packaging at Start, returning unused pouches/cartons via PROD_RETURN_IN, and keeping rejected FG separate."""
    refs = _refs(db_session)
    supv = login_and_get_headers(client, "supervisor")

    run = client.post(
        "/api/v1/production/runs",
        headers=supv,
        json={"pack_size_id": refs["mrk"], "batch_multiplier": "1.0", "plan_immediately": True},
    ).json()
    rid = run["id"]

    # Issue ALL 5 BOM items at Start (including 200 pouches & 10 cartons!)
    st = client.post(
        f"/api/v1/production/runs/{rid}/issue-materials",
        headers=supv,
        json={
            "items": [
                {"material_id": refs["flr"], "issued_qty": "40", "issued_uom": "kg"},
                {"material_id": refs["oil"], "issued_qty": "10", "issued_uom": "L"},
                {"material_id": refs["spc"], "issued_qty": "1.2", "issued_uom": "kg"},
                {"material_id": refs["pch"], "issued_qty": "200", "issued_uom": "piece"},
                {"material_id": refs["ctn"], "issued_qty": "10", "issued_uom": "piece"},
            ]
        },
    )
    assert st.status_code == 200, st.text
    # Immediately on Start, pouches drop 500 -> 300 and cartons drop 30 -> 20
    assert Decimal(_ov_map(client, supv)["MAT-PCH-200"]["physical_qty_base"]) == Decimal("300.000")
    assert Decimal(_ov_map(client, supv)["MAT-CTN-20"]["physical_qty_base"]) == Decimal("20.000")

    # Complete with 185 good + 3 rejected finished packets, 4 damaged pouches, returning 11 unused pouches & 1 unused carton!
    # Balance check on pouches: 185+3 good/rej packed? Wait: good pouches=188 (185+3), damaged=4 -> consumed=192, returned=8 -> 192+8 = 200 issued!
    cmp = client.post(
        f"/api/v1/production/runs/{rid}/complete",
        headers=supv,
        json={
            "good_output_pkts": 185,
            "rejected_output_pkts": 3,
            "batch_code": "MRK-RET-TEST",
            "quality_remarks": "3 finished packets failed seal test; 4 empty pouches torn",
            "consumptions": [
                {"material_id": refs["flr"], "actual_consumed_qty": "39", "returned_unused_qty": "1", "wasted_qty": "0.5", "uom": "kg"},
                {"material_id": refs["oil"], "actual_consumed_qty": "10", "returned_unused_qty": "0", "uom": "L"},
                {"material_id": refs["spc"], "actual_consumed_qty": "1.2", "returned_unused_qty": "0", "uom": "kg"},
                {
                    "material_id": refs["pch"],
                    "actual_good_used_qty": "188",
                    "damaged_packaging_qty": "4",
                    "returned_unused_qty": "8",
                    "uom": "piece",
                },
                {
                    "material_id": refs["ctn"],
                    "actual_good_used_qty": "9",
                    "damaged_packaging_qty": "0",
                    "returned_unused_qty": "1",
                    "uom": "piece",
                },
            ],
        },
    )
    assert cmp.status_code == 200, cmp.text

    post_resp = client.post(f"/api/v1/production/runs/{rid}/post", headers=supv)
    assert post_resp.status_code == 200, post_resp.text

    ov = _ov_map(client, supv)
    # Flour: 100 - 40 + 1 returned = 61 kg
    assert Decimal(ov["MAT-FLR"]["physical_qty_base"]) == Decimal("61000.000")
    # Pouches: 500 - 200 + 8 returned = 308
    assert Decimal(ov["MAT-PCH-200"]["physical_qty_base"]) == Decimal("308.000")
    # Cartons: 30 - 10 + 1 returned = 21
    assert Decimal(ov["MAT-CTN-20"]["physical_qty_base"]) == Decimal("21.000")
    # Saleable FG stock ONLY increases by 185 good packets (NOT +3 rejected = 188!): 50 + 185 = 235
    assert Decimal(ov["MRK-200G"]["physical_qty_base"]) == Decimal("235.000")

    ret_movs = db_session.execute(
        select(InventoryMovement).where(
            InventoryMovement.production_run_id == rid,
            InventoryMovement.movement_type == "PROD_RETURN_IN",
        )
    ).scalars().all()
    assert len(ret_movs) == 3  # Flour, Pouches, Cartons returned cleanly


def test_5_historical_bom_preservation_when_v2_activated(
    client: TestClient, db_session: Session
) -> None:
    """Test 15 / Part 11: Run posted on BOM v1 keeps exact v1 recipe & quantities even after BOM v2 is created and activated."""
    refs = _refs(db_session)
    supv = login_and_get_headers(client, "supervisor")

    # Create, start, complete, post PRD-1 under v1 (40 kg flour, 200 pkts)
    r1 = client.post(
        "/api/v1/production/runs",
        headers=supv,
        json={"pack_size_id": refs["mrk"], "batch_multiplier": "1.0", "plan_immediately": True},
    ).json()
    rid1 = r1["id"]
    assert r1["version_no"] == 1

    client.post(
        f"/api/v1/production/runs/{rid1}/issue-materials",
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
        f"/api/v1/production/runs/{rid1}/complete",
        headers=supv,
        json={
            "good_output_pkts": 200,
            "batch_code": "V1-BATCH",
            "consumptions": [
                {"material_id": refs["flr"], "actual_consumed_qty": "40", "uom": "kg"},
                {"material_id": refs["oil"], "actual_consumed_qty": "10", "uom": "L"},
                {"material_id": refs["spc"], "actual_consumed_qty": "1.2", "uom": "kg"},
                {"material_id": refs["pch"], "actual_good_used_qty": "200", "uom": "piece"},
                {"material_id": refs["ctn"], "actual_good_used_qty": "10", "uom": "piece"},
            ],
        },
    )
    client.post(f"/api/v1/production/runs/{rid1}/post", headers=supv)

    # Now create & activate BOM v2 changing Flour from 40 -> 45 kg and expected yield 200 -> 225 pkts!
    v2 = client.post(
        "/api/v1/production/bom/versions",
        headers=supv,
        json={
            "pack_size_id": refs["mrk"],
            "expected_yield_pkts": 225,
            "notes": "Expanded 45 kg flour batch recipe v2",
            "activate": True,
            "components": [
                {"material_id": refs["flr"], "input_role": "COOKING_RAW", "display_qty": "45", "display_uom": "kg"},
                {"material_id": refs["oil"], "input_role": "COOKING_RAW", "display_qty": "11", "display_uom": "L"},
                {"material_id": refs["spc"], "input_role": "COOKING_RAW", "display_qty": "1.5", "display_uom": "kg"},
                {"material_id": refs["pch"], "input_role": "PACKAGING", "display_qty": "225", "display_uom": "piece"},
                {"material_id": refs["ctn"], "input_role": "PACKAGING", "display_qty": "12", "display_uom": "piece"},
            ],
        },
    )
    assert v2.status_code == 201 and v2.json()["version_no"] == 2
    assert v2.json()["status"] == "ACTIVE"

    # v1 must now be SUPERSEDED, v2 ACTIVE
    bom_hdr = client.get(f"/api/v1/production/bom/{refs['mrk']}", headers=supv).json()
    versions_by_no = {v["version_no"]: v for v in bom_hdr["all_versions"]}
    assert versions_by_no[1]["status"] == "SUPERSEDED"
    assert versions_by_no[2]["status"] == "ACTIVE"

    # Re-open historical PRD-1 -> MUST still reference BOM v1 with original 40 kg Flour & 200 expected packets!
    hist = client.get(f"/api/v1/production/runs/{rid1}", headers=supv).json()
    assert hist["version_no"] == 1
    assert hist["expected_output_pkts"] == 200
    flr_issue = next(mi for mi in hist["material_issues"] if mi["material_code"] == "MAT-FLR")
    assert Decimal(flr_issue["planned_qty_base"]) == Decimal("40000.000")

    # Meanwhile a new run planned now automatically picks up BOM v2!
    r2 = client.post(
        "/api/v1/production/runs",
        headers=supv,
        json={"pack_size_id": refs["mrk"], "batch_multiplier": "1.0", "plan_immediately": True},
    ).json()
    assert r2["version_no"] == 2
    assert r2["expected_output_pkts"] == 225


def test_6_concurrent_material_issues_and_transaction_rollback(
    client: TestClient, db_session: Session
) -> None:
    """Tests 16 & 17: Concurrent material issue locks prevent negative stock; failed posting rolls back completely."""
    refs = _refs(db_session)
    supv = login_and_get_headers(client, "supervisor")

    # Opening Oil = 30 L. Plan two runs each needing 20 L Oil (batch_multiplier = 2.0) -> total needed 40 L > 30 L!
    run_a = client.post(
        "/api/v1/production/runs",
        headers=supv,
        json={"pack_size_id": refs["mrk"], "batch_multiplier": "2.0", "plan_immediately": True},
    ).json()
    run_b = client.post(
        "/api/v1/production/runs",
        headers=supv,
        json={"pack_size_id": refs["mrk"], "batch_multiplier": "2.0", "plan_immediately": True},
    ).json()

    # Override dependency to use independent sessions per worker thread for genuine PostgreSQL row-lock contention
    def thread_get_db():
        s = TestSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = thread_get_db

    def start_run(rid: int):
        with TestClient(app) as tc:
            return tc.post(
                f"/api/v1/production/runs/{rid}/issue-materials",
                headers=supv,
                json={
                    "items": [
                        {"material_id": refs["flr"], "issued_qty": "40", "issued_uom": "kg"},
                        {"material_id": refs["oil"], "issued_qty": "20", "issued_uom": "L"},
                        {"material_id": refs["spc"], "issued_qty": "2.4", "issued_uom": "kg"},
                    ]
                },
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted([pool.submit(start_run, run_a["id"]).result(), pool.submit(start_run, run_b["id"]).result()])

    assert results == [200, 409]  # Exactly 1 succeeded, 1 blocked!

    # Reset client session override to db_session for remaining assertions
    def reset_get_db():
        yield db_session

    app.dependency_overrides[get_db] = reset_get_db

    db_session.expire_all()
    oil_bal = db_session.execute(select(InventoryBalance).where(InventoryBalance.material_id == refs["oil"])).scalar_one()
    assert Decimal(oil_bal.on_hand_qty_base) == Decimal("10000.000")  # Strictly 10 L left >= 0!

    # Now test Transaction Rollback (Test 17): complete the active run trying to consume MORE pouches than available (600 > 500!)
    active_run_id = next(
        r.id for r in db_session.execute(select(ProductionRun).where(ProductionRun.status == "IN_PROGRESS")).scalars().all()
    )
    cmp = client.post(
        f"/api/v1/production/runs/{active_run_id}/complete",
        headers=supv,
        json={
            "good_output_pkts": 380,
            "batch_code": "ROLLBACK-TEST",
            "consumptions": [
                {"material_id": refs["flr"], "actual_consumed_qty": "40", "uom": "kg"},
                {"material_id": refs["oil"], "actual_consumed_qty": "20", "uom": "L"},
                {"material_id": refs["spc"], "actual_consumed_qty": "2.4", "uom": "kg"},
                {"material_id": refs["pch"], "actual_good_used_qty": "600", "uom": "piece"},  # Exceeds 500 stock!
                {"material_id": refs["ctn"], "actual_good_used_qty": "19", "uom": "piece"},
            ],
        },
    )
    assert cmp.status_code == 200

    fg_before = Decimal(_ov_map(client, supv)["MRK-200G"]["physical_qty_base"])
    ctn_before = Decimal(_ov_map(client, supv)["MAT-CTN-20"]["physical_qty_base"])

    post_fail = client.post(f"/api/v1/production/runs/{active_run_id}/post", headers=supv)
    assert post_fail.status_code == 409
    assert post_fail.json()["error"]["code"] == "INSUFFICIENT_STOCK"

    # Full rollback verified: Run stayed COMPLETED, cartons untouched, zero FG added, zero variance rows written!
    db_session.expire_all()
    run_after = db_session.execute(select(ProductionRun).where(ProductionRun.id == active_run_id)).scalar_one()
    assert run_after.status == "COMPLETED"
    assert len(run_after.variances) == 0
    assert Decimal(_ov_map(client, supv)["MRK-200G"]["physical_qty_base"]) == fg_before
    assert Decimal(_ov_map(client, supv)["MAT-CTN-20"]["physical_qty_base"]) == ctn_before


def test_7_rbac_isolation_across_all_roles(client: TestClient, db_session: Session) -> None:
    """RBAC enforcement: Salesman blocked completely (403); Auditor/Owner strictly read-only (403 mutations)."""
    refs = _refs(db_session)
    sm_a = login_and_get_headers(client, "salesman_a")
    aud = login_and_get_headers(client, "auditor")
    own = login_and_get_headers(client, "owner")

    # Salesman strictly forbidden on all production endpoints
    for method, url, body in [
        ("GET", "/api/v1/production/catalog", None),
        ("GET", "/api/v1/production/bom", None),
        ("GET", "/api/v1/production/dashboard", None),
        ("GET", f"/api/v1/production/bom/{refs['mrk']}/calculate?batch_multiplier=1", None),
        ("POST", "/api/v1/production/runs", {"pack_size_id": refs["mrk"], "batch_multiplier": "1"}),
    ]:
        if method == "GET":
            assert client.get(url, headers=sm_a).status_code == 403
        else:
            assert client.post(url, headers=sm_a, json=body).status_code == 403

    # Auditor & Owner can READ BOM, Calculator, Dashboard, Variance Report; CANNOT mutate
    for ro in (aud, own):
        assert client.get("/api/v1/production/bom", headers=ro).status_code == 200
        assert client.get("/api/v1/production/dashboard", headers=ro).status_code == 200
        assert client.get("/api/v1/production/reports/variances", headers=ro).status_code == 200
        assert (
            client.get(f"/api/v1/production/bom/{refs['mrk']}/calculate?batch_multiplier=1", headers=ro).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/production/runs",
                headers=ro,
                json={"pack_size_id": refs["mrk"], "batch_multiplier": "1"},
            ).status_code
            == 403
        )


def test_8_insufficient_material_blocks_start_and_abort_handles_returns_and_scrap(
    client: TestClient, db_session: Session
) -> None:
    """EC-05 & EC-06: Insufficient stock blocks start cleanly; aborting IN_PROGRESS run handles partial returns vs scrap."""
    refs = _refs(db_session)
    supv = login_and_get_headers(client, "supervisor")

    run = client.post(
        "/api/v1/production/runs",
        headers=supv,
        json={"pack_size_id": refs["mrk"], "batch_multiplier": "1.0", "plan_immediately": True},
    ).json()
    rid = run["id"]

    # Attempt to start issuing 35 L Oil (> 30 L opening balance) alongside valid 40 kg Flour -> blocked atomically!
    blocked = client.post(
        f"/api/v1/production/runs/{rid}/issue-materials",
        headers=supv,
        json={
            "items": [
                {"material_id": refs["flr"], "issued_qty": "40", "issued_uom": "kg"},
                {"material_id": refs["oil"], "issued_qty": "35", "issued_uom": "L"},
                {"material_id": refs["spc"], "issued_qty": "1.2", "issued_uom": "kg"},
            ]
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    # Verify Flour & Spice were NOT deducted
    ov_after_block = _ov_map(client, supv)
    assert Decimal(ov_after_block["MAT-FLR"]["physical_qty_base"]) == Decimal("100000.000")
    assert Decimal(ov_after_block["MAT-SPC"]["physical_qty_base"]) == Decimal("5000.000")

    # Now start legitimately with 40 kg Flour, 10 L Oil, 1.2 kg Spice
    started = client.post(
        f"/api/v1/production/runs/{rid}/issue-materials",
        headers=supv,
        json={
            "items": [
                {"material_id": refs["flr"], "issued_qty": "40", "issued_uom": "kg"},
                {"material_id": refs["oil"], "issued_qty": "10", "issued_uom": "L"},
                {"material_id": refs["spc"], "issued_qty": "1.2", "issued_uom": "kg"},
            ]
        },
    )
    assert started.status_code == 200

    # Batch burns mid-fry! 15 kg unused Flour salvaged & returned; remaining 25 kg Flour + 10 L Oil + 1.2 kg Spice lost to scrap
    aborted = client.post(
        f"/api/v1/production/runs/{rid}/cancel",
        headers=supv,
        json={
            "reason": "Power failure spoiled fryer batch; 15 kg dry flour bags returned to store",
            "returned_items": [
                {"material_id": refs["flr"], "returned_qty": "15", "uom": "kg"},
                {"material_id": refs["oil"], "returned_qty": "0", "uom": "L"},
            ],
        },
    )
    assert aborted.status_code == 200, aborted.text
    assert aborted.json()["status"] == "CANCELLED"

    # Flour: 100 - 40 + 15 returned = 75 kg!
    assert Decimal(_ov_map(client, supv)["MAT-FLR"]["physical_qty_base"]) == Decimal("75000.000")
    assert Decimal(_ov_map(client, supv)["MAT-OIL"]["physical_qty_base"]) == Decimal("20000.000")
    assert len(aborted.json()["wastages"]) == 3  # Flour (25kg), Oil (10L), Spice (1.2kg) logged as BURNT_BATCH scrap
