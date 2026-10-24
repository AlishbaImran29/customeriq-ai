"""Simple inventory endpoints: stock items, counting the shelf, and what each order did to the stock."""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.models import Order
from app.models.inventory import StockItem, StockMovement
from app.schemas.imports import CamelModel
from app.services import inventory as inv

router = APIRouter(prefix="/inventory", tags=["inventory"])


class ItemOut(CamelModel):
    id: int
    sku: str
    name: str
    category: str | None
    cost_price: Decimal | None
    selling_price: Decimal | None
    stock: int
    reserved: int
    available: int
    reorder_threshold: int
    supplier: str | None
    status: str
    low: bool


class ItemIn(CamelModel):
    sku: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=100)
    cost_price: Decimal | None = Field(default=None, ge=0, le=Decimal("9999999.99"))
    selling_price: Decimal | None = Field(default=None, ge=0, le=Decimal("9999999.99"))
    stock: int = Field(default=0, ge=0, le=1_000_000)
    reorder_threshold: int = Field(default=0, ge=0, le=1_000_000)
    supplier: str | None = Field(default=None, max_length=120)


class ItemPatch(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=100)
    cost_price: Decimal | None = Field(default=None, ge=0, le=Decimal("9999999.99"))
    selling_price: Decimal | None = Field(default=None, ge=0, le=Decimal("9999999.99"))
    reorder_threshold: int | None = Field(default=None, ge=0, le=1_000_000)
    supplier: str | None = Field(default=None, max_length=120)
    status: str | None = Field(default=None, pattern="^(active|archived)$")


class AdjustIn(CamelModel):
    delta: int = Field(ge=-100_000, le=100_000)
    kind: str = Field(default="adjustment", pattern="^(receive|adjustment)$")
    note: str | None = Field(default=None, max_length=300)


class MovementOut(CamelModel):
    id: int
    kind: str
    quantity: int
    stock_delta: int
    reserved_delta: int
    order_id: int | None
    note: str | None
    at: datetime


class EffectOut(CamelModel):
    sku: str
    kind: str
    quantity: int
    applied: bool
    short_by: int


def _out(item: StockItem) -> ItemOut:
    return ItemOut(
        id=item.id, sku=item.sku, name=item.name, category=item.category, cost_price=item.cost_price, selling_price=item.selling_price,
        stock=item.stock, reserved=item.reserved, available=inv.available(item), reorder_threshold=item.reorder_threshold,
        supplier=item.supplier, status=item.status, low=inv.is_low(item),
    )


def _get(db: Session, item_id: int) -> StockItem:
    item = db.get(StockItem, item_id)
    if item is None:
        raise ApiError(404, "item_not_found", "No such stock item.")
    return item


@router.get("/items", response_model=list[ItemOut], summary="Stock items (low ones first)")
def list_items(low_only: bool = Query(False, alias="lowOnly"), db: Session = Depends(get_db)) -> list[ItemOut]:
    items = [_out(i) for i in db.scalars(select(StockItem).order_by(StockItem.name))]
    items = [i for i in items if i.low] if low_only else items
    return sorted(items, key=lambda i: (not i.low, i.name.lower()))


@router.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED, summary="Add a stock item")
def add_item(body: ItemIn, db: Session = Depends(get_db)) -> ItemOut:
    sku = body.sku.strip().upper()
    if db.scalar(select(StockItem.id).where(func.upper(StockItem.sku) == sku)) is not None:
        raise ApiError(409, "sku_exists", "That SKU is already used.")
    item = StockItem(
        sku=sku, name=body.name.strip(), category=body.category, cost_price=body.cost_price, selling_price=body.selling_price,
        stock=0, reorder_threshold=body.reorder_threshold, supplier=body.supplier,
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "sku_exists", "That SKU is already used.") from None
    if body.stock:
        inv.adjust(db, item.id, body.stock, "receive", "Opening stock")
    db.commit()
    db.refresh(item)
    return _out(item)


@router.patch("/items/{item_id}", response_model=ItemOut, summary="Change a stock item (not the counts: use adjust)")
def change_item(item_id: int, body: ItemPatch, db: Session = Depends(get_db)) -> ItemOut:
    item = _get(db, item_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "name" and value is None:
            continue
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return _out(item)


@router.post("/items/{item_id}/adjust", response_model=ItemOut, summary="Receive goods or correct the count")
def adjust_item(item_id: int, body: AdjustIn, db: Session = Depends(get_db)) -> ItemOut:
    _get(db, item_id)
    item = inv.adjust(db, item_id, body.delta, body.kind, body.note)
    db.commit()
    db.refresh(item)
    return _out(item)


@router.get("/items/{item_id}/movements", response_model=list[MovementOut], summary="Every change to one item, newest first")
def movements(item_id: int, db: Session = Depends(get_db)) -> list[StockMovement]:
    _get(db, item_id)
    return list(db.scalars(select(StockMovement).where(StockMovement.item_id == item_id).order_by(StockMovement.id.desc()).limit(200)))


def _order(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise ApiError(404, "order_not_found", "No such order.")
    return order


def _effects(rows: list[inv.Effect]) -> list[EffectOut]:
    return [EffectOut(sku=e.sku, kind=e.kind, quantity=e.quantity, applied=e.applied, short_by=e.short_by) for e in rows]


@router.post("/orders/{order_id}/release", response_model=list[EffectOut], summary="The order was cancelled or refused: give its reservation back")
def release(order_id: int, db: Session = Depends(get_db)) -> list[EffectOut]:
    effects = inv.release_order(db, _order(db, order_id))
    db.commit()
    return _effects(effects)


@router.post("/orders/{order_id}/restock", response_model=list[EffectOut], summary="The order came back and the goods are fine: put them back on the shelf")
def restock(order_id: int, db: Session = Depends(get_db)) -> list[EffectOut]:
    effects = inv.restock_order(db, _order(db, order_id), "Returned order restocked")
    db.commit()
    return _effects(effects)
