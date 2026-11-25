from datetime import date
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.modules.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
    Supplier,
)


def list_suppliers(
    db: Session, *, active_only: bool = False, search: str | None = None
) -> list[Supplier]:
    stmt = select(Supplier)
    if active_only:
        stmt = stmt.where(Supplier.is_active.is_(True))
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Supplier.name.ilike(pattern),
                Supplier.code.ilike(pattern),
                Supplier.contact_person.ilike(pattern),
                Supplier.gstin.ilike(pattern),
            )
        )
    stmt = stmt.order_by(Supplier.is_active.desc(), Supplier.name.asc())
    return list(db.execute(stmt).scalars().all())


def get_supplier_by_id(db: Session, supplier_id: int) -> Supplier | None:
    return db.execute(select(Supplier).where(Supplier.id == supplier_id)).scalar_one_or_none()


def get_supplier_by_code(db: Session, code: str) -> Supplier | None:
    return db.execute(select(Supplier).where(Supplier.code == code.upper())).scalar_one_or_none()


def get_purchase_order_by_id(
    db: Session, po_id: int, *, for_update: bool = False
) -> PurchaseOrder | None:
    if for_update:
        po = db.execute(
            select(PurchaseOrder).where(PurchaseOrder.id == po_id).with_for_update()
        ).scalar_one_or_none()
        if po is None:
            return None
        _ = list(
            db.execute(
                select(PurchaseOrderItem)
                .where(PurchaseOrderItem.purchase_order_id == po_id)
                .order_by(PurchaseOrderItem.id.asc())
                .with_for_update()
            ).scalars().all()
        )
        db.refresh(po, attribute_names=["items", "supplier"])
        return po

    stmt = (
        select(PurchaseOrder)
        .options(joinedload(PurchaseOrder.items), joinedload(PurchaseOrder.supplier))
        .where(PurchaseOrder.id == po_id)
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def list_purchase_orders(
    db: Session,
    *,
    supplier_id: int | None = None,
    status: str | None = None,
    search: str | None = None,
) -> list[PurchaseOrder]:
    stmt = select(PurchaseOrder).join(Supplier, PurchaseOrder.supplier_id == Supplier.id)
    if supplier_id is not None:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                PurchaseOrder.po_number.ilike(pattern),
                Supplier.name.ilike(pattern),
                Supplier.code.ilike(pattern),
            )
        )
    stmt = stmt.options(joinedload(PurchaseOrder.items), joinedload(PurchaseOrder.supplier)).order_by(
        PurchaseOrder.order_date.desc(), PurchaseOrder.id.desc()
    )
    return list(db.execute(stmt).unique().scalars().all())


def get_receipt_by_client_id(
    db: Session, client_receipt_id: UUID
) -> PurchaseReceipt | None:
    stmt = (
        select(PurchaseReceipt)
        .options(joinedload(PurchaseReceipt.items), joinedload(PurchaseReceipt.supplier))
        .where(PurchaseReceipt.client_receipt_id == client_receipt_id)
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def get_receipt_by_id(
    db: Session, receipt_id: int, *, for_update: bool = False
) -> PurchaseReceipt | None:
    if for_update:
        pr = db.execute(
            select(PurchaseReceipt).where(PurchaseReceipt.id == receipt_id).with_for_update()
        ).scalar_one_or_none()
        if pr is None:
            return None
        _ = list(
            db.execute(
                select(PurchaseReceiptItem)
                .where(PurchaseReceiptItem.purchase_receipt_id == receipt_id)
                .order_by(PurchaseReceiptItem.id.asc())
                .with_for_update()
            ).scalars().all()
        )
        db.refresh(pr, attribute_names=["items", "supplier"])
        return pr

    stmt = (
        select(PurchaseReceipt)
        .options(joinedload(PurchaseReceipt.items), joinedload(PurchaseReceipt.supplier))
        .where(PurchaseReceipt.id == receipt_id)
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def list_purchase_receipts(
    db: Session,
    *,
    supplier_id: int | None = None,
    purchase_order_id: int | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
) -> list[PurchaseReceipt]:
    stmt = select(PurchaseReceipt).join(Supplier, PurchaseReceipt.supplier_id == Supplier.id)
    if supplier_id is not None:
        stmt = stmt.where(PurchaseReceipt.supplier_id == supplier_id)
    if purchase_order_id is not None:
        stmt = stmt.where(PurchaseReceipt.purchase_order_id == purchase_order_id)
    if status:
        stmt = stmt.where(PurchaseReceipt.status == status)
    if date_from is not None:
        stmt = stmt.where(PurchaseReceipt.receipt_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(PurchaseReceipt.receipt_date <= date_to)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                PurchaseReceipt.receipt_number.ilike(pattern),
                PurchaseReceipt.supplier_bill_ref.ilike(pattern),
                Supplier.name.ilike(pattern),
            )
        )
    stmt = stmt.options(
        joinedload(PurchaseReceipt.items), joinedload(PurchaseReceipt.supplier)
    ).order_by(PurchaseReceipt.receipt_date.desc(), PurchaseReceipt.id.desc())
    return list(db.execute(stmt).unique().scalars().all())


def get_supplier_stats_map(db: Session, supplier_ids: list[int]) -> dict[int, dict[str, int]]:
    if not supplier_ids:
        return {}
    po_rows = db.execute(
        select(PurchaseOrder.supplier_id, func.count(PurchaseOrder.id))
        .where(PurchaseOrder.supplier_id.in_(supplier_ids))
        .group_by(PurchaseOrder.supplier_id)
    ).all()
    pr_rows = db.execute(
        select(
            PurchaseReceipt.supplier_id,
            func.count(PurchaseReceipt.id),
            func.coalesce(func.sum(PurchaseReceipt.total_paisa), 0),
        )
        .where(
            PurchaseReceipt.supplier_id.in_(supplier_ids),
            PurchaseReceipt.status.in_(["POSTED", "RECEIVED", "CLOSED"]),
        )
        .group_by(PurchaseReceipt.supplier_id)
    ).all()

    result = {sid: {"po_count": 0, "receipt_count": 0, "total_purchased_paisa": 0} for sid in supplier_ids}
    for sid, cnt in po_rows:
        result[sid]["po_count"] = int(cnt)
    for sid, cnt, tot in pr_rows:
        result[sid]["receipt_count"] = int(cnt)
        result[sid]["total_purchased_paisa"] = int(tot)
    return result
