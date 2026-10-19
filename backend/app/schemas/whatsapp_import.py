"""Response and request shapes for the WhatsApp chat import (camelCase, matching frontend/lib/api/whatsapp.ts)."""

from datetime import date, datetime
from typing import Any

from app.schemas.imports import CamelModel


class ChatSenderOut(CamelModel):
    name: str
    messages: int


class ChatMessageOut(CamelModel):
    sender: str
    time: datetime
    text: str


class CandidateOut(CamelModel):
    """One possible order found in the chat. It is only a suggestion: the seller reviews it."""

    id: int
    customer_name: str
    phone: str | None                  # +923XXXXXXXXX
    city: str | None
    amount: float | None
    other_amounts: list[float]         # other amounts seen in the same conversation
    payment_type: str | None           # "cod" | "prepaid" | None (the chat does not say)
    order_date: date
    order_time: datetime               # when the first message of the order was sent
    confidence: str                    # "high" | "medium" | "low"
    confidence_label: str              # what was found, e.g. "Amount and phone found"
    found: dict[str, bool]
    messages: list[ChatMessageOut]     # the original messages, for the review screen only


class ChatParseOut(CamelModel):
    date_order: str                    # "dmy" | "mdy" | "ymd"
    date_order_ambiguous: bool         # every date fits day-first and month-first: ask the seller
    senders: list[ChatSenderOut]
    me: str | None                     # the seller's own name, when chosen (and found in the chat)
    customer_name_hint: str | None
    message_count: int
    system_lines: int
    media_messages: int
    unreadable_lines: int
    candidates: list[CandidateOut]
    truncated: bool                    # more candidates were found than are shown


class WhatsAppOrderIn(CamelModel):
    """An accepted order. Loosely typed on purpose: services/quick_order.py checks every field."""

    customer_name: Any = None
    phone: Any = None
    city: Any = None
    products: Any = None
    amount: Any = None
    payment_type: Any = None
    order_date: Any = None
    message_time: Any = None


class WhatsAppSaveIn(CamelModel):
    orders: list[WhatsAppOrderIn]


class WhatsAppSaveOut(CamelModel):
    saved: int
    already_imported: int
    new_customers: int


class WhatsAppSummaryOut(CamelModel):
    orders: int
    customers: int


class WhatsAppDeleteOut(CamelModel):
    orders_deleted: int
    customers_deleted: int
