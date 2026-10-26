"""PUBLIC pages behind the buttons in the COD confirmation email.

No sign-in (a customer has none). The link carries a signed token (order id, which button, expiry) that cannot be made without
MESSAGING_SECRET. Opening the link only SHOWS the order: a mail app that previews links changes nothing. The order status
changes when the customer presses the button on that page, which is a POST.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import Customer, Order
from app.services.email_auto import render as r
from app.services.email_auto import service as svc
from app.services.order_status import order_number

router = APIRouter(prefix="/email/cod", tags=["email"])


def _page(db: Session, settings: Settings, state: str, order: Order | None = None, action: str = "confirm") -> HTMLResponse:
    customer = db.get(Customer, order.customer_id) if order else None
    data = {
        **svc.look(db, settings), "state": state, "action": action, "first_name": r.first_name(customer.first_name if customer else None),
        "order_number": order_number(order) if order else None, "items": svc.order_items(db, order) if order else [],
        "order_total": r.price(order.order_value) if order else None, "delivery_city": ((order.city or "").strip() or None) if order else None,
    }
    html = r._html_env.get_template("page_cod.html").render({**r.DEFAULTS, **{k: v for k, v in data.items() if v is not None}, "subject": "Your order"})
    return HTMLResponse(html, status_code=400 if state == "invalid" else 200, headers={"Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex"})


@router.get("/{token}", response_class=HTMLResponse, summary="The page a COD email button opens (shows the order, changes nothing)")
def show(token: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    parsed = svc.read_cod_token(settings, token)
    order = db.get(Order, parsed[0]) if parsed else None
    if parsed is None or order is None:
        return _page(db, settings, "invalid")
    row = svc.cod_email_for(db, order.id)
    if row is not None and row.status != "pending":
        return _page(db, settings, row.status, order)          # already answered: show that answer, offer no button
    return _page(db, settings, "ask", order, parsed[1])


@router.post("/{token}", response_class=HTMLResponse, summary="The button on that page: confirm or cancel the order")
def press(token: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    parsed = svc.read_cod_token(settings, token)
    order = db.get(Order, parsed[0]) if parsed else None
    if parsed is None or order is None:
        return _page(db, settings, "invalid")
    row = svc.answer_cod(db, order.id, parsed[1])
    db.commit()
    return _page(db, settings, row.status, order)
