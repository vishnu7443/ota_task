"""Idempotent development & benchmark master seed script.

Seeds ONLY fictional master data and opening stock from NIT Trichy Section 5.
Explicitly does NOT pre-create any sales orders so the vertical slice can be
demonstrated end-to-end from the mobile salesman UI.
"""

import logging
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.iam.models import CompanyProfile, Role, User
from app.modules.inventory import service as inventory_service
from app.modules.inventory.models import Material, UnitConversion
from app.modules.production.models import (
    BomComponent,
    BomHeader,
    BomVersion,
    RecipeTemplate,
)
from app.modules.purchasing.models import Supplier
from app.modules.sales.models import (
    Customer,
    CustomerAddress,
    PackSize,
    PriceList,
    PriceListItem,
    Product,
    SalesmanProfile,
)

logger = logging.getLogger(__name__)

DEV_SEED_PASSWORDS: dict[str, str] = {
    "salesman_a": "SalesA@2026!",
    "salesman_b": "SalesB@2026!",
    "admin": "Admin@2026!",
    "supervisor": "Prod@2026!",
    "auditor": "Audit@2026!",
    "owner": "Owner@2026!",
}


def seed_benchmark_master_data(db: Session) -> dict[str, int]:
    """Idempotently populate benchmark masters and 50 packets opening FG stock."""
    # 1. Company Profile (Tamil Nadu Factory, State Code 33)
    company = db.execute(select(CompanyProfile).limit(1)).scalar_one_or_none()
    if company is None:
        company = CompanyProfile(
            legal_name="Kaveri Traditional Snacks Pvt. Ltd.",
            gstin="33AABCK1234F1Z5",
            state_name="Tamil Nadu",
            state_code="33",
            address="Plot 14, SIDCO Industrial Estate, Tiruchirappalli, Tamil Nadu - 620015",
            variance_tolerance_pct=Decimal("3.00"),
            valuation_method="FIFO",
            is_singleton=True,
        )
        db.add(company)
        db.flush()

    # 2. Roles
    role_defs = [
        ("SALESMAN", "Field Salesman", "Mobile field order capture and own sales tracking"),
        ("FACTORY_ADMIN", "Factory Admin", "Order verification, billing, dispatch, and collections"),
        ("PRODUCTION_SUPERVISOR", "Production Supervisor", "Raw material intake, BOM runs, output & wastage"),
        ("ACCOUNTANT_AUDITOR", "Accountant / Auditor", "Read-only financial, GST, stock, and audit reports"),
        ("OWNER", "Factory Owner", "Executive KPIs, variance alerts, and governance"),
    ]
    roles_map: dict[str, Role] = {}
    for code, name, desc in role_defs:
        role = db.execute(select(Role).where(Role.code == code)).scalar_one_or_none()
        if role is None:
            role = Role(code=code, name=name, description=desc)
            db.add(role)
            db.flush()
        roles_map[code] = role

    # 3. Development Users
    user_defs = [
        ("salesman_a", "Salesman A", "+919000000001", "SALESMAN"),
        ("salesman_b", "Salesman B", "+919000000002", "SALESMAN"),
        ("admin", "Factory Admin", "+919000000003", "FACTORY_ADMIN"),
        ("supervisor", "Production Supervisor", "+919000000004", "PRODUCTION_SUPERVISOR"),
        ("auditor", "External Auditor", "+919000000005", "ACCOUNTANT_AUDITOR"),
        ("owner", "Factory Owner", "+919000000006", "OWNER"),
    ]
    users_map: dict[str, User] = {}
    for username, full_name, phone, role_code in user_defs:
        user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if user is None:
            user = User(
                role_id=roles_map[role_code].id,
                username=username,
                phone=phone,
                full_name=full_name,
                password_hash=hash_password(DEV_SEED_PASSWORDS[username]),
                is_active=True,
            )
            db.add(user)
            db.flush()
        users_map[username] = user

    # 4. Salesman Profiles
    salesman_profiles = [
        ("salesman_a", "SM-001", "Tiruchirappalli & Central TN"),
        ("salesman_b", "SM-002", "Bengaluru & Karnataka Distributors"),
    ]
    for username, emp_code, territory in salesman_profiles:
        uid = users_map[username].id
        sp = db.execute(
            select(SalesmanProfile).where(SalesmanProfile.user_id == uid)
        ).scalar_one_or_none()
        if sp is None:
            db.add(
                SalesmanProfile(
                    user_id=uid,
                    employee_code=emp_code,
                    territory=territory,
                    is_active=True,
                )
            )
            db.flush()

    # 5. Customers: Retailer A (Tamil Nadu) & Distributor B (Karnataka)
    customer_defs = [
        {
            "code": "CUST-RET-A",
            "name": "Retailer A",
            "customer_type": "RETAILER",
            "gstin": "33AAACR9999K1Z2",
            "state_name": "Tamil Nadu",
            "state_code": "33",
            "phone": "+919840011111",
            "salesman": users_map["salesman_a"].id,
            "addr_line1": "22 Big Bazaar Street",
            "city": "Tiruchirappalli",
            "pincode": "620008",
        },
        {
            "code": "CUST-DIST-B",
            "name": "Distributor B",
            "customer_type": "DISTRIBUTOR",
            "gstin": "29AAACD8888M1Z9",
            "state_name": "Karnataka",
            "state_code": "29",
            "phone": "+919845022222",
            "salesman": users_map["salesman_b"].id,
            "addr_line1": "48 APMC Market Yard, Yeshwanthpur",
            "city": "Bengaluru",
            "pincode": "560022",
        },
    ]
    for cdef in customer_defs:
        cust = db.execute(
            select(Customer).where(Customer.code == cdef["code"])
        ).scalar_one_or_none()
        if cust is None:
            cust = Customer(
                code=cdef["code"],
                name=cdef["name"],
                customer_type=cdef["customer_type"],
                gstin=cdef["gstin"],
                primary_state_name=cdef["state_name"],
                primary_state_code=cdef["state_code"],
                phone=cdef["phone"],
                assigned_salesman_id=cdef["salesman"],
                credit_days=30,
                is_active=True,
            )
            db.add(cust)
            db.flush()
            for addr_type in ("BILLING", "SHIPPING"):
                db.add(
                    CustomerAddress(
                        customer_id=cust.id,
                        address_type=addr_type,
                        line1=cdef["addr_line1"],
                        city=cdef["city"],
                        state_name=cdef["state_name"],
                        state_code=cdef["state_code"],
                        pincode=cdef["pincode"],
                        is_default=True,
                    )
                )
            db.flush()

    # 6. Product & Pack Size: Murukku 200 g (₹50.00 before tax, 5% GST)
    prod = db.execute(select(Product).where(Product.product_code == "PROD-MRK")).scalar_one_or_none()
    if prod is None:
        prod = Product(
            product_code="PROD-MRK",
            name="Murukku",
            category="Murukku",
            hsn_code="21069099",
            gst_rate_bps=500,
            is_active=True,
        )
        db.add(prod)
        db.flush()

    pack_200g = db.execute(select(PackSize).where(PackSize.sku_code == "MRK-200G")).scalar_one_or_none()
    if pack_200g is None:
        pack_200g = PackSize(
            product_id=prod.id,
            sku_code="MRK-200G",
            display_name="Murukku 200 g",
            pack_weight_g=200,
            packets_per_carton=20,
            base_selling_price_paisa=5000,
            is_active=True,
        )
        db.add(pack_200g)
        db.flush()

    # 7. Default Price List
    price_list = db.execute(
        select(PriceList).where(PriceList.is_default.is_(True), PriceList.is_active.is_(True))
    ).scalar_one_or_none()
    if price_list is None:
        price_list = PriceList(
            name="Standard Factory Price List 2026",
            is_default=True,
            customer_id=None,
            effective_from=date(2026, 4, 1),
            effective_to=None,
            is_active=True,
        )
        db.add(price_list)
        db.flush()

    pli = db.execute(
        select(PriceListItem).where(
            PriceListItem.price_list_id == price_list.id,
            PriceListItem.pack_size_id == pack_200g.id,
            PriceListItem.min_qty == 1,
        )
    ).scalar_one_or_none()
    if pli is None:
        db.add(
            PriceListItem(
                price_list_id=price_list.id,
                pack_size_id=pack_200g.id,
                unit_price_paisa=5000,
                min_qty=1,
            )
        )
        db.flush()

    # 8. Initial Finished Goods Opening Stock: 50 packets of Murukku 200 g
    inventory_service.seed_opening_finished_goods(
        db,
        batch_ref="SEED-BENCHMARK-2026",
        pack_size_id=pack_200g.id,
        opening_qty_pkts=50,
        unit_cost_paisa=2885,
        as_of_date=date(2026, 11, 1),
        created_by=users_map["admin"].id,
    )

    # 9. Unit Conversions (MASS, VOLUME, COUNT)
    uom_defs = [
        ("kg", "g", "MASS", Decimal("1000.000000")),
        ("g", "g", "MASS", Decimal("1.000000")),
        ("L", "ml", "VOLUME", Decimal("1000.000000")),
        ("ml", "ml", "VOLUME", Decimal("1.000000")),
        ("piece", "piece", "COUNT", Decimal("1.000000")),
        ("packet", "packet", "COUNT", Decimal("1.000000")),
    ]
    for from_uom, to_base_uom, dim, mult in uom_defs:
        existing_uom = db.execute(
            select(UnitConversion).where(
                UnitConversion.from_uom == from_uom,
                UnitConversion.to_base_uom == to_base_uom,
            )
        ).scalar_one_or_none()
        if existing_uom is None:
            db.add(
                UnitConversion(
                    from_uom=from_uom,
                    to_base_uom=to_base_uom,
                    unit_dimension=dim,
                    multiplier=mult,
                )
            )
            db.flush()

    # 10. Official Raw Materials, Packaging Materials & Opening Balances (NIT Trichy Section 5)
    material_defs = [
        {
            "code": "MAT-FLR",
            "name": "Flour",
            "category": "RAW_MATERIAL",
            "dim": "MASS",
            "base_uom": "g",
            "display_uom": "kg",
            "reorder_base": Decimal("50000.000"),
            "opening_qty": Decimal(100),
            "opening_uom": "kg",
            "opening_rate_paisa": 4200,
        },
        {
            "code": "MAT-OIL",
            "name": "Cooking oil",
            "category": "RAW_MATERIAL",
            "dim": "VOLUME",
            "base_uom": "ml",
            "display_uom": "L",
            "reorder_base": Decimal("15000.000"),
            "opening_qty": Decimal(30),
            "opening_uom": "L",
            "opening_rate_paisa": 14000,
        },
        {
            "code": "MAT-SPC",
            "name": "Salt and spice mix",
            "category": "RAW_MATERIAL",
            "dim": "MASS",
            "base_uom": "g",
            "display_uom": "kg",
            "reorder_base": Decimal("2000.000"),
            "opening_qty": Decimal(5),
            "opening_uom": "kg",
            "opening_rate_paisa": 20000,
        },
        {
            "code": "MAT-PCH-200",
            "name": "200 g pouch",
            "category": "PACKAGING_MATERIAL",
            "dim": "COUNT",
            "base_uom": "piece",
            "display_uom": "piece",
            "reorder_base": Decimal("200.000"),
            "opening_qty": Decimal(500),
            "opening_uom": "piece",
            "opening_rate_paisa": 250,
        },
        {
            "code": "MAT-CTN-20",
            "name": "Carton (20 pkts)",
            "category": "PACKAGING_MATERIAL",
            "dim": "COUNT",
            "base_uom": "piece",
            "display_uom": "piece",
            "reorder_base": Decimal("15.000"),
            "opening_qty": Decimal(30),
            "opening_uom": "piece",
            "opening_rate_paisa": 1500,
        },
    ]
    materials_map: dict[str, Material] = {}
    for mdef in material_defs:
        mat = db.execute(select(Material).where(Material.code == mdef["code"])).scalar_one_or_none()
        if mat is None:
            mat = Material(
                code=mdef["code"],
                name=mdef["name"],
                material_category=mdef["category"],
                unit_dimension=mdef["dim"],
                base_uom=mdef["base_uom"],
                display_uom=mdef["display_uom"],
                reorder_level_base=mdef["reorder_base"],
                is_active=True,
            )
            db.add(mat)
            db.flush()
        materials_map[mdef["code"]] = mat

        inventory_service.seed_opening_material(
            db,
            batch_ref="SEED-BENCHMARK-2026",
            material=mat,
            entered_qty=mdef["opening_qty"],
            entered_uom=mdef["opening_uom"],
            unit_rate_paisa_per_entered_uom=mdef["opening_rate_paisa"],
            as_of_date=date(2026, 11, 1),
            created_by=users_map["admin"].id,
        )

    # 11. Benchmark Supplier (Cauvery Agro Mills, Tamil Nadu)
    supplier = db.execute(select(Supplier).where(Supplier.code == "SUP-001")).scalar_one_or_none()
    if supplier is None:
        supplier = Supplier(
            code="SUP-001",
            name="Cauvery Agro Mills",
            contact_person="S. Sundaram",
            phone="+919842212345",
            email="dispatch@cauveryagro.example",
            gstin="33AAACS7777P1Z1",
            state_name="Tamil Nadu",
            state_code="33",
            address="No. 88, Gandhi Market Road, Tiruchirappalli, Tamil Nadu - 620008",
            is_active=True,
        )
        db.add(supplier)
        db.flush()

    # 12. Base Recipe Template & Active Murukku 200 g BOM v1 (NIT Trichy Section 5)
    recipe_tpl = db.execute(
        select(RecipeTemplate).where(RecipeTemplate.code == "RCP-MRK-BASE")
    ).scalar_one_or_none()
    if recipe_tpl is None:
        recipe_tpl = RecipeTemplate(
            code="RCP-MRK-BASE",
            name="Murukku Base Mix (40 kg flour batch)",
            product_id=prod.id,
            base_yield_weight_g=Decimal("40000.000"),
            notes="Standard cooked murukku dough yielding 40 kg net snack across pack sizes.",
            is_active=True,
        )
        db.add(recipe_tpl)
        db.flush()

    bom_header = db.execute(
        select(BomHeader).where(BomHeader.pack_size_id == pack_200g.id)
    ).scalar_one_or_none()
    if bom_header is None:
        bom_header = BomHeader(pack_size_id=pack_200g.id)
        db.add(bom_header)
        db.flush()

        bom_v1 = BomVersion(
            bom_header_id=bom_header.id,
            version_no=1,
            recipe_template_id=recipe_tpl.id,
            expected_yield_pkts=200,
            batch_multiplier=Decimal("1.0000"),
            status="DRAFT",
            effective_date=date(2026, 11, 1),
            notes="Official NIT Trichy Section 5 Benchmark BOM v1 for Murukku 200 g",
            created_by=users_map["admin"].id,
        )
        db.add(bom_v1)
        db.flush()

        comp_defs = [
            ("MAT-FLR", "COOKING_RAW", Decimal("40000.000"), Decimal("40.000"), "kg", 1),
            ("MAT-OIL", "COOKING_RAW", Decimal("10000.000"), Decimal("10.000"), "L", 2),
            ("MAT-SPC", "COOKING_RAW", Decimal("1200.000"), Decimal("1.200"), "kg", 3),
            ("MAT-PCH-200", "PACKAGING", Decimal("200.000"), Decimal("200.000"), "piece", 4),
            ("MAT-CTN-20", "PACKAGING", Decimal("10.000"), Decimal("10.000"), "piece", 5),
        ]
        for code, role, std_base, disp_qty, disp_uom, sort_idx in comp_defs:
            db.add(
                BomComponent(
                    bom_version_id=bom_v1.id,
                    material_id=materials_map[code].id,
                    input_role=role,
                    std_qty_base=std_base,
                    display_qty=disp_qty,
                    display_uom=disp_uom,
                    sort_order=sort_idx,
                )
            )
        db.flush()

        bom_v1.status = "ACTIVE"
        bom_v1.activated_by = users_map["admin"].id
        bom_v1.activated_at = datetime.now(UTC)
        bom_header.active_version_id = bom_v1.id
        db.flush()

    db.commit()
    return {
        "salesman_a_id": users_map["salesman_a"].id,
        "salesman_b_id": users_map["salesman_b"].id,
        "admin_id": users_map["admin"].id,
        "supervisor_id": users_map["supervisor"].id,
        "auditor_id": users_map["auditor"].id,
        "owner_id": users_map["owner"].id,
        "murukku_200g_pack_size_id": pack_200g.id,
        "murukku_200g_bom_version_id": bom_header.active_version_id or 0,
        "supplier_id": supplier.id,
        "flour_material_id": materials_map["MAT-FLR"].id,
        "oil_material_id": materials_map["MAT-OIL"].id,
        "spice_material_id": materials_map["MAT-SPC"].id,
        "pouch_material_id": materials_map["MAT-PCH-200"].id,
        "carton_material_id": materials_map["MAT-CTN-20"].id,
    }


def main() -> None:
    settings = get_settings()
    if not settings.ENABLE_DEV_SEED:
        logger.info("ENABLE_DEV_SEED is False; skipping seed.")
        return
    with SessionLocal() as db:
        result = seed_benchmark_master_data(db)
        logger.info("Benchmark seed completed successfully: %s", result)


if __name__ == "__main__":
    main()
