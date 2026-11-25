from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.modules.inventory import repository as inventory_repo
from app.modules.inventory.models import InventoryBalance, OpeningBalance, StockReservation


def _balance_snapshot(bal: InventoryBalance | None) -> dict[str, int]:
    if bal is None:
        return {"on_hand_pkts": 0, "reserved_pkts": 0, "available_pkts": 0}
    on_hand = int(bal.on_hand_qty_base)
    reserved = int(bal.reserved_qty_base)
    available = on_hand - reserved
    return {
        "on_hand_pkts": on_hand,
        "reserved_pkts": reserved,
        "available_pkts": available,
    }


def get_pack_size_availability_map(db: Session, pack_size_ids: list[int]) -> dict[int, dict[str, int]]:
    """Read-only availability summary per pack_size_id without mutating stock."""
    balances = inventory_repo.get_balances_by_pack_size_ids(db, pack_size_ids)
    return {sku_id: _balance_snapshot(balances.get(sku_id)) for sku_id in pack_size_ids}


def reserve_order_stock(
    db: Session,
    *,
    order_id: int,
    lines: list[dict],
    actor_user_id: int,
) -> tuple[list[StockReservation], dict[str, dict[str, int]], int, int]:
    """Atomically lock InventoryBalance rows in ascending ID order and reserve FG stock.

    `lines` is a list of dicts with keys:
      - `sales_order_item_id`: int
      - `pack_size_id`: int
      - `sku_code`: str
      - `display_name`: str
      - `qty_pkts`: int

    Raises ConflictError (`INSUFFICIENT_STOCK`) before any mutation if any SKU lacks coverage.
    """
    pack_ids = [line["pack_size_id"] for line in lines]
    locked_balances = inventory_repo.lock_balances_by_pack_size_ids(db, pack_ids)

    shortages: list[dict] = []
    stock_snapshot: dict[str, dict[str, int]] = {}
    ordered_total = 0
    available_total = 0

    for line in lines:
        ps_id = line["pack_size_id"]
        req_qty = int(line["qty_pkts"])
        bal = locked_balances.get(ps_id)
        snap = _balance_snapshot(bal)
        shortage_qty = max(0, req_qty - snap["available_pkts"])
        ordered_total += req_qty
        available_total += snap["available_pkts"]
        stock_snapshot[line["sku_code"]] = {
            "ordered_pkts": req_qty,
            "on_hand_pkts": snap["on_hand_pkts"],
            "reserved_pkts": snap["reserved_pkts"],
            "available_pkts": snap["available_pkts"],
            "shortage_pkts": shortage_qty,
        }
        if shortage_qty > 0:
            shortages.append(
                {
                    "pack_size_id": ps_id,
                    "sku_code": line["sku_code"],
                    "display_name": line["display_name"],
                    "requested_qty_pkts": req_qty,
                    "on_hand_qty_pkts": snap["on_hand_pkts"],
                    "reserved_qty_pkts": snap["reserved_pkts"],
                    "available_qty_pkts": snap["available_pkts"],
                    "shortage_pkts": shortage_qty,
                }
            )

    if shortages:
        summary = "; ".join(
            f"{s['display_name']}: requested {s['requested_qty_pkts']}, available {s['available_qty_pkts']} (short by {s['shortage_pkts']})"
            for s in shortages
        )
        raise ConflictError(
            f"Insufficient available finished-goods stock for approval ({summary}).",
            error_code="INSUFFICIENT_STOCK",
            details={
                "items": shortages,
                "stock_snapshot": stock_snapshot,
                "policy": (
                    "BR-AVL-02 / BR-AVL-03: Available stock = Physical On-Hand - Active Reservations. "
                    "Approval cannot exceed available stock or drive stock negative. "
                    "Reduce approved quantity, mark Under Review awaiting production, request correction, or reject order."
                ),
            },
        )

    now_utc = datetime.now(UTC)
    created_reservations: list[StockReservation] = []
    for line in lines:
        req_qty = int(line["qty_pkts"])
        bal = locked_balances[line["pack_size_id"]]
        bal.reserved_qty_base = (
            Decimal(bal.reserved_qty_base) + Decimal(req_qty)
        ).quantize(Decimal("0.001"))

        res = StockReservation(
            sales_order_id=order_id,
            sales_order_item_id=line["sales_order_item_id"],
            pack_size_id=line["pack_size_id"],
            reserved_qty_pkts=req_qty,
            status="ACTIVE",
            reserved_by=actor_user_id,
            reserved_at=now_utc,
        )
        db.add(res)
        created_reservations.append(res)

    db.flush()
    return created_reservations, stock_snapshot, ordered_total, available_total


def release_order_reservations(
    db: Session,
    *,
    order_id: int,
    actor_user_id: int,
    reason: str,
) -> list[tuple[StockReservation, InventoryBalance]]:
    """Release all ACTIVE stock reservations for a cancelled pre-invoice order atomically."""
    active_rows = inventory_repo.list_active_reservations_for_order_for_update(db, order_id)
    if not active_rows:
        return []

    locked_balances = inventory_repo.lock_balances_by_pack_size_ids(
        db, [r.pack_size_id for r in active_rows]
    )
    now_utc = datetime.now(UTC)
    released_pairs: list[tuple[StockReservation, InventoryBalance]] = []

    for res in active_rows:
        bal = locked_balances[res.pack_size_id]
        bal.reserved_qty_base = max(
            Decimal("0.000"),
            (Decimal(bal.reserved_qty_base) - Decimal(res.reserved_qty_pkts)).quantize(Decimal("0.001")),
        )
        res.status = "RELEASED"
        res.released_by = actor_user_id
        res.released_at = now_utc
        res.release_reason = reason
        released_pairs.append((res, bal))

    db.flush()
    return released_pairs


def list_reservations_for_order(db: Session, order_id: int) -> list[StockReservation]:
    return inventory_repo.list_reservations_for_order(db, order_id)


def seed_opening_finished_goods(
    db: Session,
    *,
    batch_ref: str,
    pack_size_id: int,
    opening_qty_pkts: int,
    unit_cost_paisa: int,
    as_of_date: date,
    created_by: int,
) -> OpeningBalance:
    """Create opening FG stock via ledger movement; DB trigger updates inventory_balances."""
    return inventory_repo.create_opening_fg_ledger_entry(
        db,
        batch_ref=batch_ref,
        pack_size_id=pack_size_id,
        opening_qty_pkts=opening_qty_pkts,
        unit_cost_paisa=unit_cost_paisa,
        as_of_date=as_of_date,
        created_by=created_by,
    )
