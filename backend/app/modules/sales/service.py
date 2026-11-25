from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError, DomainValidationError, NotFoundError
from app.modules.iam.schemas import CurrentActor
from app.modules.inventory import service as inventory_service
from app.modules.sales import repository as sales_repo
from app.modules.sales.models import Customer, CustomerAddress, PackSize
from app.modules.sales.schemas import (
    CustomerAddressResponse,
    CustomerSummary,
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
