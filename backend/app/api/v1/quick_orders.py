"""Quick Order Entry endpoints: add one order by hand, and look a customer up by phone number."""

import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import Order
from app.schemas.quick_order import CustomerLookupOut, QuickOrderIn, QuickOrderOut
from app.services.phone import normalise_pk_phone
from app.services.quick_order import check_quick_order, create_quick_order, find_customer

router = APIRouter(tags=["quick-orders"])


@router.get("/customers/lookup", response_model=CustomerLookupOut, summary="Is this phone number a returning customer?")
def lookup_customer(phone: str = Query(max_length=40), db: Session = Depends(get_db)) -> CustomerLookupOut:
    """Used while the seller types a phone number. A number that is not (yet) a Pakistani mobile
    number is not an error here: the answer is just `valid: false`."""
    number = normalise_pk_phone(phone)
    if number is None:
        return CustomerLookupOut(valid=False, phone=None, found=False, name=None, orders=0, last_order_date=None, last_city=None)
    customer = find_customer(db, number)
    if customer is None:
        return CustomerLookupOut(valid=True, phone=number, found=False, name=None, orders=0, last_order_date=None, last_city=None)
    orders = db.scalar(select(func.count()).select_from(Order).where(Order.customer_id == customer.id)) or 0
    last = db.execute(
        select(Order.order_date, Order.city)
        .where(Order.customer_id == customer.id)
        .order_by(Order.order_date.desc(), Order.id.desc())
        .limit(1)
    ).first()
    last_city = db.scalar(
        select(Order.city)
        .where(Order.customer_id == customer.id, Order.city.is_not(None))
        .order_by(Order.order_date.desc(), Order.id.desc())
        .limit(1)
    )
    return CustomerLookupOut(
        valid=True, phone=number, found=True, name=customer.first_name, orders=int(orders),
        last_order_date=last[0] if last else None, last_city=last_city,
    )


@router.post("/orders", response_model=QuickOrderOut, status_code=status.HTTP_201_CREATED, summary="Add one order by hand")
def add_order(body: QuickOrderIn, db: Session = Depends(get_db)) -> QuickOrderOut:
    """Check the order, find the customer by phone number (or create them), and save it.

    Every problem is returned at once as `details.fields` (field name -> message); nothing is saved."""
    clean, errors = check_quick_order(body.model_dump(by_alias=True))
    if clean is None:
        raise ApiError(422, "invalid_order", "Some fields need attention.", {"fields": errors})
    result = create_quick_order(db, clean)
    _after_order_added(db, result, body.whatsapp_ok is True)
    return QuickOrderOut(
        order_id=result.order_id, customer_id=result.customer_id, customer_name=result.customer_name,
        phone=result.phone, returning=result.returning, customer_orders=result.customer_orders,
    )


def _after_order_added(db: Session, result, whatsapp_ok: bool) -> None:
    """Auto Messenger: remember the customer's consent if the seller ticked the box, and start the order's status
    history at "confirmed" (which sends the confirmation when the customer agreed). Never allowed to fail the order."""
    from app.services import order_status
    from app.services.messaging import consent

    try:
        customer = find_customer(db, result.phone)
        order = db.scalar(select(Order).where(Order.external_id == result.order_id))
        if customer is not None and whatsapp_ok:
            consent.set_consent(db, customer.id, "whatsapp", True, "add_order", note="The seller ticked: customer agreed to WhatsApp order updates")
        if order is not None:
            order_status.record_status(db, get_settings(), order, "confirmed", source="manual")
        db.commit()
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("Could not record the consent or status of a new order")
        db.rollback()
