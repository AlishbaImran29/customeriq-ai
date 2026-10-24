"""Shapes for the order-status part of the Auto Messenger (camelCase)."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.imports import CamelModel
from app.schemas.messaging import MessageOut

OrderStatus = Literal["confirmed", "dispatched", "in_transit", "out_for_delivery", "delivered", "returned"]


class SeedIn(CamelModel):
    groups: list[Literal["orders", "followups", "journeys"]] | None = None


class SeedOut(CamelModel):
    added: int


class OrderRowOut(CamelModel):
    id: int
    order_number: str
    customer_id: int
    customer_name: str
    phone: str | None
    amount: float
    payment_type: str | None
    products: str | None
    status: OrderStatus | None         # None = no status recorded yet
    status_at: datetime | None
    messages: int                      # how many messages this order has caused


class StatusIn(CamelModel):
    status: OrderStatus
    courier: str | None = Field(default=None, max_length=60)
    tracking_number: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=200)
    notify: bool = True                # False = record it without messaging the customer


class StatusEventOut(CamelModel):
    status: OrderStatus
    at: datetime
    source: str
    courier: str | None
    tracking_number: str | None
    note: str | None


class StatusResultOut(CamelModel):
    recorded: bool
    announced: bool                    # the move was news and fresh, so the customer message was attempted
    reason: str | None                 # same_status / not_forward / too_old / not_requested
    messages: list[MessageOut]


class TimelineOut(CamelModel):
    order_number: str
    customer_name: str
    events: list[StatusEventOut]
    messages: list[MessageOut]
