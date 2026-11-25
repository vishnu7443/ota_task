from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.modules.iam.models import User
from app.modules.sales.models import (
    Customer,
    PackSize,
    PriceList,
    PriceListItem,
    Product,
    SalesmanProfile,
)


def list_customers(
    db: Session,
    *,
    salesman_user_id: int | None = None,
    search: str | None = None,
) -> list[Customer]:
    stmt = (
        select(Customer)
        .options(joinedload(Customer.addresses))
        .where(Customer.is_active.is_(True))
    )
    if salesman_user_id is not None:
        stmt = stmt.where(
            or_(
                Customer.assigned_salesman_id == salesman_user_id,
                Customer.assigned_salesman_id.is_(None),
            )
        )
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Customer.name.ilike(pattern),
                Customer.code.ilike(pattern),
                Customer.primary_state_name.ilike(pattern),
            )
        )
    stmt = stmt.order_by(Customer.name.asc())
    return list(db.execute(stmt).unique().scalars().all())


def get_customer_by_id(db: Session, customer_id: int) -> Customer | None:
    stmt = (
        select(Customer)
        .options(joinedload(Customer.addresses))
        .where(Customer.id == customer_id)
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def list_active_pack_sizes(db: Session) -> list[PackSize]:
    stmt = (
        select(PackSize)
        .join(Product, PackSize.product_id == Product.id)
        .options(joinedload(PackSize.product))
        .where(PackSize.is_active.is_(True), Product.is_active.is_(True))
        .order_by(PackSize.display_name.asc())
    )
    return list(db.execute(stmt).scalars().all())


def get_pack_sizes_by_ids(
    db: Session, pack_size_ids: list[int], *, include_inactive: bool = False
) -> dict[int, PackSize]:
    if not pack_size_ids:
        return {}
    stmt = (
        select(PackSize)
        .join(Product, PackSize.product_id == Product.id)
        .options(joinedload(PackSize.product))
        .where(PackSize.id.in_(pack_size_ids))
    )
    if not include_inactive:
        stmt = stmt.where(PackSize.is_active.is_(True), Product.is_active.is_(True))
    rows = db.execute(stmt).scalars().all()
    return {row.id: row for row in rows}


def resolve_price_paisa_from_lists(
    db: Session,
    *,
    pack_size_id: int,
    customer_id: int | None,
    qty_pkts: int,
    as_of: date,
) -> int | None:
    # 1. Customer-specific active price list override
    if customer_id is not None:
        cust_stmt = (
            select(PriceListItem.unit_price_paisa)
            .join(PriceList, PriceListItem.price_list_id == PriceList.id)
            .where(
                PriceList.customer_id == customer_id,
                PriceList.is_active.is_(True),
                PriceList.effective_from <= as_of,
                or_(PriceList.effective_to.is_(None), PriceList.effective_to >= as_of),
                PriceListItem.pack_size_id == pack_size_id,
                PriceListItem.min_qty <= qty_pkts,
            )
            .order_by(PriceListItem.min_qty.desc(), PriceList.effective_from.desc())
            .limit(1)
        )
        cust_price = db.execute(cust_stmt).scalar_one_or_none()
        if cust_price is not None:
            return int(cust_price)

    # 2. Default active price list
    default_stmt = (
        select(PriceListItem.unit_price_paisa)
        .join(PriceList, PriceListItem.price_list_id == PriceList.id)
        .where(
            PriceList.is_default.is_(True),
            PriceList.is_active.is_(True),
            PriceList.effective_from <= as_of,
            or_(PriceList.effective_to.is_(None), PriceList.effective_to >= as_of),
            PriceListItem.pack_size_id == pack_size_id,
            PriceListItem.min_qty <= qty_pkts,
        )
        .order_by(PriceListItem.min_qty.desc())
        .limit(1)
    )
    return db.execute(default_stmt).scalar_one_or_none()


def get_salesman_profile_by_user_id(db: Session, user_id: int) -> SalesmanProfile | None:
    return db.execute(
        select(SalesmanProfile).where(SalesmanProfile.user_id == user_id)
    ).scalar_one_or_none()


def list_active_salesmen(db: Session) -> list[tuple[SalesmanProfile, User]]:
    stmt = (
        select(SalesmanProfile, User)
        .join(User, SalesmanProfile.user_id == User.id)
        .where(SalesmanProfile.is_active.is_(True), User.is_active.is_(True))
        .order_by(User.full_name.asc())
    )
    return [(row[0], row[1]) for row in db.execute(stmt).all()]
