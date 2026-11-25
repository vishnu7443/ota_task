"""Production domain service — Catalog extensions, BOM versioning, BOM calculator, production planning,
controlled material issue, quality/output recording, atomic production posting, and variance analysis."""

from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.modules.audit.models import VarianceAlert
from app.modules.audit.service import record_audit_log
from app.modules.iam.models import CompanyProfile, User
from app.modules.iam.schemas import CurrentActor
from app.modules.inventory import repository as inventory_repo
from app.modules.inventory.models import CostLot, InventoryMovement, Material
from app.modules.inventory.uom import convert_to_base_qty, normalize_uom
from app.modules.production import repository as prod_repo
from app.modules.production.models import (
    BomComponent,
    BomHeader,
    BomVersion,
    ProductionMaterialIssue,
    ProductionOutput,
    ProductionRun,
    ProductionVariance,
    ProductionWastage,
)
from app.modules.production.schemas import (
    BomCalculateRequest,
    BomCalculationOut,
    BomComponentInput,
    BomComponentOut,
    BomHeaderOut,
    BomVersionOut,
    CancelProductionRequest,
    CompleteProductionRequest,
    CreateBomVersionRequest,
    CreateMaterialRequest,
    CreatePackSizeRequest,
    CreateProductionRunRequest,
    MaterialConsumptionInput,
    MaterialIssueOut,
    MaterialRequirementOut,
    PackSizeOut,
    ProductionCatalogOut,
    ProductionDashboardOut,
    ProductionOutputOut,
    ProductionRunOut,
    ProductionRunSummaryOut,
    ProductionVarianceReportRow,
    ProductOut,
    RecipeTemplateOut,
    ShortageItemOut,
    StartProductionRequest,
    UpdateDraftBomVersionRequest,
    VarianceAlertOut,
    VarianceOut,
    WastageOut,
)
from app.modules.sales.models import PackSize, Product

IST = ZoneInfo("Asia/Kolkata")
_OPERATOR_ROLES = {"FACTORY_ADMIN", "PRODUCTION_SUPERVISOR"}
_VIEWER_ROLES = {"FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "OWNER", "ACCOUNTANT_AUDITOR"}


def _require_operator(actor: CurrentActor, action: str) -> None:
    if actor.role_code not in _OPERATOR_ROLES:
        raise AuthorizationError(f"Only Factory Admin or Production Supervisor can {action}.")


def _require_viewer(actor: CurrentActor, action: str) -> None:
    if actor.role_code not in _VIEWER_ROLES:
        raise AuthorizationError(f"Your role is not permitted to {action}.")


def _get_company(db: Session) -> CompanyProfile:
    cp = db.execute(select(CompanyProfile).limit(1)).scalar_one_or_none()
    if cp is None:
        raise DomainValidationError("Company profile is not configured.")
    return cp


def _get_materials_map(db: Session, ids: list[int]) -> dict[int, Material]:
    unique = list(set(ids))
    if not unique:
        return {}
    rows = db.execute(select(Material).where(Material.id.in_(unique))).scalars().all()
    return {m.id: m for m in rows}


def _get_users_map(db: Session, ids: set[int]) -> dict[int, User]:
    clean = {i for i in ids if i is not None}
    if not clean:
        return {}
    rows = db.execute(select(User).where(User.id.in_(clean))).scalars().all()
    return {u.id: u for u in rows}


def _get_pack_size(db: Session, pack_size_id: int) -> PackSize:
    ps = db.execute(select(PackSize).where(PackSize.id == pack_size_id)).scalar_one_or_none()
    if ps is None or not ps.is_active:
        raise NotFoundError(f"Active pack size {pack_size_id} was not found.")
    return ps


def _display_factor(display_uom: str, base_uom: str) -> Decimal:
    if display_uom == "kg" and base_uom == "g":
        return Decimal(1000)
    if display_uom == "L" and base_uom == "ml":
        return Decimal(1000)
    return Decimal(1)


# ── Catalog & Extensible Pack Sizes / Materials ─────────────────────────────


def get_production_catalog(db: Session, actor: CurrentActor) -> ProductionCatalogOut:
    _require_viewer(actor, "view production catalog")
    products = prod_repo.list_products(db, active_only=True)
    pack_sizes = prod_repo.list_pack_sizes(db, active_only=True)
    templates = prod_repo.list_recipe_templates(db)
    headers = prod_repo.list_all_bom_headers(db)

    prod_map = {p.id: p for p in products}
    header_by_ps = {h.pack_size_id: h for h in headers}
    active_ver_ids = [h.active_version_id for h in headers if h.active_version_id is not None]
    ver_map: dict[int, BomVersion] = {}
    if active_ver_ids:
        for bv in db.execute(select(BomVersion).where(BomVersion.id.in_(active_ver_ids))).scalars().all():
            ver_map[bv.id] = bv

    return ProductionCatalogOut(
        products=[
            ProductOut(
                id=p.id,
                product_code=p.product_code,
                name=p.name,
                category=p.category,
                hsn_code=p.hsn_code,
                gst_rate_bps=p.gst_rate_bps,
                is_active=p.is_active,
            )
            for p in products
        ],
        pack_sizes=[
            PackSizeOut(
                id=ps.id,
                product_id=ps.product_id,
                product_code=prod_map[ps.product_id].product_code,
                product_name=prod_map[ps.product_id].name,
                sku_code=ps.sku_code,
                display_name=ps.display_name,
                pack_weight_g=ps.pack_weight_g,
                packets_per_carton=ps.packets_per_carton,
                base_selling_price_paisa=ps.base_selling_price_paisa,
                is_active=ps.is_active,
                has_active_bom=(
                    ps.id in header_by_ps and header_by_ps[ps.id].active_version_id is not None
                ),
                active_bom_version_no=(
                    ver_map[header_by_ps[ps.id].active_version_id].version_no
                    if ps.id in header_by_ps and header_by_ps[ps.id].active_version_id in ver_map
                    else None
                ),
            )
            for ps in pack_sizes
            if ps.product_id in prod_map
        ],
        recipe_templates=[
            RecipeTemplateOut(
                id=t.id,
                code=t.code,
                name=t.name,
                product_id=t.product_id,
                base_yield_weight_g=Decimal(t.base_yield_weight_g),
                notes=t.notes,
                is_active=t.is_active,
            )
            for t in templates
        ],
    )


def create_pack_size(
    db: Session, actor: CurrentActor, payload: CreatePackSizeRequest
) -> PackSizeOut:
    """Add a new pack size variant (e.g. Murukku 500 g) sharing an existing Product family."""
    _require_operator(actor, "add product pack sizes")
    prod = prod_repo.get_product(db, payload.product_id)
    if prod is None or not prod.is_active:
        raise NotFoundError(f"Active product {payload.product_id} was not found.")

    dup_sku = db.execute(select(PackSize).where(PackSize.sku_code == payload.sku_code)).scalar_one_or_none()
    if dup_sku is not None:
        raise ConflictError(f"SKU code '{payload.sku_code}' already exists.", error_code="DUPLICATE_SKU_CODE")

    dup_weight = db.execute(
        select(PackSize).where(
            PackSize.product_id == prod.id, PackSize.pack_weight_g == payload.pack_weight_g
        )
    ).scalar_one_or_none()
    if dup_weight is not None:
        raise ConflictError(
            f"Product '{prod.name}' already defines a {payload.pack_weight_g} g pack size.",
            error_code="DUPLICATE_PACK_WEIGHT",
        )

    ps = PackSize(
        product_id=prod.id,
        sku_code=payload.sku_code,
        display_name=payload.display_name.strip(),
        pack_weight_g=payload.pack_weight_g,
        packets_per_carton=payload.packets_per_carton,
        base_selling_price_paisa=payload.base_selling_price_paisa,
        is_active=True,
    )
    db.add(ps)
    db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="PACK_SIZE_CREATED",
        entity_schema="sales",
        entity_table="pack_sizes",
        entity_id=ps.id,
        after_state={
            "sku_code": ps.sku_code,
            "product_id": prod.id,
            "pack_weight_g": ps.pack_weight_g,
            "packets_per_carton": ps.packets_per_carton,
        },
        reason=f"Added pack size {ps.display_name}",
    )
    db.commit()

    return PackSizeOut(
        id=ps.id,
        product_id=prod.id,
        product_code=prod.product_code,
        product_name=prod.name,
        sku_code=ps.sku_code,
        display_name=ps.display_name,
        pack_weight_g=ps.pack_weight_g,
        packets_per_carton=ps.packets_per_carton,
        base_selling_price_paisa=ps.base_selling_price_paisa,
        is_active=ps.is_active,
        has_active_bom=False,
        active_bom_version_no=None,
    )


def create_material(
    db: Session, actor: CurrentActor, payload: CreateMaterialRequest
) -> dict:
    """Create a new Raw or Packaging Material (e.g. 500 g pouch) validated cleanly on dimension."""
    _require_operator(actor, "create materials")
    dup = db.execute(select(Material).where(Material.code == payload.code)).scalar_one_or_none()
    if dup is not None:
        raise ConflictError(f"Material code '{payload.code}' already exists.", error_code="DUPLICATE_MATERIAL_CODE")

    base_map = {"MASS": "g", "VOLUME": "ml", "COUNT": "piece"}
    base_uom = base_map[payload.unit_dimension]
    reorder_base, _mult, norm_disp_uom = convert_to_base_qty(
        db,
        entered_qty=payload.reorder_level_display,
        entered_uom=payload.display_uom,
        expected_dimension=payload.unit_dimension,
        expected_base_uom=base_uom,
    )

    mat = Material(
        code=payload.code,
        name=payload.name.strip(),
        material_category=payload.material_category,
        unit_dimension=payload.unit_dimension,
        base_uom=base_uom,
        display_uom=norm_disp_uom,
        reorder_level_base=reorder_base,
        is_active=True,
    )
    db.add(mat)
    db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="MATERIAL_CREATED",
        entity_schema="production",
        entity_table="materials",
        entity_id=mat.id,
        after_state={"code": mat.code, "name": mat.name, "unit_dimension": mat.unit_dimension},
    )
    db.commit()
    return {
        "id": mat.id,
        "code": mat.code,
        "name": mat.name,
        "material_category": mat.material_category,
        "unit_dimension": mat.unit_dimension,
        "base_uom": mat.base_uom,
        "display_uom": mat.display_uom,
        "reorder_level_base": str(mat.reorder_level_base),
        "is_active": mat.is_active,
    }


# ── BOM Management & Versioning ─────────────────────────────────────────────


def _hydrate_component(comp: BomComponent, mat: Material) -> BomComponentOut:
    return BomComponentOut(
        id=comp.id,
        material_id=comp.material_id,
        material_code=mat.code,
        material_name=mat.name,
        material_category=mat.material_category,
        unit_dimension=mat.unit_dimension,
        input_role=comp.input_role,
        std_qty_base=Decimal(comp.std_qty_base),
        display_qty=Decimal(comp.display_qty),
        display_uom=comp.display_uom,
        base_uom=mat.base_uom,
        sort_order=comp.sort_order,
    )


def _hydrate_version(
    ver: BomVersion,
    mats: dict[int, Material],
    users: dict[int, User],
    run_counts: dict[int, int],
    templates: dict[int, str],
) -> BomVersionOut:
    rc = run_counts.get(ver.id, 0)
    return BomVersionOut(
        id=ver.id,
        bom_header_id=ver.bom_header_id,
        version_no=ver.version_no,
        recipe_template_id=ver.recipe_template_id,
        recipe_template_name=templates.get(ver.recipe_template_id) if ver.recipe_template_id else None,
        expected_yield_pkts=ver.expected_yield_pkts,
        batch_multiplier=Decimal(ver.batch_multiplier),
        status=ver.status,
        effective_date=ver.effective_date,
        notes=ver.notes,
        created_by_name=users[ver.created_by].full_name if ver.created_by in users else "System",
        activated_by_name=(
            users[ver.activated_by].full_name
            if ver.activated_by and ver.activated_by in users
            else None
        ),
        activated_at=ver.activated_at,
        created_at=ver.created_at,
        run_count=rc,
        is_locked=(ver.status != "DRAFT" or rc > 0),
        components=[
            _hydrate_component(c, mats[c.material_id])
            for c in sorted(ver.components, key=lambda x: (x.sort_order, x.id))
        ],
    )


def _hydrate_bom_header(
    db: Session, ps: PackSize, prod: Product, header: BomHeader | None
) -> BomHeaderOut:
    if header is None:
        return BomHeaderOut(
            id=0,
            pack_size_id=ps.id,
            sku_code=ps.sku_code,
            display_name=ps.display_name,
            product_id=prod.id,
            product_name=prod.name,
            pack_weight_g=ps.pack_weight_g,
            packets_per_carton=ps.packets_per_carton,
            active_version_id=None,
            active_version=None,
            all_versions=[],
        )

    versions = prod_repo.list_bom_versions_for_header(db, header.id)
    mat_ids = [c.material_id for v in versions for c in v.components]
    mats = _get_materials_map(db, mat_ids)
    user_ids = {v.created_by for v in versions} | {
        v.activated_by for v in versions if v.activated_by is not None
    }
    users = _get_users_map(db, user_ids)
    run_counts = prod_repo.count_runs_by_bom_version_ids(db, [v.id for v in versions])
    tpl_map = {t.id: t.name for t in prod_repo.list_recipe_templates(db)}

    v_outs = [_hydrate_version(v, mats, users, run_counts, tpl_map) for v in versions]
    active_v = next((v for v in v_outs if v.id == header.active_version_id), None)

    return BomHeaderOut(
        id=header.id,
        pack_size_id=ps.id,
        sku_code=ps.sku_code,
        display_name=ps.display_name,
        product_id=prod.id,
        product_name=prod.name,
        pack_weight_g=ps.pack_weight_g,
        packets_per_carton=ps.packets_per_carton,
        active_version_id=header.active_version_id,
        active_version=active_v,
        all_versions=v_outs,
    )


def list_bom_headers(db: Session, actor: CurrentActor) -> list[BomHeaderOut]:
    _require_viewer(actor, "view BOM masters")
    pack_sizes = prod_repo.list_pack_sizes(db, active_only=True)
    products = {p.id: p for p in prod_repo.list_products(db, active_only=False)}
    headers_by_ps = {h.pack_size_id: h for h in prod_repo.list_all_bom_headers(db)}
    return [
        _hydrate_bom_header(db, ps, products[ps.product_id], headers_by_ps.get(ps.id))
        for ps in pack_sizes
        if ps.product_id in products
    ]


def get_bom_for_pack_size(db: Session, actor: CurrentActor, pack_size_id: int) -> BomHeaderOut:
    _require_viewer(actor, "view BOM details")
    ps = _get_pack_size(db, pack_size_id)
    prod = db.execute(select(Product).where(Product.id == ps.product_id)).scalar_one()
    header = prod_repo.get_bom_header_by_pack_size(db, pack_size_id)
    return _hydrate_bom_header(db, ps, prod, header)


def _validate_and_convert_bom_components(
    db: Session, components: list[BomComponentInput]
) -> tuple[list[dict], dict[int, Material]]:
    mat_ids = [c.material_id for c in components]
    if len(mat_ids) != len(set(mat_ids)):
        raise DomainValidationError("Duplicate material entries in the same BOM version are not allowed.")

    mats = _get_materials_map(db, mat_ids)
    if len(mats) != len(mat_ids):
        missing = set(mat_ids) - set(mats.keys())
        raise NotFoundError(f"Material IDs not found: {sorted(missing)}")

    converted: list[dict] = []
    for idx, ci in enumerate(components):
        mat = mats[ci.material_id]
        if not mat.is_active:
            raise DomainValidationError(f"Material '{mat.name}' is inactive and cannot be added to a BOM.")
        if ci.input_role == "COOKING_RAW" and mat.material_category != "RAW_MATERIAL":
            raise DomainValidationError(
                f"Material '{mat.name}' has category {mat.material_category} and cannot have role COOKING_RAW."
            )
        if ci.input_role == "PACKAGING" and mat.material_category != "PACKAGING_MATERIAL":
            raise DomainValidationError(
                f"Material '{mat.name}' has category {mat.material_category} and cannot have role PACKAGING."
            )
        base_qty, _mult, norm_uom = convert_to_base_qty(
            db,
            entered_qty=ci.display_qty,
            entered_uom=ci.display_uom,
            expected_dimension=mat.unit_dimension,
            expected_base_uom=mat.base_uom,
        )
        converted.append(
            {
                "material_id": ci.material_id,
                "input_role": ci.input_role,
                "std_qty_base": base_qty,
                "display_qty": ci.display_qty.quantize(Decimal("0.001")),
                "display_uom": norm_uom,
                "sort_order": idx + 1,
            }
        )
    return converted, mats


def _do_activate_bom_version(
    db: Session, header: BomHeader, version: BomVersion, actor: CurrentActor
) -> None:
    now_utc = datetime.now(UTC)
    if header.active_version_id is not None and header.active_version_id != version.id:
        old = prod_repo.get_bom_version(db, header.active_version_id, for_update=True)
        if old and old.status == "ACTIVE":
            old.status = "SUPERSEDED"
            db.flush()

    version.status = "ACTIVE"
    version.activated_by = actor.user_id
    version.activated_at = now_utc
    header.active_version_id = version.id
    db.flush()


def create_bom_version(
    db: Session, actor: CurrentActor, payload: CreateBomVersionRequest
) -> BomVersionOut:
    _require_operator(actor, "create BOM versions")
    ps = _get_pack_size(db, payload.pack_size_id)

    if payload.recipe_template_id is not None:
        tpl = prod_repo.get_recipe_template(db, payload.recipe_template_id)
        if tpl is None or not tpl.is_active:
            raise NotFoundError(f"Active recipe template {payload.recipe_template_id} was not found.")

    converted_lines, _mats = _validate_and_convert_bom_components(db, payload.components)

    header = prod_repo.get_bom_header_by_pack_size(db, ps.id, for_update=True)
    if header is None:
        header = BomHeader(pack_size_id=ps.id)
        db.add(header)
        db.flush()

    version_no = prod_repo.get_next_version_no(db, header.id)
    version = BomVersion(
        bom_header_id=header.id,
        version_no=version_no,
        recipe_template_id=payload.recipe_template_id,
        expected_yield_pkts=payload.expected_yield_pkts,
        batch_multiplier=Decimal("1.0000"),
        status="DRAFT",
        effective_date=payload.effective_date or datetime.now(IST).date(),
        notes=payload.notes.strip() if payload.notes else None,
        created_by=actor.user_id,
    )
    db.add(version)
    db.flush()

    for cl in converted_lines:
        db.add(BomComponent(bom_version_id=version.id, **cl))
    db.flush()

    if payload.activate:
        _do_activate_bom_version(db, header, version, actor)

    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="BOM_VERSION_CREATED",
        entity_schema="production",
        entity_table="bom_versions",
        entity_id=version.id,
        after_state={
            "pack_size_id": ps.id,
            "sku_code": ps.sku_code,
            "version_no": version_no,
            "status": version.status,
            "expected_yield_pkts": payload.expected_yield_pkts,
        },
        reason=payload.notes or f"Created BOM v{version_no} for {ps.sku_code}",
    )
    db.commit()

    refreshed = prod_repo.get_bom_version(db, version.id)
    assert refreshed is not None
    mats = _get_materials_map(db, [c.material_id for c in refreshed.components])
    users = _get_users_map(
        db, {refreshed.created_by, refreshed.activated_by} if refreshed.activated_by else {refreshed.created_by}
    )
    tpl_map = {t.id: t.name for t in prod_repo.list_recipe_templates(db)}
    return _hydrate_version(refreshed, mats, users, {}, tpl_map)


def update_draft_bom_version(
    db: Session, actor: CurrentActor, version_id: int, payload: UpdateDraftBomVersionRequest
) -> BomVersionOut:
    """Update components/yield ONLY while BOM version is in DRAFT. Non-DRAFT versions are immutable."""
    _require_operator(actor, "edit draft BOM versions")
    version = prod_repo.get_bom_version(db, version_id, for_update=True)
    if version is None:
        raise NotFoundError(f"BOM version {version_id} was not found.")
    if version.status != "DRAFT":
        raise ConflictError(
            f"BOM version v{version.version_no} is '{version.status}' and immutable. Create a new BOM version to make recipe changes.",
            error_code="IMMUTABLE_BOM_VERSION",
        )

    converted_lines, _mats = _validate_and_convert_bom_components(db, payload.components)
    before = {"expected_yield_pkts": version.expected_yield_pkts, "notes": version.notes}

    version.expected_yield_pkts = payload.expected_yield_pkts
    if payload.effective_date is not None:
        version.effective_date = payload.effective_date
    version.notes = payload.notes.strip() if payload.notes else None
    prod_repo.delete_components_for_version(db, version.id)
    for cl in converted_lines:
        db.add(BomComponent(bom_version_id=version.id, **cl))
    db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="BOM_DRAFT_UPDATED",
        entity_schema="production",
        entity_table="bom_versions",
        entity_id=version.id,
        before_state=before,
        after_state={"expected_yield_pkts": version.expected_yield_pkts, "notes": version.notes},
    )
    db.commit()

    refreshed = prod_repo.get_bom_version(db, version.id)
    assert refreshed is not None
    mats = _get_materials_map(db, [c.material_id for c in refreshed.components])
    users = _get_users_map(db, {refreshed.created_by})
    tpl_map = {t.id: t.name for t in prod_repo.list_recipe_templates(db)}
    return _hydrate_version(refreshed, mats, users, {}, tpl_map)


def activate_bom_version(
    db: Session, actor: CurrentActor, version_id: int
) -> BomVersionOut:
    _require_operator(actor, "activate BOM versions")
    version = prod_repo.get_bom_version(db, version_id, for_update=True)
    if version is None:
        raise NotFoundError(f"BOM version {version_id} was not found.")
    if version.status == "ACTIVE":
        raise ConflictError("This BOM version is already active.", error_code="ALREADY_ACTIVE")
    if not version.components:
        raise DomainValidationError("Cannot activate an empty BOM version without components.")

    header = prod_repo.get_bom_header(db, version.bom_header_id, for_update=True)
    assert header is not None
    prev_status = version.status
    _do_activate_bom_version(db, header, version, actor)

    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="BOM_VERSION_ACTIVATED",
        entity_schema="production",
        entity_table="bom_versions",
        entity_id=version.id,
        before_state={"status": prev_status},
        after_state={"version_no": version.version_no, "status": "ACTIVE"},
        reason=f"Activated BOM v{version.version_no}",
    )
    db.commit()

    refreshed = prod_repo.get_bom_version(db, version.id)
    assert refreshed is not None
    mats = _get_materials_map(db, [c.material_id for c in refreshed.components])
    users = _get_users_map(
        db, {refreshed.created_by, refreshed.activated_by} if refreshed.activated_by else {refreshed.created_by}
    )
    run_counts = prod_repo.count_runs_by_bom_version_ids(db, [refreshed.id])
    tpl_map = {t.id: t.name for t in prod_repo.list_recipe_templates(db)}
    return _hydrate_version(refreshed, mats, users, run_counts, tpl_map)


def delete_bom_version(db: Session, actor: CurrentActor, version_id: int) -> None:
    """Allow deleting ONLY unactivated DRAFT BOM versions; block ACTIVE/SUPERSEDED mutations."""
    _require_operator(actor, "delete BOM versions")
    version = prod_repo.get_bom_version(db, version_id, for_update=True)
    if version is None:
        raise NotFoundError(f"BOM version {version_id} was not found.")
    if version.status != "DRAFT":
        raise ConflictError(
            f"BOM version v{version.version_no} is '{version.status}' and immutable; historical versions cannot be deleted.",
            error_code="IMMUTABLE_BOM_VERSION",
        )
    prod_repo.delete_components_for_version(db, version.id)
    db.delete(version)
    db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="BOM_DRAFT_DELETED",
        entity_schema="production",
        entity_table="bom_versions",
        entity_id=version_id,
        before_state={"version_no": version.version_no, "status": "DRAFT"},
    )
    db.commit()


# ── BOM Calculation Engine ──────────────────────────────────────────────────


def _resolve_scale_and_bom(
    db: Session,
    *,
    pack_size_id: int,
    batch_multiplier: Decimal | None,
    target_output_pkts: int | None,
    bom_version_id: int | None = None,
) -> tuple[PackSize, BomVersion, Decimal, int]:
    ps = _get_pack_size(db, pack_size_id)
    if bom_version_id is not None:
        version = prod_repo.get_bom_version(db, bom_version_id)
        if version is None:
            raise NotFoundError(f"BOM version {bom_version_id} was not found.")
        header = prod_repo.get_bom_header(db, version.bom_header_id)
        if header is None or header.pack_size_id != ps.id:
            raise DomainValidationError("Selected BOM version does not belong to the chosen pack size.")
    else:
        version = prod_repo.get_active_bom_version_for_pack_size(db, ps.id)
        if version is None:
            raise NotFoundError(f"No active BOM version exists for {ps.sku_code}. Activate a BOM first.")

    if target_output_pkts is not None:
        eff_mult = (Decimal(target_output_pkts) / Decimal(version.expected_yield_pkts)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        if eff_mult <= 0:
            raise DomainValidationError("Calculated batch multiplier must be greater than zero.")
        expected_pkts = target_output_pkts
    else:
        assert batch_multiplier is not None
        eff_mult = Decimal(batch_multiplier).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        expected_pkts = int(
            (Decimal(version.expected_yield_pkts) * eff_mult).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        )

    return ps, version, eff_mult, expected_pkts


def calculate_bom_requirements(
    db: Session, actor: CurrentActor, payload: BomCalculateRequest
) -> BomCalculationOut:
    """Scale BOM ingredients cleanly using Decimal math and ceiling rounding for indivisible COUNT units."""
    _require_viewer(actor, "calculate BOM material requirements")
    ps, version, eff_mult, expected_pkts = _resolve_scale_and_bom(
        db,
        pack_size_id=payload.pack_size_id,
        batch_multiplier=payload.batch_multiplier,
        target_output_pkts=payload.target_output_pkts,
        bom_version_id=payload.bom_version_id,
    )

    mat_ids = [c.material_id for c in version.components]
    mats = _get_materials_map(db, mat_ids)
    balances = inventory_repo.get_balances_by_material_ids(db, mat_ids)

    requirements: list[MaterialRequirementOut] = []
    has_shortages = False
    shortage_parts: list[str] = []

    for comp in sorted(version.components, key=lambda x: (x.sort_order, x.id)):
        mat = mats[comp.material_id]
        exact_scaled = (Decimal(comp.std_qty_base) * eff_mult).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )
        was_rounded_up = False
        rounding_note: str | None = None

        if mat.unit_dimension == "COUNT":
            unrounded = Decimal(comp.std_qty_base) * eff_mult
            std_qty_base = unrounded.to_integral_value(rounding=ROUND_CEILING).quantize(Decimal("0.001"))
            if std_qty_base != unrounded.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP):
                was_rounded_up = True
                rounding_note = (
                    f"Indivisible packaging unit rounded up from {unrounded:.3f} to {int(std_qty_base)} {mat.base_uom}"
                )
        else:
            std_qty_base = exact_scaled

        factor = _display_factor(mat.display_uom, mat.base_uom)
        disp_qty = (std_qty_base / factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

        bal = balances.get(mat.id)
        on_hand = Decimal(bal.on_hand_qty_base).quantize(Decimal("0.001")) if bal else Decimal("0.000")
        reserved = Decimal(bal.reserved_qty_base).quantize(Decimal("0.001")) if bal else Decimal("0.000")
        avail = max(Decimal("0.000"), (on_hand - reserved).quantize(Decimal("0.001")))
        additional = max(Decimal("0.000"), (std_qty_base - avail).quantize(Decimal("0.001")))
        is_short = additional > 0

        if is_short:
            has_shortages = True
            shortage_parts.append(
                f"{mat.name}: need {(std_qty_base / factor):.3f} {mat.display_uom}, available {(avail / factor):.3f} {mat.display_uom} (short {(additional / factor):.3f})"
            )

        requirements.append(
            MaterialRequirementOut(
                material_id=mat.id,
                material_code=mat.code,
                material_name=mat.name,
                material_category=mat.material_category,
                unit_dimension=mat.unit_dimension,
                input_role=comp.input_role,
                bom_std_qty_base=Decimal(comp.std_qty_base),
                exact_scaled_qty_base=exact_scaled,
                standard_qty_base=std_qty_base,
                was_rounded_up=was_rounded_up,
                rounding_note=rounding_note,
                display_qty=disp_qty,
                display_uom=comp.display_uom,
                base_uom=mat.base_uom,
                display_factor=factor,
                on_hand_qty_base=on_hand,
                reserved_qty_base=reserved,
                available_qty_base=avail,
                additional_required_base=additional,
                is_shortage=is_short,
            )
        )

    return BomCalculationOut(
        pack_size_id=ps.id,
        sku_code=ps.sku_code,
        display_name=ps.display_name,
        bom_version_id=version.id,
        version_no=version.version_no,
        batch_multiplier=eff_mult,
        expected_output_pkts=expected_pkts,
        requirements=requirements,
        has_shortages=has_shortages,
        shortage_summary="; ".join(shortage_parts) if shortage_parts else "All required materials in stock",
    )


# ── Production Run Hydration ────────────────────────────────────────────────


def _hydrate_alert(
    alert: VarianceAlert,
    runs_map: dict[int, ProductionRun],
    ps_map: dict[int, PackSize],
    users: dict[int, User],
) -> VarianceAlertOut:
    run = runs_map[alert.production_run_id]
    ps = ps_map[run.pack_size_id]
    return VarianceAlertOut(
        id=alert.id,
        production_run_id=alert.production_run_id,
        run_number=run.run_number,
        sku_code=ps.sku_code,
        production_variance_id=alert.production_variance_id,
        alert_type=alert.alert_type,
        message=alert.message,
        status=alert.status,
        acknowledged_by_name=(
            users[alert.acknowledged_by].full_name
            if alert.acknowledged_by and alert.acknowledged_by in users
            else None
        ),
        acknowledged_at=alert.acknowledged_at,
        acknowledgement_note=alert.acknowledgement_note,
        created_at=alert.created_at,
    )


def _hydrate_run(db: Session, run: ProductionRun) -> ProductionRunOut:
    ps = db.execute(select(PackSize).where(PackSize.id == run.pack_size_id)).scalar_one()
    version = prod_repo.get_bom_version(db, run.bom_version_id)
    assert version is not None

    mat_ids = [mi.material_id for mi in run.material_issues]
    mat_ids += [w.material_id for w in run.wastages if w.material_id is not None]
    mat_ids += [v.material_id for v in run.variances if v.material_id is not None]
    mats = _get_materials_map(db, mat_ids)
    balances = inventory_repo.get_balances_by_material_ids(db, [mi.material_id for mi in run.material_issues])
    alerts = prod_repo.list_alerts(db, run_id=run.id)

    user_ids: set[int] = {run.supervisor_id}
    if run.posted_by:
        user_ids.add(run.posted_by)
    for mi in run.material_issues:
        if mi.issued_by:
            user_ids.add(mi.issued_by)
    for o in run.outputs:
        user_ids.add(o.recorded_by)
    for w in run.wastages:
        user_ids.add(w.recorded_by)
    for al in alerts:
        if al.acknowledged_by:
            user_ids.add(al.acknowledged_by)
    users = _get_users_map(db, user_ids)

    mi_outs: list[MaterialIssueOut] = []
    for mi in run.material_issues:
        mat = mats[mi.material_id]
        bal = balances.get(mi.material_id)
        avail = (
            max(Decimal("0.000"), Decimal(bal.on_hand_qty_base) - Decimal(bal.reserved_qty_base))
            if bal
            else Decimal("0.000")
        )
        mi_outs.append(
            MaterialIssueOut(
                id=mi.id,
                material_id=mi.material_id,
                material_code=mat.code,
                material_name=mat.name,
                material_category=mat.material_category,
                issue_phase=mi.issue_phase,
                planned_qty_base=Decimal(mi.planned_qty_base),
                issued_qty_base=Decimal(mi.issued_qty_base),
                actual_consumed_qty_base=Decimal(mi.actual_consumed_qty_base),
                actual_good_used_base=Decimal(mi.actual_good_used_base),
                damaged_qty_base=Decimal(mi.damaged_qty_base),
                returned_unused_qty_base=Decimal(mi.returned_unused_qty_base),
                wasted_qty_base=Decimal(mi.wasted_qty_base),
                cost_absorbed_paisa=int(mi.cost_absorbed_paisa),
                display_uom=mat.display_uom,
                base_uom=mat.base_uom,
                display_factor=_display_factor(mat.display_uom, mat.base_uom),
                available_qty_base=avail.quantize(Decimal("0.001")),
                issued_by_name=users[mi.issued_by].full_name if mi.issued_by in users else None,
                issued_at=mi.issued_at,
            )
        )

    out_outs = [
        ProductionOutputOut(
            id=o.id,
            good_qty_pkts=o.good_qty_pkts,
            rejected_qty_pkts=o.rejected_qty_pkts,
            total_qty_pkts=o.good_qty_pkts + o.rejected_qty_pkts,
            batch_code=o.batch_code,
            expiry_date=o.expiry_date,
            quality_remarks=o.quality_remarks,
            recorded_by_name=users[o.recorded_by].full_name if o.recorded_by in users else "Unknown",
            recorded_at=o.recorded_at,
        )
        for o in run.outputs
    ]

    w_outs: list[WastageOut] = []
    for w in run.wastages:
        mat = mats.get(w.material_id) if w.material_id else None
        w_outs.append(
            WastageOut(
                id=w.id,
                material_id=w.material_id,
                material_code=mat.code if mat else None,
                material_name=mat.name if mat else None,
                pack_size_id=w.pack_size_id,
                wastage_type=w.wastage_type,
                qty_base=Decimal(w.qty_base),
                uom=w.uom,
                cost_impact_paisa=int(w.cost_impact_paisa),
                reason=w.reason,
                recorded_by_name=users[w.recorded_by].full_name if w.recorded_by in users else "Unknown",
                recorded_at=w.recorded_at,
            )
        )

    v_outs: list[VarianceOut] = []
    for v in run.variances:
        mat = mats.get(v.material_id) if v.material_id else None
        disp_uom = mat.display_uom if mat else "packet"
        base_uom = mat.base_uom if mat else "packet"
        v_outs.append(
            VarianceOut(
                id=v.id,
                variance_scope=v.variance_scope,
                material_id=v.material_id,
                material_code=mat.code if mat else None,
                material_name=mat.name if mat else None,
                planned_qty_base=Decimal(v.planned_qty_base),
                actual_qty_base=Decimal(v.actual_qty_base),
                variance_qty_base=Decimal(v.variance_qty_base),
                variance_pct=Decimal(v.variance_pct) if v.variance_pct is not None else None,
                tolerance_pct=Decimal(v.tolerance_pct),
                is_flagged=v.is_flagged,
                formula_explanation=v.formula_explanation,
                display_uom=disp_uom,
                base_uom=base_uom,
                display_factor=_display_factor(disp_uom, base_uom),
                computed_at=v.computed_at,
            )
        )

    alert_outs = [_hydrate_alert(al, {run.id: run}, {ps.id: ps}, users) for al in alerts]

    return ProductionRunOut(
        id=run.id,
        run_number=run.run_number,
        pack_size_id=run.pack_size_id,
        sku_code=ps.sku_code,
        display_name=ps.display_name,
        packets_per_carton=ps.packets_per_carton,
        bom_version_id=run.bom_version_id,
        version_no=version.version_no,
        bom_status=version.status,
        bom_expected_yield_pkts=version.expected_yield_pkts,
        batch_multiplier=Decimal(run.batch_multiplier),
        expected_output_pkts=run.expected_output_pkts,
        actual_good_output_pkts=run.actual_good_output_pkts,
        rejected_output_pkts=run.rejected_output_pkts,
        status=run.status,
        run_date=run.run_date,
        planned_at=run.planned_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        posted_at=run.posted_at,
        cancelled_at=run.cancelled_at,
        supervisor_name=users[run.supervisor_id].full_name if run.supervisor_id in users else "Unknown",
        posted_by_name=users[run.posted_by].full_name if run.posted_by and run.posted_by in users else None,
        quality_remarks=run.quality_remarks,
        notes=run.notes,
        total_material_cost_paisa=sum(int(mi.cost_absorbed_paisa) for mi in run.material_issues),
        material_issues=mi_outs,
        outputs=out_outs,
        wastages=w_outs,
        variances=v_outs,
        alerts=alert_outs,
    )


# ── Production Lifecycle Operations ─────────────────────────────────────────


def create_production_run(
    db: Session, actor: CurrentActor, payload: CreateProductionRunRequest
) -> ProductionRunOut:
    """Create a Production Run in DRAFT (or directly PLANNED), pinning active BOM version."""
    _require_operator(actor, "create production runs")
    ps, version, eff_mult, expected_pkts = _resolve_scale_and_bom(
        db,
        pack_size_id=payload.pack_size_id,
        batch_multiplier=payload.batch_multiplier,
        target_output_pkts=payload.target_output_pkts,
    )

    run_date = payload.run_date or datetime.now(IST).date()
    now_utc = datetime.now(UTC)
    initial_status = "PLANNED" if payload.plan_immediately else "DRAFT"

    mat_ids = [c.material_id for c in version.components]
    mats = _get_materials_map(db, mat_ids)

    try:
        run = ProductionRun(
            run_number=f"TMP-PRD-{uuid4().hex[:8]}",
            pack_size_id=ps.id,
            bom_version_id=version.id,
            batch_multiplier=eff_mult,
            expected_output_pkts=expected_pkts,
            status=initial_status,
            run_date=run_date,
            planned_at=now_utc if payload.plan_immediately else None,
            supervisor_id=actor.user_id,
            notes=payload.notes.strip() if payload.notes else None,
        )
        db.add(run)
        db.flush()
        run.run_number = f"PRD-{run_date.year}-{run.id:04d}"

        for comp in sorted(version.components, key=lambda x: (x.sort_order, x.id)):
            mat = mats[comp.material_id]
            raw_scaled = Decimal(comp.std_qty_base) * eff_mult
            if mat.unit_dimension == "COUNT":
                planned_qty = raw_scaled.to_integral_value(rounding=ROUND_CEILING).quantize(Decimal("0.001"))
            else:
                planned_qty = raw_scaled.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

            phase = "RAW_ISSUE" if comp.input_role == "COOKING_RAW" else "PACKAGING_PACK"
            db.add(
                ProductionMaterialIssue(
                    production_run_id=run.id,
                    material_id=comp.material_id,
                    issue_phase=phase,
                    planned_qty_base=planned_qty,
                )
            )
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PRODUCTION_RUN_CREATED",
            entity_schema="production",
            entity_table="production_runs",
            entity_id=run.id,
            after_state={
                "run_number": run.run_number,
                "status": run.status,
                "bom_version_id": version.id,
                "bom_version_no": version.version_no,
                "expected_output_pkts": expected_pkts,
            },
            reason=f"Created {run.run_number} ({initial_status}) pinned to BOM v{version.version_no}",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = prod_repo.get_production_run(db, run.id)
    assert refreshed is not None
    return _hydrate_run(db, refreshed)


def plan_production_run(
    db: Session, actor: CurrentActor, run_id: int
) -> ProductionRunOut:
    """Transition DRAFT -> PLANNED without touching stock."""
    _require_operator(actor, "plan production runs")
    try:
        run = prod_repo.get_production_run(db, run_id, for_update=True)
        if run is None:
            raise NotFoundError(f"Production run {run_id} was not found.")
        if run.status != "DRAFT":
            raise ConflictError(
                f"Cannot plan run in status '{run.status}'; expected 'DRAFT'.",
                error_code="INVALID_STATE_TRANSITION",
            )
        run.status = "PLANNED"
        run.planned_at = datetime.now(UTC)
        run.version += 1

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PRODUCTION_RUN_PLANNED",
            entity_schema="production",
            entity_table="production_runs",
            entity_id=run.id,
            before_state={"status": "DRAFT"},
            after_state={"status": "PLANNED"},
            reason=f"Run {run.run_number} planned for execution",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = prod_repo.get_production_run(db, run_id)
    assert refreshed is not None
    return _hydrate_run(db, refreshed)


def issue_materials_and_start_run(
    db: Session, actor: CurrentActor, run_id: int, payload: StartProductionRequest
) -> ProductionRunOut:
    """PLANNED -> IN_PROGRESS: Atomically validate availability, lock balances, deplete FIFO lots, post PROD_ISSUE_OUT."""
    _require_operator(actor, "issue materials and start production")
    try:
        run = prod_repo.get_production_run(db, run_id, for_update=True)
        if run is None:
            raise NotFoundError(f"Production run {run_id} was not found.")

        if run.status in {"IN_PROGRESS", "COMPLETED", "POSTED"} or run.started_at is not None:
            raise ConflictError(
                f"Materials already issued for {run.run_number} (status: {run.status}). Double material issue is prohibited.",
                error_code="DOUBLE_MATERIAL_ISSUE",
            )
        if run.status != "PLANNED":
            raise ConflictError(
                f"Cannot start production from status '{run.status}'; run must be 'PLANNED'.",
                error_code="INVALID_STATE_TRANSITION",
            )

        issue_by_mat: dict[int, Decimal] = {}
        bom_mat_ids = {mi.material_id for mi in run.material_issues}
        mats = _get_materials_map(db, list(bom_mat_ids | {i.material_id for i in payload.items}))

        for item in payload.items:
            if item.material_id in issue_by_mat:
                raise DomainValidationError(f"Duplicate material_id {item.material_id} in issue payload.")
            if item.material_id not in bom_mat_ids:
                raise DomainValidationError(
                    f"Material {item.material_id} is not part of BOM v{run.bom_version_id} for this run."
                )
            mat = mats[item.material_id]
            base_qty, _m, _u = convert_to_base_qty(
                db,
                entered_qty=item.issued_qty,
                entered_uom=item.issued_uom,
                expected_dimension=mat.unit_dimension,
                expected_base_uom=mat.base_uom,
            )
            issue_by_mat[item.material_id] = base_qty

        # Require at least one raw material > 0
        raw_total_issued = sum(
            issue_by_mat.get(mi.material_id, Decimal("0.000"))
            for mi in run.material_issues
            if mi.issue_phase == "RAW_ISSUE"
        )
        if raw_total_issued <= 0:
            raise DomainValidationError("At least one cooking raw material quantity must be > 0 to start production.")

        # Acquire deterministic locks on ALL BOM materials in ascending ID order
        all_lock_ids = sorted(bom_mat_ids)
        locked_balances = inventory_repo.lock_balances_by_material_ids(db, all_lock_ids)

        # Validate material availability strictly before posting any ledger row
        shortages: list[dict] = []
        for mi in run.material_issues:
            mat = mats[mi.material_id]
            requested = issue_by_mat.get(mi.material_id, Decimal("0.000"))
            required_check = requested if requested > 0 else (
                Decimal(mi.planned_qty_base) if payload.require_all_bom_stock else Decimal("0.000")
            )
            if required_check <= 0:
                continue

            bal = locked_balances.get(mi.material_id)
            on_hand = Decimal(bal.on_hand_qty_base) if bal else Decimal("0.000")
            reserved = Decimal(bal.reserved_qty_base) if bal else Decimal("0.000")
            avail = max(Decimal("0.000"), on_hand - reserved)

            if avail < required_check:
                factor = _display_factor(mat.display_uom, mat.base_uom)
                shortages.append(
                    {
                        "material_id": mat.id,
                        "material_code": mat.code,
                        "material_name": mat.name,
                        "required_base": str(required_check),
                        "available_base": str(avail),
                        "shortage_base": str((required_check - avail).quantize(Decimal("0.001"))),
                        "display_uom": mat.display_uom,
                        "shortage_display": f"{((required_check - avail) / factor):.3f} {mat.display_uom}",
                    }
                )

        if shortages:
            msg = "; ".join(f"{s['material_name']} short by {s['shortage_display']}" for s in shortages)
            raise ConflictError(
                f"Cannot start production — insufficient available material stock ({msg}).",
                error_code="INSUFFICIENT_STOCK",
                details={"shortages": shortages},
            )

        now_utc = datetime.now(UTC)
        total_cost = 0
        for mi in run.material_issues:
            qty_to_issue = issue_by_mat.get(mi.material_id, Decimal("0.000"))
            if qty_to_issue <= 0:
                continue

            mat = mats[mi.material_id]
            factor = _display_factor(mat.display_uom, mat.base_uom)
            cost_paisa, consumed_lots = prod_repo.consume_fifo_lots(
                db, material_id=mi.material_id, qty_base=qty_to_issue
            )
            unit_cost_base = (
                (Decimal(cost_paisa) / qty_to_issue).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            )

            mov = InventoryMovement(
                item_category=mat.material_category,
                material_id=mat.id,
                movement_type="PROD_ISSUE_OUT",
                entered_qty=(qty_to_issue / factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
                entered_uom=mat.display_uom,
                signed_qty_base=-qty_to_issue,
                unit_cost_paisa_per_base=unit_cost_base,
                total_cost_paisa=cost_paisa,
                source_doc_type="PRODUCTION_RUN",
                reference_code=run.run_number,
                notes=f"Material issue at start of {run.run_number}",
                production_run_id=run.id,
                created_by=actor.user_id,
            )
            prod_repo.record_movement_with_lot_consumptions(
                db, movement=mov, consumed_lots=consumed_lots
            )

            mi.issued_qty_base = qty_to_issue
            mi.actual_consumed_qty_base = qty_to_issue
            mi.actual_good_used_base = qty_to_issue
            mi.cost_absorbed_paisa = cost_paisa
            mi.issued_by = actor.user_id
            mi.issued_at = now_utc
            total_cost += cost_paisa

        run.status = "IN_PROGRESS"
        run.started_at = now_utc
        run.version += 1
        if payload.notes:
            run.notes = ((run.notes or "") + f"\nStart notes: {payload.notes.strip()}").strip()
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PRODUCTION_MATERIALS_ISSUED",
            entity_schema="production",
            entity_table="production_runs",
            entity_id=run.id,
            before_state={"status": "PLANNED"},
            after_state={
                "status": "IN_PROGRESS",
                "issued_material_cost_paisa": total_cost,
                "issued_quantities": {str(k): str(v) for k, v in issue_by_mat.items()},
            },
            reason=f"Materials issued & production started for {run.run_number}",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = prod_repo.get_production_run(db, run_id)
    assert refreshed is not None
    return _hydrate_run(db, refreshed)


def complete_production_run(
    db: Session, actor: CurrentActor, run_id: int, payload: CompleteProductionRequest
) -> ProductionRunOut:
    """IN_PROGRESS -> COMPLETED: Capture actual consumption, unused returns, good/rejected output, damaged packaging & remarks."""
    _require_operator(actor, "record production execution and quality output")
    try:
        run = prod_repo.get_production_run(db, run_id, for_update=True)
        if run is None:
            raise NotFoundError(f"Production run {run_id} was not found.")
        if run.status != "IN_PROGRESS":
            raise ConflictError(
                f"Cannot record completion from status '{run.status}'; expected 'IN_PROGRESS'.",
                error_code="INVALID_STATE_TRANSITION",
            )

        ps = _get_pack_size(db, run.pack_size_id)
        bom_mat_ids = {mi.material_id for mi in run.material_issues}
        extra_mat_ids = {ew.material_id for ew in payload.extra_wastages if ew.material_id is not None}
        mats = _get_materials_map(
            db, list(bom_mat_ids | extra_mat_ids | {c.material_id for c in payload.consumptions})
        )

        # Map consumption entries cleanly
        cons_by_mat: dict[int, MaterialConsumptionInput] = {}
        for ci in payload.consumptions:
            if ci.material_id in cons_by_mat:
                raise DomainValidationError(f"Duplicate consumption row for material {ci.material_id}.")
            if ci.material_id not in bom_mat_ids:
                raise DomainValidationError(f"Material {ci.material_id} does not belong to this production run.")
            cons_by_mat[ci.material_id] = ci

        now_utc = datetime.now(UTC)
        for mi in run.material_issues:
            mat = mats[mi.material_id]
            ci = cons_by_mat.get(mi.material_id)
            if ci is None:
                continue

            norm_uom = normalize_uom(ci.uom)
            ret_base, _, _ = convert_to_base_qty(
                db,
                entered_qty=ci.returned_unused_qty,
                entered_uom=norm_uom,
                expected_dimension=mat.unit_dimension,
                expected_base_uom=mat.base_uom,
            )
            wasted_base, _, _ = convert_to_base_qty(
                db,
                entered_qty=ci.wasted_qty,
                entered_uom=norm_uom,
                expected_dimension=mat.unit_dimension,
                expected_base_uom=mat.base_uom,
            )
            dmg_base, _, _ = convert_to_base_qty(
                db,
                entered_qty=ci.damaged_packaging_qty,
                entered_uom=norm_uom,
                expected_dimension=mat.unit_dimension,
                expected_base_uom=mat.base_uom,
            )

            if mi.issue_phase == "PACKAGING_PACK":
                if ci.actual_good_used_qty is not None:
                    good_base, _, _ = convert_to_base_qty(
                        db,
                        entered_qty=ci.actual_good_used_qty,
                        entered_uom=norm_uom,
                        expected_dimension=mat.unit_dimension,
                        expected_base_uom=mat.base_uom,
                    )
                    consumed_base = (good_base + dmg_base).quantize(Decimal("0.001"))
                elif ci.actual_consumed_qty is not None:
                    consumed_base, _, _ = convert_to_base_qty(
                        db,
                        entered_qty=ci.actual_consumed_qty,
                        entered_uom=norm_uom,
                        expected_dimension=mat.unit_dimension,
                        expected_base_uom=mat.base_uom,
                    )
                    if dmg_base > consumed_base:
                        raise DomainValidationError(
                            f"Damaged qty ({dmg_base}) cannot exceed total consumed qty ({consumed_base}) for {mat.name}."
                        )
                    good_base = (consumed_base - dmg_base).quantize(Decimal("0.001"))
                else:
                    raise DomainValidationError(
                        f"Provide actual_good_used_qty or actual_consumed_qty for packaging item {mat.name}."
                    )
            else:
                if dmg_base > 0:
                    raise DomainValidationError(
                        f"damaged_packaging_qty applies only to PACKAGING items, not raw material {mat.name}."
                    )
                raw_val = ci.actual_consumed_qty if ci.actual_consumed_qty is not None else ci.actual_good_used_qty
                if raw_val is None:
                    raise DomainValidationError(f"Provide actual_consumed_qty for raw material {mat.name}.")
                consumed_base, _, _ = convert_to_base_qty(
                    db,
                    entered_qty=raw_val,
                    entered_uom=norm_uom,
                    expected_dimension=mat.unit_dimension,
                    expected_base_uom=mat.base_uom,
                )
                if wasted_base > consumed_base:
                    raise DomainValidationError(
                        f"Wasted qty ({wasted_base}) cannot exceed actual consumed qty ({consumed_base}) for {mat.name}."
                    )
                good_base = (consumed_base - wasted_base).quantize(Decimal("0.001"))

            issued_base = Decimal(mi.issued_qty_base).quantize(Decimal("0.001"))
            if ret_base > 0:
                if issued_base <= 0:
                    raise DomainValidationError(
                        f"Cannot return {ret_base} unused {mat.name} because zero quantity was issued."
                    )
                if ret_base > issued_base:
                    raise DomainValidationError(
                        f"Returned unused {mat.name} ({ret_base}) exceeds issued quantity ({issued_base})."
                    )
                if (consumed_base + ret_base) != issued_base:
                    raise DomainValidationError(
                        f"Material balance mismatch for {mat.name}: consumed ({consumed_base}) + returned ({ret_base}) must equal issued ({issued_base})."
                    )

            mi.actual_consumed_qty_base = consumed_base
            mi.actual_good_used_base = good_base
            mi.damaged_qty_base = dmg_base
            mi.returned_unused_qty_base = ret_base
            mi.wasted_qty_base = wasted_base

            # Record wastage records separately
            if dmg_base > 0:
                db.add(
                    ProductionWastage(
                        production_run_id=run.id,
                        material_id=mat.id,
                        wastage_type="DAMAGED_PACKAGING",
                        qty_base=dmg_base,
                        uom=mat.base_uom,
                        cost_impact_paisa=0,
                        reason=payload.quality_remarks or f"Damaged packaging recorded on {run.run_number}",
                        recorded_by=actor.user_id,
                    )
                )
            if wasted_base > 0 and mi.issue_phase == "RAW_ISSUE":
                db.add(
                    ProductionWastage(
                        production_run_id=run.id,
                        material_id=mat.id,
                        wastage_type="RAW_MATERIAL_WASTAGE",
                        qty_base=wasted_base,
                        uom=mat.base_uom,
                        cost_impact_paisa=0,
                        reason=payload.quality_remarks or f"Raw material wastage recorded on {run.run_number}",
                        recorded_by=actor.user_id,
                    )
                )

        # Record good & rejected outputs cleanly separated from packaging
        db.add(
            ProductionOutput(
                production_run_id=run.id,
                pack_size_id=run.pack_size_id,
                good_qty_pkts=payload.good_output_pkts,
                rejected_qty_pkts=payload.rejected_output_pkts,
                batch_code=payload.batch_code.strip(),
                expiry_date=payload.expiry_date,
                quality_remarks=payload.quality_remarks.strip() if payload.quality_remarks else None,
                recorded_by=actor.user_id,
            )
        )

        if payload.rejected_output_pkts > 0:
            db.add(
                ProductionWastage(
                    production_run_id=run.id,
                    pack_size_id=ps.id,
                    wastage_type="REJECTED_FINISHED_GOOD",
                    qty_base=Decimal(payload.rejected_output_pkts).quantize(Decimal("0.001")),
                    uom="packet",
                    cost_impact_paisa=0,
                    reason=payload.quality_remarks or "Rejected finished packets (excluded from saleable FG stock)",
                    recorded_by=actor.user_id,
                )
            )

        for ew in payload.extra_wastages:
            if ew.material_id is not None:
                mat = mats[ew.material_id]
                w_qty_base, _, _ = convert_to_base_qty(
                    db,
                    entered_qty=ew.qty,
                    entered_uom=ew.uom,
                    expected_dimension=mat.unit_dimension,
                    expected_base_uom=mat.base_uom,
                )
                w_uom = mat.base_uom
            else:
                w_qty_base = ew.qty.quantize(Decimal("0.001"))
                w_uom = normalize_uom(ew.uom)
            db.add(
                ProductionWastage(
                    production_run_id=run.id,
                    material_id=ew.material_id,
                    pack_size_id=ps.id if ew.material_id is None else None,
                    wastage_type=ew.wastage_type,
                    qty_base=w_qty_base,
                    uom=w_uom,
                    cost_impact_paisa=0,
                    reason=ew.reason.strip(),
                    recorded_by=actor.user_id,
                )
            )

        run.actual_good_output_pkts = payload.good_output_pkts
        run.rejected_output_pkts = payload.rejected_output_pkts
        run.quality_remarks = payload.quality_remarks.strip() if payload.quality_remarks else None
        run.status = "COMPLETED"
        run.completed_at = now_utc
        run.version += 1
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PRODUCTION_RUN_COMPLETED",
            entity_schema="production",
            entity_table="production_runs",
            entity_id=run.id,
            before_state={"status": "IN_PROGRESS"},
            after_state={
                "status": "COMPLETED",
                "good_output_pkts": payload.good_output_pkts,
                "rejected_output_pkts": payload.rejected_output_pkts,
                "batch_code": payload.batch_code.strip(),
            },
            reason=payload.quality_remarks or f"Completed {run.run_number}",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = prod_repo.get_production_run(db, run_id)
    assert refreshed is not None
    return _hydrate_run(db, refreshed)


def _compute_and_store_variances(
    db: Session,
    *,
    run: ProductionRun,
    ps: PackSize,
    mats: dict[int, Material],
    tolerance: Decimal,
) -> None:
    """Persist ProductionVariance rows and trigger audit.variance_alerts when |var%| > tolerance."""
    # 1. Yield Variance: (actual_good - expected) / expected * 100
    expected_out = Decimal(run.expected_output_pkts)
    actual_good = Decimal(run.actual_good_output_pkts)
    yield_diff = actual_good - expected_out
    yield_pct = ((yield_diff / expected_out) * Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    yield_flagged = abs(yield_pct) > tolerance
    v_yield = ProductionVariance(
        production_run_id=run.id,
        variance_scope="YIELD",
        planned_qty_base=expected_out.quantize(Decimal("0.001")),
        actual_qty_base=actual_good.quantize(Decimal("0.001")),
        variance_qty_base=yield_diff.quantize(Decimal("0.001")),
        variance_pct=yield_pct,
        tolerance_pct=tolerance,
        is_flagged=yield_flagged,
        formula_explanation=(
            f"Yield Variance = (Actual Good {int(actual_good)} - Expected {int(expected_out)}) / {int(expected_out)} × 100 = {yield_pct}%"
        ),
    )
    db.add(v_yield)
    db.flush()

    if yield_flagged:
        alert_type = "YIELD_LOSS" if yield_pct < 0 else "YIELD_EXCESS"
        db.add(
            VarianceAlert(
                production_run_id=run.id,
                production_variance_id=v_yield.id,
                alert_type=alert_type,
                message=(
                    f"{run.run_number} ({ps.sku_code}): Yield variance {yield_pct}% "
                    f"({int(actual_good)} good vs {int(expected_out)} expected) exceeds ±{tolerance}% tolerance."
                ),
            )
        )

    # 2. Raw & Packaging Variances
    for mi in run.material_issues:
        mat = mats[mi.material_id]
        factor = _display_factor(mat.display_uom, mat.base_uom)
        planned = Decimal(mi.planned_qty_base)
        actual = Decimal(mi.actual_consumed_qty_base)

        if mi.issue_phase == "RAW_ISSUE":
            diff = (actual - planned).quantize(Decimal("0.001"))
            var_pct = (
                ((diff / planned) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if planned > 0
                else None
            )
            flagged = var_pct is not None and abs(var_pct) > tolerance
            pv_raw = ProductionVariance(
                production_run_id=run.id,
                variance_scope="RAW_CONSUMPTION",
                material_id=mat.id,
                planned_qty_base=planned,
                actual_qty_base=actual,
                variance_qty_base=diff,
                variance_pct=var_pct,
                tolerance_pct=tolerance,
                is_flagged=flagged,
                formula_explanation=(
                    f"Raw Consumption Variance = (Actual {actual / factor:.3f} {mat.display_uom} - Standard {planned / factor:.3f} {mat.display_uom}) / {planned / factor:.3f} × 100 = {var_pct}%"
                ),
            )
            db.add(pv_raw)
            db.flush()

            if flagged and var_pct is not None:
                db.add(
                    VarianceAlert(
                        production_run_id=run.id,
                        production_variance_id=pv_raw.id,
                        alert_type="MATERIAL_OVERUSE" if var_pct > 0 else "MATERIAL_UNDERUSE",
                        message=(
                            f"{run.run_number} ({ps.sku_code}): {mat.name} consumption variance {var_pct}% "
                            f"({actual / factor:.3f} vs {planned / factor:.3f} {mat.display_uom}) exceeds ±{tolerance}% tolerance."
                        ),
                    )
                )
        else:
            # Packaging: record Batch BOM variance cleanly AND Output-Scaled variance transparently
            diff_batch = (actual - planned).quantize(Decimal("0.001"))
            batch_pct = (
                ((diff_batch / planned) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if planned > 0
                else None
            )
            db.add(
                ProductionVariance(
                    production_run_id=run.id,
                    variance_scope="PACKAGING_BATCH_BOM",
                    material_id=mat.id,
                    planned_qty_base=planned,
                    actual_qty_base=actual,
                    variance_qty_base=diff_batch,
                    variance_pct=batch_pct,
                    tolerance_pct=tolerance,
                    is_flagged=False,
                    formula_explanation=(
                        f"Batch BOM Comparison = Actual Total ({int(actual)}) vs Batch Standard ({int(planned)}): diff {int(diff_batch)} ({batch_pct}%). Kept unflagged when output-scaled variance governs."
                    ),
                )
            )

            # Output-scaled rule per BR-VAR-03
            is_carton = "carton" in mat.name.lower() or mat.code.startswith("MAT-CTN")
            if is_carton:
                scaled_std = Decimal(int(actual_good) // ps.packets_per_carton).quantize(Decimal("0.001"))
                loose = int(actual_good) % ps.packets_per_carton
                extra_note = f"; {loose} loose packets remain un-cartoned"
            else:
                scaled_std = actual_good.quantize(Decimal("0.001"))
                extra_note = f" (includes {int(mi.damaged_qty_base)} damaged units)"

            diff_scaled = (actual - scaled_std).quantize(Decimal("0.001"))
            scaled_pct = (
                ((diff_scaled / scaled_std) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if scaled_std > 0
                else None
            )
            scaled_flagged = scaled_pct is not None and abs(scaled_pct) > tolerance
            pv_pkg = ProductionVariance(
                production_run_id=run.id,
                variance_scope="PACKAGING_OUTPUT_SCALED",
                material_id=mat.id,
                planned_qty_base=scaled_std,
                actual_qty_base=actual,
                variance_qty_base=diff_scaled,
                variance_pct=scaled_pct,
                tolerance_pct=tolerance,
                is_flagged=scaled_flagged,
                formula_explanation=(
                    f"Output-Scaled Packaging Variance = (Actual Consumed {int(actual)} - Output-Scaled Expected {int(scaled_std)}) / {int(scaled_std)} × 100 = {scaled_pct}%{extra_note}"
                ),
            )
            db.add(pv_pkg)
            db.flush()

            if scaled_flagged and scaled_pct is not None:
                db.add(
                    VarianceAlert(
                        production_run_id=run.id,
                        production_variance_id=pv_pkg.id,
                        alert_type="PACKAGING_WASTAGE",
                        message=(
                            f"{run.run_number} ({ps.sku_code}): {mat.name} output-scaled variance {scaled_pct}% "
                            f"({int(actual)} consumed vs {int(scaled_std)} needed, {int(mi.damaged_qty_base)} damaged) exceeds ±{tolerance}%."
                        ),
                    )
                )


def post_production_run(
    db: Session, actor: CurrentActor, run_id: int
) -> ProductionRunOut:
    """COMPLETED -> POSTED: Single atomic posting reconciling consumption, returns, damaged packaging, FG output, variances & audit."""
    _require_operator(actor, "post completed production runs")
    try:
        run = prod_repo.get_production_run(db, run_id, for_update=True)
        if run is None:
            raise NotFoundError(f"Production run {run_id} was not found.")
        if run.status == "POSTED" or run.posted_at is not None:
            raise ConflictError(
                f"Production run {run.run_number} is already posted. Duplicate posting is blocked.",
                error_code="DUPLICATE_POST",
            )
        if run.status != "COMPLETED":
            raise ConflictError(
                f"Cannot post run in status '{run.status}'; expected 'COMPLETED'.",
                error_code="INVALID_STATE_TRANSITION",
            )
        if not run.material_issues or not run.outputs:
            raise DomainValidationError("Production run must have material issue and output records before posting.")

        company = _get_company(db)
        ps = _get_pack_size(db, run.pack_size_id)
        mats = _get_materials_map(db, [mi.material_id for mi in run.material_issues])
        existing_movements = prod_repo.list_movements_for_run(db, run.id)

        # Deterministic locks on all material balances & finished good pack_size balance
        locked_mat_bals = inventory_repo.lock_balances_by_material_ids(
            db, [mi.material_id for mi in run.material_issues]
        )
        inventory_repo.lock_balances_by_pack_size_ids(db, [run.pack_size_id])

        net_posted_out_by_mat: dict[int, Decimal] = {}
        for mov in existing_movements:
            if mov.material_id is not None:
                net_posted_out_by_mat[mov.material_id] = (
                    net_posted_out_by_mat.get(mov.material_id, Decimal("0.000")) - Decimal(mov.signed_qty_base)
                )

        # Reconcile every BOM material ledger delta atomically
        for mi in run.material_issues:
            mat = mats[mi.material_id]
            factor = _display_factor(mat.display_uom, mat.base_uom)
            already_out = net_posted_out_by_mat.get(mi.material_id, Decimal("0.000")).quantize(Decimal("0.001"))
            desired_consumed = Decimal(mi.actual_consumed_qty_base).quantize(Decimal("0.001"))
            bal = locked_mat_bals.get(mi.material_id)
            on_hand = Decimal(bal.on_hand_qty_base) if bal else Decimal("0.000")
            reserved = Decimal(bal.reserved_qty_base) if bal else Decimal("0.000")
            avail = max(Decimal("0.000"), on_hand - reserved)

            if already_out == Decimal("0.000") and desired_consumed > 0:
                # Never issued at Start (e.g. packaging issued at packing/posting)
                if avail < desired_consumed:
                    raise ConflictError(
                        f"Insufficient available stock for {mat.name} during posting: need {desired_consumed}, have {avail}.",
                        error_code="INSUFFICIENT_STOCK",
                    )
                good_part = Decimal(mi.actual_good_used_base).quantize(Decimal("0.001"))
                dmg_part = Decimal(mi.damaged_qty_base).quantize(Decimal("0.001"))

                total_mi_cost = 0
                if good_part > 0:
                    c_good, lots_good = prod_repo.consume_fifo_lots(
                        db, material_id=mat.id, qty_base=good_part
                    )
                    uc_good = (Decimal(c_good) / good_part).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                    mov_good = InventoryMovement(
                        item_category=mat.material_category,
                        material_id=mat.id,
                        movement_type="PROD_ISSUE_OUT",
                        entered_qty=(good_part / factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
                        entered_uom=mat.display_uom,
                        signed_qty_base=-good_part,
                        unit_cost_paisa_per_base=uc_good,
                        total_cost_paisa=c_good,
                        source_doc_type="PRODUCTION_RUN",
                        reference_code=run.run_number,
                        notes=f"Material consumption posted for {run.run_number}",
                        production_run_id=run.id,
                        created_by=actor.user_id,
                    )
                    prod_repo.record_movement_with_lot_consumptions(db, movement=mov_good, consumed_lots=lots_good)
                    total_mi_cost += c_good

                if dmg_part > 0:
                    c_dmg, lots_dmg = prod_repo.consume_fifo_lots(
                        db, material_id=mat.id, qty_base=dmg_part
                    )
                    uc_dmg = (Decimal(c_dmg) / dmg_part).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                    mov_dmg = InventoryMovement(
                        item_category=mat.material_category,
                        material_id=mat.id,
                        movement_type="PACKAGING_DAMAGE_OUT",
                        entered_qty=(dmg_part / factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
                        entered_uom=mat.display_uom,
                        signed_qty_base=-dmg_part,
                        unit_cost_paisa_per_base=uc_dmg,
                        total_cost_paisa=c_dmg,
                        source_doc_type="PRODUCTION_RUN",
                        reference_code=run.run_number,
                        notes=f"Damaged packaging posted for {run.run_number}",
                        production_run_id=run.id,
                        created_by=actor.user_id,
                    )
                    prod_repo.record_movement_with_lot_consumptions(db, movement=mov_dmg, consumed_lots=lots_dmg)
                    total_mi_cost += c_dmg

                mi.cost_absorbed_paisa = total_mi_cost

            elif already_out > desired_consumed:
                # Unused material returned to store -> PROD_RETURN_IN
                return_qty = (already_out - desired_consumed).quantize(Decimal("0.001"))
                mi.returned_unused_qty_base = return_qty
                avg_unit_cost = (
                    (Decimal(mi.cost_absorbed_paisa) / already_out).quantize(
                        Decimal("0.000001"), rounding=ROUND_HALF_UP
                    )
                    if already_out > 0
                    else Decimal("0.000000")
                )
                return_cost_paisa = int((return_qty * avg_unit_cost).quantize(Decimal(1), rounding=ROUND_HALF_UP))

                db.add(
                    InventoryMovement(
                        item_category=mat.material_category,
                        material_id=mat.id,
                        movement_type="PROD_RETURN_IN",
                        entered_qty=(return_qty / factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
                        entered_uom=mat.display_uom,
                        signed_qty_base=return_qty,
                        unit_cost_paisa_per_base=avg_unit_cost,
                        total_cost_paisa=return_cost_paisa,
                        source_doc_type="PRODUCTION_RUN",
                        reference_code=run.run_number,
                        notes=f"Unused material returned to store from {run.run_number}",
                        production_run_id=run.id,
                        created_by=actor.user_id,
                    )
                )
                db.add(
                    CostLot(
                        item_category=mat.material_category,
                        material_id=mat.id,
                        source_doc_type="PRODUCTION_RUN",
                        source_doc_id=run.id,
                        batch_code=f"RET-{run.run_number}",
                        original_qty_base=return_qty,
                        remaining_qty_base=return_qty,
                        unit_cost_paisa_per_base=avg_unit_cost,
                    )
                )
                mi.cost_absorbed_paisa = max(0, int(mi.cost_absorbed_paisa) - return_cost_paisa)

            elif desired_consumed > already_out:
                # Additional consumption above what was issued at Start
                extra_out = (desired_consumed - already_out).quantize(Decimal("0.001"))
                if avail < extra_out:
                    raise ConflictError(
                        f"Insufficient available stock for extra {mat.name} consumption: need {extra_out}, have {avail}.",
                        error_code="INSUFFICIENT_STOCK",
                    )
                c_extra, lots_extra = prod_repo.consume_fifo_lots(
                    db, material_id=mat.id, qty_base=extra_out
                )
                uc_extra = (Decimal(c_extra) / extra_out).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                mov_extra = InventoryMovement(
                    item_category=mat.material_category,
                    material_id=mat.id,
                    movement_type="PROD_ISSUE_OUT",
                    entered_qty=(extra_out / factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
                    entered_uom=mat.display_uom,
                    signed_qty_base=-extra_out,
                    unit_cost_paisa_per_base=uc_extra,
                    total_cost_paisa=c_extra,
                    source_doc_type="PRODUCTION_RUN",
                    reference_code=run.run_number,
                    notes=f"Additional material consumption posted for {run.run_number}",
                    production_run_id=run.id,
                    created_by=actor.user_id,
                )
                prod_repo.record_movement_with_lot_consumptions(db, movement=mov_extra, consumed_lots=lots_extra)
                mi.cost_absorbed_paisa = int(mi.cost_absorbed_paisa) + c_extra

        # Finished Goods output: ONLY good packets enter saleable FG stock!
        total_mat_cost = sum(int(mi.cost_absorbed_paisa) for mi in run.material_issues)
        good_pkts = run.actual_good_output_pkts
        if good_pkts > 0:
            fg_unit_cost = (Decimal(total_mat_cost) / Decimal(good_pkts)).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
            for out in run.outputs:
                if out.good_qty_pkts <= 0:
                    continue
                qty_dec = Decimal(out.good_qty_pkts).quantize(Decimal("0.001"))
                out_total_cost = int((qty_dec * fg_unit_cost).quantize(Decimal(1), rounding=ROUND_HALF_UP))
                db.add(
                    InventoryMovement(
                        item_category="FINISHED_GOOD",
                        pack_size_id=run.pack_size_id,
                        movement_type="PROD_OUTPUT_IN",
                        entered_qty=qty_dec,
                        entered_uom="packet",
                        signed_qty_base=qty_dec,
                        unit_cost_paisa_per_base=fg_unit_cost,
                        total_cost_paisa=out_total_cost,
                        source_doc_type="PRODUCTION_RUN",
                        reference_code=run.run_number,
                        notes=f"Good finished packets output from {run.run_number} (batch {out.batch_code})",
                        production_run_id=run.id,
                        created_by=actor.user_id,
                    )
                )
                db.add(
                    CostLot(
                        item_category="FINISHED_GOOD",
                        pack_size_id=run.pack_size_id,
                        source_doc_type="PRODUCTION_RUN",
                        source_doc_id=run.id,
                        batch_code=out.batch_code,
                        expiry_date=out.expiry_date,
                        original_qty_base=qty_dec,
                        remaining_qty_base=qty_dec,
                        unit_cost_paisa_per_base=fg_unit_cost,
                    )
                )

        # Evaluate & store variances + trigger tolerance alerts
        _compute_and_store_variances(
            db,
            run=run,
            ps=ps,
            mats=mats,
            tolerance=Decimal(company.variance_tolerance_pct),
        )

        now_utc = datetime.now(UTC)
        run.status = "POSTED"
        run.posted_by = actor.user_id
        run.posted_at = now_utc
        run.version += 1
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PRODUCTION_RUN_POSTED",
            entity_schema="production",
            entity_table="production_runs",
            entity_id=run.id,
            before_state={"status": "COMPLETED"},
            after_state={
                "status": "POSTED",
                "good_output_pkts": run.actual_good_output_pkts,
                "rejected_output_pkts": run.rejected_output_pkts,
                "material_cost_paisa": total_mat_cost,
            },
            reason=f"Atomically posted {run.run_number} to inventory ledger & variance audit",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = prod_repo.get_production_run(db, run_id)
    assert refreshed is not None
    return _hydrate_run(db, refreshed)


def cancel_production_run(
    db: Session, actor: CurrentActor, run_id: int, payload: CancelProductionRequest
) -> ProductionRunOut:
    """Cancel DRAFT, PLANNED, or abort IN_PROGRESS run (EC-06: unspoiled returns -> PROD_RETURN_IN; unreturned -> scrap)."""
    _require_operator(actor, "cancel production runs")
    try:
        run = prod_repo.get_production_run(db, run_id, for_update=True)
        if run is None:
            raise NotFoundError(f"Production run {run_id} was not found.")
        if run.status in {"COMPLETED", "POSTED", "CANCELLED"}:
            raise ConflictError(
                f"Cannot cancel run in status '{run.status}'.",
                error_code="INVALID_STATE_TRANSITION",
            )

        prev_status = run.status
        now_utc = datetime.now(UTC)
        mats = _get_materials_map(db, [mi.material_id for mi in run.material_issues])

        if prev_status == "IN_PROGRESS":
            ret_by_mat: dict[int, Decimal] = {}
            for ri in payload.returned_items:
                if ri.material_id not in mats:
                    raise DomainValidationError(f"Material {ri.material_id} does not belong to run.")
                mat = mats[ri.material_id]
                r_base, _, _ = convert_to_base_qty(
                    db,
                    entered_qty=ri.returned_qty,
                    entered_uom=ri.uom,
                    expected_dimension=mat.unit_dimension,
                    expected_base_uom=mat.base_uom,
                )
                ret_by_mat[ri.material_id] = r_base

            inventory_repo.lock_balances_by_material_ids(db, sorted(mats.keys()))

            for mi in run.material_issues:
                issued = Decimal(mi.issued_qty_base).quantize(Decimal("0.001"))
                if issued <= 0:
                    continue
                mat = mats[mi.material_id]
                factor = _display_factor(mat.display_uom, mat.base_uom)
                ret_qty = ret_by_mat.get(mi.material_id, Decimal("0.000")).quantize(Decimal("0.001"))
                if ret_qty > issued:
                    raise DomainValidationError(
                        f"Returned qty ({ret_qty}) for {mat.name} exceeds issued qty ({issued})."
                    )
                scrap_qty = (issued - ret_qty).quantize(Decimal("0.001"))

                if ret_qty > 0:
                    avg_uc = (Decimal(mi.cost_absorbed_paisa) / issued).quantize(
                        Decimal("0.000001"), rounding=ROUND_HALF_UP
                    )
                    ret_cost = int((ret_qty * avg_uc).quantize(Decimal(1), rounding=ROUND_HALF_UP))
                    db.add(
                        InventoryMovement(
                            item_category=mat.material_category,
                            material_id=mat.id,
                            movement_type="PROD_RETURN_IN",
                            entered_qty=(ret_qty / factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
                            entered_uom=mat.display_uom,
                            signed_qty_base=ret_qty,
                            unit_cost_paisa_per_base=avg_uc,
                            total_cost_paisa=ret_cost,
                            source_doc_type="PRODUCTION_RUN",
                            reference_code=run.run_number,
                            notes=f"Unspoiled material returned on abort of {run.run_number}",
                            production_run_id=run.id,
                            created_by=actor.user_id,
                        )
                    )
                    db.add(
                        CostLot(
                            item_category=mat.material_category,
                            material_id=mat.id,
                            source_doc_type="PRODUCTION_RUN",
                            source_doc_id=run.id,
                            batch_code=f"ABT-{run.run_number}",
                            original_qty_base=ret_qty,
                            remaining_qty_base=ret_qty,
                            unit_cost_paisa_per_base=avg_uc,
                        )
                    )
                if scrap_qty > 0:
                    db.add(
                        ProductionWastage(
                            production_run_id=run.id,
                            material_id=mat.id,
                            wastage_type="BURNT_BATCH",
                            qty_base=scrap_qty,
                            uom=mat.base_uom,
                            cost_impact_paisa=0,
                            reason=f"Aborted run loss: {payload.reason.strip()}",
                            recorded_by=actor.user_id,
                        )
                    )
                mi.returned_unused_qty_base = ret_qty
                mi.wasted_qty_base = scrap_qty
                mi.actual_consumed_qty_base = scrap_qty
                mi.actual_good_used_base = Decimal("0.000")

        run.status = "CANCELLED"
        run.cancelled_at = now_utc
        run.notes = ((run.notes or "") + f"\nCancelled: {payload.reason.strip()}").strip()
        run.version += 1

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PRODUCTION_RUN_CANCELLED",
            entity_schema="production",
            entity_table="production_runs",
            entity_id=run.id,
            before_state={"status": prev_status},
            after_state={"status": "CANCELLED"},
            reason=payload.reason.strip(),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = prod_repo.get_production_run(db, run_id)
    assert refreshed is not None
    return _hydrate_run(db, refreshed)


# ── Dashboard, Alerts & Reports ─────────────────────────────────────────────


def get_production_dashboard(
    db: Session,
    actor: CurrentActor,
    *,
    status: str | None = None,
    pack_size_id: int | None = None,
) -> ProductionDashboardOut:
    _require_viewer(actor, "view production dashboard")
    all_runs = prod_repo.list_production_runs(db, limit=500)
    filtered_runs = [
        r
        for r in all_runs
        if (not status or r.status == status) and (not pack_size_id or r.pack_size_id == pack_size_id)
    ]

    ps_map = {ps.id: ps for ps in prod_repo.list_pack_sizes(db, active_only=False)}
    all_alerts = prod_repo.list_alerts(db, limit=200)
    open_alerts = [a for a in all_alerts if a.status == "OPEN"]

    user_ids = {r.supervisor_id for r in all_runs} | {
        a.acknowledged_by for a in open_alerts if a.acknowledged_by is not None
    }
    users = _get_users_map(db, user_ids)

    ver_ids = list({r.bom_version_id for r in all_runs})
    ver_map: dict[int, BomVersion] = {}
    if ver_ids:
        for bv in db.execute(select(BomVersion).where(BomVersion.id.in_(ver_ids))).scalars().all():
            ver_map[bv.id] = bv

    open_alerts_by_run: dict[int, int] = {}
    for al in open_alerts:
        open_alerts_by_run[al.production_run_id] = open_alerts_by_run.get(al.production_run_id, 0) + 1

    # Aggregate upcoming shortages across PLANNED / DRAFT runs
    req_by_mat: dict[int, Decimal] = {}
    for r in all_runs:
        if r.status in {"DRAFT", "PLANNED"}:
            for mi in r.material_issues:
                req_by_mat[mi.material_id] = (
                    req_by_mat.get(mi.material_id, Decimal("0.000")) + Decimal(mi.planned_qty_base)
                )
    shortage_items: list[ShortageItemOut] = []
    if req_by_mat:
        mats = _get_materials_map(db, list(req_by_mat.keys()))
        bals = inventory_repo.get_balances_by_material_ids(db, list(req_by_mat.keys()))
        for mid, req_qty in sorted(req_by_mat.items()):
            mat = mats[mid]
            bal = bals.get(mid)
            avail = (
                max(Decimal("0.000"), Decimal(bal.on_hand_qty_base) - Decimal(bal.reserved_qty_base))
                if bal
                else Decimal("0.000")
            )
            if req_qty > avail:
                shortage_items.append(
                    ShortageItemOut(
                        material_id=mid,
                        material_code=mat.code,
                        material_name=mat.name,
                        display_uom=mat.display_uom,
                        base_uom=mat.base_uom,
                        display_factor=_display_factor(mat.display_uom, mat.base_uom),
                        required_qty_base=req_qty.quantize(Decimal("0.001")),
                        available_qty_base=avail.quantize(Decimal("0.001")),
                        shortage_qty_base=(req_qty - avail).quantize(Decimal("0.001")),
                    )
                )

    counts = {s: 0 for s in ("DRAFT", "PLANNED", "IN_PROGRESS", "COMPLETED", "POSTED", "CANCELLED")}
    total_exp = 0
    total_good = 0
    total_rej = 0
    total_dmg = Decimal("0.000")
    flagged_runs = 0

    for r in all_runs:
        counts[r.status] = counts.get(r.status, 0) + 1
        if r.status in {"COMPLETED", "POSTED"}:
            total_exp += r.expected_output_pkts
            total_good += r.actual_good_output_pkts
            total_rej += r.rejected_output_pkts
        dmg_r = sum((Decimal(mi.damaged_qty_base) for mi in r.material_issues), Decimal("0.000"))
        total_dmg += dmg_r
        if any(v.is_flagged for v in r.variances):
            flagged_runs += 1

    run_summaries: list[ProductionRunSummaryOut] = []
    for r in filtered_runs:
        ps = ps_map[r.pack_size_id]
        bv = ver_map.get(r.bom_version_id)
        dmg_r = sum((Decimal(mi.damaged_qty_base) for mi in r.material_issues), Decimal("0.000"))
        run_summaries.append(
            ProductionRunSummaryOut(
                id=r.id,
                run_number=r.run_number,
                pack_size_id=r.pack_size_id,
                sku_code=ps.sku_code,
                display_name=ps.display_name,
                bom_version_id=r.bom_version_id,
                version_no=bv.version_no if bv else 0,
                batch_multiplier=Decimal(r.batch_multiplier),
                expected_output_pkts=r.expected_output_pkts,
                actual_good_output_pkts=r.actual_good_output_pkts,
                rejected_output_pkts=r.rejected_output_pkts,
                status=r.status,
                run_date=r.run_date,
                supervisor_name=users[r.supervisor_id].full_name if r.supervisor_id in users else "Unknown",
                has_flagged_variance=any(v.is_flagged for v in r.variances),
                open_alert_count=open_alerts_by_run.get(r.id, 0),
                damaged_packaging_qty=dmg_r.quantize(Decimal("0.001")),
            )
        )

    runs_map = {r.id: r for r in all_runs}
    open_alert_outs = [_hydrate_alert(al, runs_map, ps_map, users) for al in open_alerts]

    return ProductionDashboardOut(
        total_runs=len(all_runs),
        draft_count=counts["DRAFT"],
        planned_count=counts["PLANNED"],
        in_progress_count=counts["IN_PROGRESS"],
        completed_count=counts["COMPLETED"],
        posted_count=counts["POSTED"],
        cancelled_count=counts["CANCELLED"],
        total_expected_output_pkts=total_exp,
        total_good_output_pkts=total_good,
        total_rejected_output_pkts=total_rej,
        total_damaged_packaging_units=total_dmg.quantize(Decimal("0.001")),
        flagged_variance_count=flagged_runs,
        open_alerts_count=len(open_alerts),
        upcoming_shortages=shortage_items,
        open_alerts=open_alert_outs,
        runs=run_summaries,
    )


def get_production_run_detail(
    db: Session, actor: CurrentActor, run_id: int
) -> ProductionRunOut:
    _require_viewer(actor, "view production run details")
    run = prod_repo.get_production_run(db, run_id)
    if run is None:
        raise NotFoundError(f"Production run {run_id} was not found.")
    return _hydrate_run(db, run)


def list_alerts(
    db: Session, actor: CurrentActor, *, status: str | None = None
) -> list[VarianceAlertOut]:
    _require_viewer(actor, "view variance alerts")
    alerts = prod_repo.list_alerts(db, status=status)
    if not alerts:
        return []
    run_ids = list({a.production_run_id for a in alerts})
    runs = db.execute(select(ProductionRun).where(ProductionRun.id.in_(run_ids))).scalars().all()
    runs_map = {r.id: r for r in runs}
    ps_map = {ps.id: ps for ps in prod_repo.list_pack_sizes(db, active_only=False)}
    users = _get_users_map(db, {a.acknowledged_by for a in alerts if a.acknowledged_by})
    return [_hydrate_alert(al, runs_map, ps_map, users) for al in alerts]


def acknowledge_alert(
    db: Session, actor: CurrentActor, alert_id: int, note: str | None = None
) -> VarianceAlertOut:
    if actor.role_code not in {"FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "OWNER"}:
        raise AuthorizationError("Only Admin, Production Supervisor, or Owner can acknowledge variance alerts.")
    alert = prod_repo.get_alert(db, alert_id, for_update=True)
    if alert is None:
        raise NotFoundError(f"Variance alert {alert_id} was not found.")
    if alert.status == "ACKNOWLEDGED":
        raise ConflictError("Variance alert is already acknowledged.", error_code="ALREADY_ACKNOWLEDGED")

    alert.status = "ACKNOWLEDGED"
    alert.acknowledged_by = actor.user_id
    alert.acknowledged_at = datetime.now(UTC)
    alert.acknowledgement_note = note.strip() if note else None

    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="VARIANCE_ALERT_ACKNOWLEDGED",
        entity_schema="audit",
        entity_table="variance_alerts",
        entity_id=alert.id,
        after_state={"status": "ACKNOWLEDGED", "note": alert.acknowledgement_note},
        reason=alert.acknowledgement_note or "Acknowledged variance alert",
    )
    db.commit()

    run = prod_repo.get_production_run(db, alert.production_run_id)
    assert run is not None
    ps = db.execute(select(PackSize).where(PackSize.id == run.pack_size_id)).scalar_one()
    users = _get_users_map(db, {actor.user_id})
    return _hydrate_alert(alert, {run.id: run}, {ps.id: ps}, users)


def list_production_variance_report(
    db: Session, actor: CurrentActor
) -> list[ProductionVarianceReportRow]:
    _require_viewer(actor, "view production variance reports")
    runs = prod_repo.list_production_runs(db, status="POSTED", limit=200)
    ps_map = {ps.id: ps for ps in prod_repo.list_pack_sizes(db, active_only=False)}
    mats = {m.id: m for m in db.execute(select(Material)).scalars().all()}
    oil_mat = next((m for m in mats.values() if m.code == "MAT-OIL"), None)
    ver_ids = list({r.bom_version_id for r in runs})
    ver_map: dict[int, BomVersion] = {}
    if ver_ids:
        for bv in db.execute(select(BomVersion).where(BomVersion.id.in_(ver_ids))).scalars().all():
            ver_map[bv.id] = bv

    rows: list[ProductionVarianceReportRow] = []
    for r in runs:
        ps = ps_map[r.pack_size_id]
        bv = ver_map.get(r.bom_version_id)
        yield_var = next((v for v in r.variances if v.variance_scope == "YIELD"), None)
        oil_var = (
            next(
                (v for v in r.variances if v.variance_scope == "RAW_CONSUMPTION" and oil_mat and v.material_id == oil_mat.id),
                None,
            )
            if oil_mat
            else None
        )
        dmg = sum((Decimal(mi.damaged_qty_base) for mi in r.material_issues), Decimal("0.000"))
        rows.append(
            ProductionVarianceReportRow(
                run_id=r.id,
                run_number=r.run_number,
                run_date=r.run_date,
                sku_code=ps.sku_code,
                display_name=ps.display_name,
                bom_version_no=bv.version_no if bv else 0,
                batch_multiplier=Decimal(r.batch_multiplier),
                expected_output_pkts=r.expected_output_pkts,
                actual_good_output_pkts=r.actual_good_output_pkts,
                rejected_output_pkts=r.rejected_output_pkts,
                yield_variance_pct=Decimal(yield_var.variance_pct) if yield_var and yield_var.variance_pct is not None else None,
                oil_variance_pct=Decimal(oil_var.variance_pct) if oil_var and oil_var.variance_pct is not None else None,
                damaged_packaging_qty=dmg.quantize(Decimal("0.001")),
                status=r.status,
                flagged_count=sum(1 for v in r.variances if v.is_flagged),
            )
        )
    return rows
