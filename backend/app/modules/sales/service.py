import re
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.modules.audit.service import record_audit_log
from app.modules.iam.models import User
from app.modules.iam.schemas import CurrentActor
from app.modules.inventory import service as inventory_service
from app.modules.sales import repository as sales_repo
from app.modules.sales.models import (
    Customer,
    CustomerAddress,
    PackSize,
    PriceList,
    PriceListItem,
)
from app.modules.sales.schemas import (
    CustomerAddressResponse,
    CustomerCreateRequest,
    CustomerSummary,
    PackSizePriceUpdateRequest,
    ProductPackResponse,
    SalesmanOption,
)

IST = ZoneInfo("Asia/Kolkata")


def _pick_default_shipping(customer: Customer) -> CustomerAddress | None:
    shipping = [a for a in customer.addresses if a.address_type == "SHIPPING"]
    for addr in shipping:
        if addr.is_default:
            return addr
    return shipping[0] if shipping else (customer.addresses[0] if customer.addresses else None)


def _to_customer_summary(customer: Customer) -> CustomerSummary:
    ship = _pick_default_shipping(customer)
    ship_dto = (
        CustomerAddressResponse(
            id=ship.id,
            address_type=ship.address_type,
            line1=ship.line1,
            line2=ship.line2,
            city=ship.city,
            state_name=ship.state_name,
            state_code=ship.state_code,
            pincode=ship.pincode,
        )
        if ship
        else None
    )
    return CustomerSummary(
        id=customer.id,
        code=customer.code,
        name=customer.name,
        customer_type=customer.customer_type,
        gstin=customer.gstin,
        primary_state_name=customer.primary_state_name,
        primary_state_code=customer.primary_state_code,
        phone=customer.phone,
        assigned_salesman_id=customer.assigned_salesman_id,
        default_shipping_address=ship_dto,
    )


def list_accessible_customers(
    db: Session, actor: CurrentActor, search: str | None = None
) -> list[CustomerSummary]:
    salesman_scope = actor.user_id if actor.role_code == "SALESMAN" else None
    customers = sales_repo.list_customers(db, salesman_user_id=salesman_scope, search=search)
    return [_to_customer_summary(c) for c in customers]


def validate_customer_access(db: Session, actor: CurrentActor, customer_id: int) -> Customer:
    customer = sales_repo.get_customer_by_id(db, customer_id)
    if customer is None:
        raise NotFoundError(f"Customer {customer_id} was not found.")
    if not customer.is_active:
        raise DomainValidationError(f"Customer '{customer.name}' is inactive.")
    if (
        actor.role_code == "SALESMAN"
        and customer.assigned_salesman_id is not None
        and customer.assigned_salesman_id != actor.user_id
    ):
        raise AuthorizationError("You do not have access to this customer account.")
    return customer


def resolve_authoritative_price_paisa(
    db: Session,
    *,
    pack_size: PackSize,
    customer_id: int | None,
    qty_pkts: int,
    as_of: date,
) -> int:
    price = sales_repo.resolve_price_paisa_from_lists(
        db,
        pack_size_id=pack_size.id,
        customer_id=customer_id,
        qty_pkts=qty_pkts,
        as_of=as_of,
    )
    return price if price is not None else int(pack_size.base_selling_price_paisa)


def list_active_products(
    db: Session, actor: CurrentActor, customer_id: int | None = None
) -> list[ProductPackResponse]:
    if customer_id is not None:
        validate_customer_access(db, actor, customer_id)

    pack_sizes = sales_repo.list_active_pack_sizes(db)
    sku_ids = [ps.id for ps in pack_sizes]
    availability = inventory_service.get_pack_size_availability_map(db, sku_ids)
    from datetime import datetime

    today_ist = datetime.now(IST).date()
    results: list[ProductPackResponse] = []
    for ps in pack_sizes:
        price_paisa = resolve_authoritative_price_paisa(
            db, pack_size=ps, customer_id=customer_id, qty_pkts=1, as_of=today_ist
        )
        stock = availability.get(ps.id, {"on_hand_pkts": 0, "available_pkts": 0})
        results.append(
            ProductPackResponse(
                pack_size_id=ps.id,
                product_id=ps.product.id,
                product_code=ps.product.product_code,
                sku_code=ps.sku_code,
                product_name=ps.product.name,
                display_name=ps.display_name,
                category=ps.product.category,
                hsn_code=ps.product.hsn_code,
                gst_rate_bps=ps.product.gst_rate_bps,
                pack_weight_g=ps.pack_weight_g,
                packets_per_carton=ps.packets_per_carton,
                selling_price_paisa=price_paisa,
                available_stock_pkts=stock["available_pkts"],
                on_hand_stock_pkts=stock["on_hand_pkts"],
            )
        )
    return results


def list_salesmen_options(db: Session) -> list[SalesmanOption]:
    rows = sales_repo.list_active_salesmen(db)
    return [
        SalesmanOption(
            user_id=user.id,
            full_name=user.full_name,
            employee_code=profile.employee_code,
            territory=profile.territory,
        )
        for profile, user in rows
    ]



def create_customer(
    db: Session, actor: CurrentActor, payload: CustomerCreateRequest
) -> CustomerSummary:
    if actor.role_code != "FACTORY_ADMIN":
        raise AuthorizationError("Only Factory Admin can register new customer accounts.")
    code = payload.code.strip().upper()
    if len(code) < 3 or len(code) > 32:
        raise DomainValidationError("Customer code must be 3–32 characters.")
    if payload.customer_type not in {"RETAILER", "DISTRIBUTOR"}:
        raise DomainValidationError("customer_type must be RETAILER or DISTRIBUTOR.")
    state_code = payload.primary_state_code.strip()
    if not re.fullmatch(r"[0-9]{2}", state_code):
        raise DomainValidationError("primary_state_code must be a 2-digit GST state code.")
    pincode = payload.pincode.strip()
    if not re.fullmatch(r"[0-9]{6}", pincode):
        raise DomainValidationError("pincode must be a 6-digit Indian PIN code.")
    if payload.credit_days < 0:
        raise DomainValidationError("credit_days cannot be negative.")

    gstin_clean = payload.gstin.strip().upper() if payload.gstin and payload.gstin.strip() else None
    if gstin_clean is not None:
        if not re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]", gstin_clean):
            raise DomainValidationError("Invalid 15-character Indian GSTIN format.")
        if gstin_clean[:2] != state_code:
            raise DomainValidationError("First two digits of GSTIN must match primary_state_code.")

    if db.execute(select(Customer).where(Customer.code == code)).scalar_one_or_none() is not None:
        raise ConflictError(f"Customer code '{code}' already exists.", error_code="DUPLICATE_CUSTOMER_CODE")

    if payload.assigned_salesman_id is not None:
        sm = db.execute(select(User).where(User.id == payload.assigned_salesman_id)).scalar_one_or_none()
        if sm is None:
            raise NotFoundError(f"Assigned salesman user {payload.assigned_salesman_id} not found.")

    cust = Customer(
        code=code,
        name=payload.name.strip(),
        customer_type=payload.customer_type,
        gstin=gstin_clean,
        primary_state_name=payload.primary_state_name.strip(),
        primary_state_code=state_code,
        phone=payload.phone.strip() if payload.phone and payload.phone.strip() else None,
        assigned_salesman_id=payload.assigned_salesman_id,
        credit_days=payload.credit_days,
        is_active=True,
    )
    db.add(cust)
    db.flush()

    for addr_type in ("BILLING", "SHIPPING"):
        db.add(
            CustomerAddress(
                customer_id=cust.id,
                address_type=addr_type,
                line1=payload.address_line1.strip(),
                city=payload.city.strip(),
                state_name=cust.primary_state_name,
                state_code=state_code,
                pincode=pincode,
                is_default=True,
            )
        )
    db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="CUSTOMER_CREATED",
        entity_schema="sales",
        entity_table="customers",
        entity_id=cust.id,
        after_state={
            "code": cust.code,
            "name": cust.name,
            "customer_type": cust.customer_type,
            "primary_state_code": cust.primary_state_code,
            "gstin": cust.gstin,
        },
        reason=f"Registered customer {cust.name}",
    )
    db.commit()
    reloaded = sales_repo.get_customer_by_id(db, cust.id)
    assert reloaded is not None
    return _to_customer_summary(reloaded)


def update_pack_size_price(
    db: Session, actor: CurrentActor, pack_size_id: int, payload: PackSizePriceUpdateRequest
) -> ProductPackResponse:
    if actor.role_code != "FACTORY_ADMIN":
        raise AuthorizationError("Only Factory Admin can update catalog selling prices.")
    if payload.unit_price_paisa < 0:
        raise DomainValidationError("unit_price_paisa cannot be negative.")
    reason = payload.reason.strip()
    if len(reason) < 5:
        raise DomainValidationError("Price change reason must be at least 5 characters.")

    ps = db.execute(select(PackSize).where(PackSize.id == pack_size_id)).scalar_one_or_none()
    if ps is None:
        raise NotFoundError(f"Pack size {pack_size_id} was not found.")

    old_price = int(ps.base_selling_price_paisa)
    ps.base_selling_price_paisa = int(payload.unit_price_paisa)

    # Also update active default price list entry (min_qty=1) if present
    def_pl = db.execute(
        select(PriceList).where(PriceList.is_default.is_(True), PriceList.is_active.is_(True))
    ).scalar_one_or_none()
    if def_pl is not None:
        pli = db.execute(
            select(PriceListItem).where(
                PriceListItem.price_list_id == def_pl.id,
                PriceListItem.pack_size_id == ps.id,
                PriceListItem.min_qty == 1,
            )
        ).scalar_one_or_none()
        if pli is not None:
            pli.unit_price_paisa = int(payload.unit_price_paisa)
        else:
            db.add(
                PriceListItem(
                    price_list_id=def_pl.id,
                    pack_size_id=ps.id,
                    unit_price_paisa=int(payload.unit_price_paisa),
                    min_qty=1,
                )
            )
    db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="PRICE_UPDATED",
        entity_schema="sales",
        entity_table="pack_sizes",
        entity_id=ps.id,
        before_state={"base_selling_price_paisa": old_price},
        after_state={"base_selling_price_paisa": int(payload.unit_price_paisa)},
        reason=reason,
    )
    db.commit()
    return next(p for p in list_active_products(db, actor) if p.pack_size_id == ps.id)
