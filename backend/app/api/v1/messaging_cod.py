"""COD auto-confirmation: who was asked, who answered, who needs a phone call."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import Customer, Order
from app.models.cod_confirmation import CodConfirmation
from app.schemas.imports import CamelModel
from app.services import order_status
from app.services.messaging import cod_confirm

router = APIRouter(prefix="/messaging/cod", tags=["messaging"])


class CodRowOut(CamelModel):
    order_id: int
    order_number: str
    customer_name: str
    phone: str | None
    amount: float
    state: Literal["awaiting", "confirmed", "cancelled", "needs_call"]
    resolved_by: Literal["customer", "seller"] | None
    reply_text: str | None
    asked_at: datetime
    deadline_at: datetime
    answered_at: datetime | None


class ResolveIn(CamelModel):
    result: Literal["confirmed", "cancelled"]


def _row(c: CodConfirmation, order: Order, customer: Customer | None) -> CodRowOut:
    name = " ".join(p for p in (customer.first_name, customer.last_name) if p) if customer else ""
    return CodRowOut(
        order_id=order.id, order_number=order_status.order_number(order), customer_name=name or (customer.external_id if customer else "?"),
        phone=customer.phone if customer else None, amount=float(order.order_value), state=c.state, resolved_by=c.resolved_by,  # type: ignore[arg-type]
        reply_text=c.reply_text, asked_at=c.asked_at, deadline_at=c.deadline_at, answered_at=c.answered_at,
    )


@router.get("", response_model=list[CodRowOut], summary="COD orders that were asked to confirm (the ones needing a call first)")
def list_cod(state: Literal["awaiting", "confirmed", "cancelled", "needs_call"] | None = Query(None), db: Session = Depends(get_db)) -> list[CodRowOut]:
    query = select(CodConfirmation, Order, Customer).join(Order, Order.id == CodConfirmation.order_id).join(Customer, Customer.id == Order.customer_id)
    if state:
        query = query.where(CodConfirmation.state == state)
    rank = {"needs_call": 0, "awaiting": 1, "cancelled": 2, "confirmed": 3}
    rows = [_row(c, o, cu) for c, o, cu in db.execute(query.order_by(CodConfirmation.asked_at.desc()).limit(300))]
    return sorted(rows, key=lambda r: rank[r.state])


@router.post("/{order_id}/ask", response_model=CodRowOut, summary="Ask the customer to confirm this COD order now")
def ask(order_id: int, db: Session = Depends(get_db)) -> CodRowOut:
    order = db.get(Order, order_id)
    if order is None or order.payment_type != "cod":
        raise ApiError(404, "not_cod_order", "This is not a cash-on-delivery order.")
    confirmation = cod_confirm.ask(db, get_settings(), order)
    if confirmation is None:
        existing = cod_confirm.get(db, order_id)
        if existing is None:
            raise ApiError(409, "cannot_ask", "Nobody was asked. Check that the customer agreed to WhatsApp and that an approved cod_confirmation template exists.")
        confirmation = existing
    db.commit()
    return _row(confirmation, order, db.get(Customer, order.customer_id))


@router.post("/{order_id}/resolve", response_model=CodRowOut, summary="Record the result of your phone call")
def resolve(order_id: int, body: ResolveIn, db: Session = Depends(get_db)) -> CodRowOut:
    confirmation = cod_confirm.resolve(db, order_id, body.result)
    db.commit()
    order = db.get(Order, order_id)
    assert order is not None
    return _row(confirmation, order, db.get(Customer, order.customer_id))
