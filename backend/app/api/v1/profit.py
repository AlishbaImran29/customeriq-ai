"""Profit analytics: real profit per order, the other money numbers, the shop's cost settings and ad spend."""

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.models.profit import AdSpend
from app.schemas.imports import CamelModel
from app.services import data_rules, profit_analytics as pa

router = APIRouter(prefix="/profit", tags=["profit"])

Channel = Literal["instagram", "whatsapp", "facebook", "website", "other"]
MAX_DAYS = 366


class GroupOut(CamelModel):
    key: str
    orders: int
    revenue: float
    profit: float
    enough: bool
    margin: float | None
    profit_per_order: float | None
    return_rate: float | None


class SettingsOut(CamelModel):
    packing_cost: float | None
    return_shipping_cost: float | None


class SettingsIn(CamelModel):
    packing_cost: Decimal | None = Field(default=None, ge=0, le=Decimal("99999"))
    return_shipping_cost: Decimal | None = Field(default=None, ge=0, le=Decimal("99999"))


class AdSpendIn(CamelModel):
    spend_date: date
    channel: Channel
    amount: Decimal = Field(ge=0, le=Decimal("99999999"))
    campaign: str | None = Field(default=None, max_length=160)


class AdSpendOut(CamelModel):
    id: int
    spend_date: date
    channel: str
    campaign: str | None
    amount: float
    source: str


def _g(rows) -> list[GroupOut]:
    return [GroupOut(key=g.key, orders=g.orders, revenue=float(g.revenue), profit=float(g.profit), enough=g.enough, margin=g.margin, profit_per_order=g.profit_per_order, return_rate=g.return_rate) for g in rows]


@router.get("/summary", summary="Money numbers for a period (Asia/Karachi days), with every definition")
def summary(start: date | None = Query(None), end: date | None = Query(None), db: Session = Depends(get_db)) -> dict[str, Any]:
    default_start, default_end = pa.default_range()
    start, end = start or default_start, end or default_end
    if end < start:
        raise ApiError(422, "invalid_range", "The end date is before the start date.")
    if (end - start).days >= MAX_DAYS:
        raise ApiError(422, "range_too_long", "Choose at most one year.")
    a = pa.analyze(db, start, end)
    return {
        "start": a.start, "end": a.end, "minGroupCount": data_rules.MIN_GROUP_COUNT,
        "orders": {"placed": a.placed, "ended": a.ended, "pending": a.pending, "counted": a.counted, "costUnknown": a.cost_unknown},
        "money": {
            "grossRevenue": float(a.gross_revenue), "deliveredRevenue": float(a.delivered_revenue), "prepaidCollected": float(a.prepaid_collected),
            "adSpend": float(a.ad_spend), "estimatedProfit": float(a.profit) if a.counted else None,
        },
        "rates": {"returnRate": a.return_rate, "failedDeliveryRate": a.failed_delivery_rate, "repeatPurchaseRate": a.repeat_purchase_rate},
        "lowStockItems": a.low_stock,
        "missing": a.missing, "packingSet": a.packing_set, "returnShippingSet": a.return_shipping_set,
        "revenueByChannel": {k: float(v) for k, v in a.revenue_by_channel.items()},
        "groups": {"channel": _g(a.by_channel), "city": _g(a.by_city), "courier": _g(a.by_courier), "product": _g(a.by_product), "customer": _g(a.by_customer)},
        "definitions": pa.DEFINITIONS,
        "note": "Profit is an estimate: ad cost is shared over a channel's orders, and orders whose product cost you have not entered are left out.",
    }


@router.get("/settings", response_model=SettingsOut, summary="The shop's packing and return-shipping costs")
def get_settings(db: Session = Depends(get_db)) -> SettingsOut:
    row = pa.get_settings(db)
    db.commit()
    return SettingsOut(packing_cost=float(row.packing_cost) if row.packing_cost is not None else None, return_shipping_cost=float(row.return_shipping_cost) if row.return_shipping_cost is not None else None)


@router.put("/settings", response_model=SettingsOut, summary="Change them (owner only)")
def put_settings(body: SettingsIn, db: Session = Depends(get_db)) -> SettingsOut:
    row = pa.get_settings(db)
    row.packing_cost, row.return_shipping_cost = body.packing_cost, body.return_shipping_cost
    db.commit()
    return SettingsOut(packing_cost=float(row.packing_cost) if row.packing_cost is not None else None, return_shipping_cost=float(row.return_shipping_cost) if row.return_shipping_cost is not None else None)


@router.get("/ad-spend", response_model=list[AdSpendOut], summary="Ad spend entries, newest first")
def list_spend(db: Session = Depends(get_db)) -> list[AdSpend]:
    return list(db.scalars(select(AdSpend).order_by(AdSpend.spend_date.desc(), AdSpend.id.desc()).limit(300)))


@router.post("/ad-spend", response_model=AdSpendOut, status_code=status.HTTP_201_CREATED, summary="Add what you spent on ads one day")
def add_spend(body: AdSpendIn, db: Session = Depends(get_db)) -> AdSpend:
    row = AdSpend(spend_date=body.spend_date, channel=body.channel, amount=body.amount, campaign=(body.campaign or "").strip() or None, source="manual")
    db.add(row)
    db.commit()
    return row


@router.delete("/ad-spend/{spend_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove an entry (owner only)")
def delete_spend(spend_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(AdSpend, spend_id)
    if row is None:
        raise ApiError(404, "spend_not_found", "No such entry.")
    db.delete(row)
    db.commit()
