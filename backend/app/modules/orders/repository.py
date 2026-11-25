from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.modules.iam.models import User
from app.modules.orders.models import SalesOrder, SalesOrderItem
from app.modules.sales.models import Customer


def get_by_salesman_and_client_order_id(
    db: Session, salesman_id: int, client_order_id
) -> SalesOrder | None:
    stmt = (
        select(SalesOrder)
        .options(
            joinedload(SalesOrder.items),
            joinedload(SalesOrder.status_history),
            joinedload(SalesOrder.approvals),
        )
        .where(
            SalesOrder.salesman_id == salesman_id,
            SalesOrder.client_order_id == client_order_id,
        )
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def get_order_by_id(db: Session, order_id: int) -> SalesOrder | None:
    stmt = (
        select(SalesOrder)
        .options(
            joinedload(SalesOrder.items),
            joinedload(SalesOrder.status_history),
            joinedload(SalesOrder.approvals),
        )
        .where(SalesOrder.id == order_id)
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def get_order_by_id_for_update(db: Session, order_id: int) -> SalesOrder | None:
    """Acquire an exclusive row lock on sales_orders before reading relations cleanly."""
    order = db.execute(
        select(SalesOrder).where(SalesOrder.id == order_id).with_for_update()
    ).scalar_one_or_none()
    if order is None:
        return None
    # Load child collections via separate statements after holding the parent row lock
    _ = list(
        db.execute(
            select(SalesOrderItem)
            .where(SalesOrderItem.sales_order_id == order_id)
            .order_by(SalesOrderItem.id.asc())
        ).scalars().all()
    )
    db.refresh(order, attribute_names=["items", "status_history", "approvals"])
    return order


def list_orders(
    db: Session,
    *,
    salesman_id: int | None = None,
    customer_id: int | None = None,
    statuses: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    has_shortage: bool | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[SalesOrder], int]:
    base_stmt = (
        select(SalesOrder)
        .join(Customer, SalesOrder.customer_id == Customer.id)
        .join(User, SalesOrder.salesman_id == User.id)
    )
    if salesman_id is not None:
        base_stmt = base_stmt.where(SalesOrder.salesman_id == salesman_id)
    if customer_id is not None:
        base_stmt = base_stmt.where(SalesOrder.customer_id == customer_id)
    if statuses:
        base_stmt = base_stmt.where(SalesOrder.status.in_(statuses))
    if date_from is not None:
        base_stmt = base_stmt.where(SalesOrder.order_date >= date_from)
    if date_to is not None:
        base_stmt = base_stmt.where(SalesOrder.order_date <= date_to)
    if has_shortage is not None:
        base_stmt = base_stmt.where(SalesOrder.has_shortage.is_(has_shortage))
    if search:
        pattern = f"%{search.strip()}%"
        base_stmt = base_stmt.where(
            or_(
                SalesOrder.order_number.ilike(pattern),
                Customer.name.ilike(pattern),
                Customer.code.ilike(pattern),
                User.full_name.ilike(pattern),
            )
        )

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = int(db.execute(count_stmt).scalar_one())

    items_stmt = (
        base_stmt.options(joinedload(SalesOrder.items))
        .order_by(SalesOrder.submitted_at.desc().nulls_last(), SalesOrder.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = list(db.execute(items_stmt).unique().scalars().all())
    return rows, total


def list_all_orders_for_summary(db: Session) -> list[SalesOrder]:
    stmt = (
        select(SalesOrder)
        .options(joinedload(SalesOrder.items))
        .order_by(SalesOrder.id.desc())
    )
    return list(db.execute(stmt).unique().scalars().all())
