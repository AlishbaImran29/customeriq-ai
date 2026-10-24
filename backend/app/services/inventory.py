"""Simple inventory: what is on the shelf, what is promised, and an audit trail of every change.

THE RULES (all keyed so that the same order event can never change the stock twice)
- An order is CONFIRMED  -> its items are RESERVED   (reserved goes up; stock is unchanged).
- An order is DISPATCHED -> its items are SOLD       (stock goes down; the reservation, if any, is released).
- An order is cancelled or refused -> the seller presses "release" and the reservation is given back.
- An order is RETURNED   -> the seller presses "restock" if the goods are fine to sell again.
Nothing is restocked by itself: a returned parcel may be damaged.

WHICH ITEMS AN ORDER HAS. Orders keep their products as text ("Lip balm, Hair oil x2"). Each part is matched to a stock item by
SKU or by name (not case sensitive); "x2" or "2x" means two units, otherwise one. Parts that match no stock item are ignored
(the seller does not have to count everything).

Only FRESH statuses change the stock (at most 3 days old), so importing an old courier file does not subtract last
year's parcels from today's shelf count.
"""

import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import Order
from app.models.inventory import StockItem, StockMovement

_QTY_AFTER = re.compile(r"^(.*?)\s*[x×*]\s*(\d{1,3})$", re.IGNORECASE)
_QTY_BEFORE = re.compile(r"^(\d{1,3})\s*[x×*]\s*(.+)$", re.IGNORECASE)
MAX_QTY = 999


@dataclass
class Effect:
    item_id: int
    sku: str
    kind: str
    quantity: int
    applied: bool          # False when the same event had already been applied
    short_by: int = 0      # reserve/sale only: how many units were missing from the shelf


def parse_lines(text: str | None) -> list[tuple[str, int]]:
    """"Lip balm, Hair oil x2" -> [("Lip balm", 1), ("Hair oil", 2)]."""
    lines: list[tuple[str, int]] = []
    for part in re.split(r"[,\n;]", text or ""):
        part = part.strip()
        if not part:
            continue
        qty = 1
        after, before = _QTY_AFTER.match(part), _QTY_BEFORE.match(part)
        if after and after.group(1).strip():
            part, qty = after.group(1).strip(), int(after.group(2))
        elif before:
            part, qty = before.group(2).strip(), int(before.group(1))
        lines.append((part, max(1, min(qty, MAX_QTY))))
    return lines


def order_items(db: Session, order: Order) -> dict[int, int]:
    """{stock item id: units} for the items of an order that the seller counts."""
    items = list(db.scalars(select(StockItem).where(StockItem.status == "active")))
    by_key: dict[str, StockItem] = {}
    for item in items:
        by_key[item.sku.lower()] = item
        by_key.setdefault(item.name.lower(), item)
    wanted: Counter[int] = Counter()
    for name, qty in parse_lines(order.products):
        item = by_key.get(name.lower())
        if item is not None:
            wanted[item.id] += qty
    return dict(wanted)


def _locked(db: Session, item_id: int) -> StockItem:
    # FOR UPDATE: two requests for the same item (two webhooks at once) take turns instead of overwriting each other.
    item = db.scalar(select(StockItem).where(StockItem.id == item_id).with_for_update())
    if item is None:
        raise ApiError(404, "item_not_found", "No such stock item.")
    return item


def _seen(db: Session, key: str) -> StockMovement | None:
    return db.scalar(select(StockMovement).where(StockMovement.idempotency_key == key))


def _move(db: Session, item: StockItem, kind: str, quantity: int, stock_delta: int, reserved_delta: int, *, order_id: int | None = None, key: str | None = None, note: str | None = None) -> StockMovement:
    item.stock += stock_delta
    item.reserved = max(0, item.reserved + reserved_delta)
    movement = StockMovement(item_id=item.id, kind=kind, quantity=quantity, stock_delta=stock_delta, reserved_delta=reserved_delta, order_id=order_id, idempotency_key=key, note=note)
    db.add(movement)
    db.flush()
    return movement


def _holds_reservation(db: Session, order_id: int, item_id: int) -> bool:
    """Did this order reserve this item and not yet sold or released it?"""
    return _seen(db, f"order:{order_id}:{item_id}:reserve") is not None and _seen(db, f"order:{order_id}:{item_id}:sale") is None and _seen(db, f"order:{order_id}:{item_id}:release") is None


def reserve_order(db: Session, order: Order) -> list[Effect]:
    effects = []
    for item_id, qty in order_items(db, order).items():
        item = _locked(db, item_id)
        key = f"order:{order.id}:{item_id}:reserve"
        if _seen(db, key) is not None:
            effects.append(Effect(item_id, item.sku, "reserve", qty, False))
            continue
        short = max(0, qty - (item.stock - item.reserved))
        _move(db, item, "reserve", qty, 0, qty, order_id=order.id, key=key)
        effects.append(Effect(item_id, item.sku, "reserve", qty, True, short))
    return effects


def sell_order(db: Session, order: Order) -> list[Effect]:
    effects = []
    for item_id, qty in order_items(db, order).items():
        item = _locked(db, item_id)
        key = f"order:{order.id}:{item_id}:sale"
        if _seen(db, key) is not None:
            effects.append(Effect(item_id, item.sku, "sale", qty, False))
            continue
        release = -qty if _holds_reservation(db, order.id, item_id) else 0
        short = max(0, qty - item.stock)
        _move(db, item, "sale", qty, -qty, release, order_id=order.id, key=key)
        effects.append(Effect(item_id, item.sku, "sale", qty, True, short))
    return effects


def release_order(db: Session, order: Order) -> list[Effect]:
    """Give back what a cancelled or refused order had reserved. Does nothing for an order already sold."""
    effects = []
    for item_id, qty in order_items(db, order).items():
        item = _locked(db, item_id)
        if not _holds_reservation(db, order.id, item_id):
            continue
        _move(db, item, "release", qty, 0, -qty, order_id=order.id, key=f"order:{order.id}:{item_id}:release")
        effects.append(Effect(item_id, item.sku, "release", qty, True))
    return effects


def restock_order(db: Session, order: Order, note: str | None = None) -> list[Effect]:
    """A returned order's goods are put back on the shelf. Only items that were really sold by this order come back."""
    effects = []
    for item_id, qty in order_items(db, order).items():
        item = _locked(db, item_id)
        if _seen(db, f"order:{order.id}:{item_id}:sale") is None:
            continue
        key = f"order:{order.id}:{item_id}:return"
        if _seen(db, key) is not None:
            effects.append(Effect(item_id, item.sku, "return", qty, False))
            continue
        _move(db, item, "return", qty, qty, 0, order_id=order.id, key=key, note=note)
        effects.append(Effect(item_id, item.sku, "return", qty, True))
    return effects


def on_status(db: Session, order: Order, status: str) -> list[Effect]:
    """The hook the order-status code calls (fresh statuses only). Confirmed reserves; dispatched and later sell."""
    if status == "confirmed":
        return reserve_order(db, order)
    if status in ("dispatched", "in_transit", "out_for_delivery", "delivered"):
        return sell_order(db, order)
    return []


def adjust(db: Session, item_id: int, delta: int, kind: str, note: str | None) -> StockItem:
    """Count the shelf: `receive` (new goods in, delta > 0) or `adjustment` (a correction; delta can be negative)."""
    if kind not in ("receive", "adjustment"):
        raise ApiError(422, "invalid_kind", "Use receive or adjustment.")
    if delta == 0 or abs(delta) > 100_000:
        raise ApiError(422, "invalid_quantity", "The change must be a whole number other than zero.")
    if kind == "receive" and delta < 0:
        raise ApiError(422, "invalid_quantity", "Goods received must be a positive number. Use an adjustment to take stock away.")
    item = _locked(db, item_id)
    _move(db, item, kind, abs(delta), delta, 0, note=(note or None) and note[:300])
    return item


def available(item: StockItem) -> int:
    return item.stock - item.reserved


def is_low(item: StockItem) -> bool:
    return item.status == "active" and available(item) <= item.reorder_threshold
