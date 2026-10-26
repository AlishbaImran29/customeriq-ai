"""Email Automations (signed-in): the overview, the shop's look, COD emails, win-back, new-product drafts, test mode."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import CatalogProduct, CodEmail, Customer, EmailAnnouncement, EmailLog, Order
from app.schemas.imports import CamelModel
from app.services.email_auto import render as r
from app.services.email_auto import service as svc
from app.services.order_status import order_number

router = APIRouter(prefix="/email-auto", tags=["email-automations"])


class SettingsIn(CamelModel):
    store_name: str | None = Field(None, max_length=80)
    logo_url: str | None = Field(None, max_length=400)
    brand_color: str | None = Field(None, max_length=7)
    support_email: str | None = Field(None, max_length=320)
    store_url: str | None = Field(None, max_length=300)


class WinbackIn(CamelModel):
    discount_code: str | None = Field(None, max_length=30)
    discount_value: str | None = Field(None, max_length=20)


class AnnounceIn(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    category: str | None = Field(None, max_length=100)
    price: float | None = Field(None, ge=0)
    description: str | None = Field(None, max_length=1500)
    image_url: str | None = Field(None, max_length=500)
    product_url: str | None = Field(None, max_length=500)


def _settings_out(db: Session, settings: Settings) -> dict:
    row = svc.get_settings_row(db)
    shown = svc.look(db, settings)
    return {"storeName": row.store_name or "", "logoUrl": row.logo_url or "", "brandColor": row.brand_color or "", "supportEmail": row.support_email or "", "storeUrl": row.store_url or "",
            "effective": {"storeName": shown["store_name"], "brandColor": shown["brand_color"], "supportEmail": shown["support_email"]}}


@router.get("/overview", summary="Everything the Email Automations page shows")
def overview(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    cod = []
    for row, order, customer in db.execute(select(CodEmail, Order, Customer).join(Order, Order.id == CodEmail.order_id).join(Customer, Customer.id == Order.customer_id).order_by(CodEmail.created_at.desc()).limit(100)):
        cod.append({"orderId": order.id, "orderNumber": order_number(order), "customerName": " ".join(p for p in (customer.first_name, customer.last_name) if p) or customer.external_id,
                    "email": customer.email, "amount": float(order.order_value), "status": row.status, "sentAt": row.sent_at, "reminderSentAt": row.reminder_sent_at, "answeredAt": row.answered_at})
    drafts = []
    for ann, product in db.execute(select(EmailAnnouncement, CatalogProduct).join(CatalogProduct, CatalogProduct.id == EmailAnnouncement.product_id).order_by(EmailAnnouncement.id.desc()).limit(20)):
        drafts.append({"id": ann.id, "productName": product.name, "category": product.category, "status": ann.status, "sentCount": ann.sent_count})
    state = func.coalesce(Customer.lifecycle, "unknown")
    lifecycle = {k: int(n) for k, n in db.execute(select(state, func.count()).group_by(state))}
    return {
        "sentToday": svc.sent_today(db), "dailyLimit": svc.DAILY_LIMIT, "marketingCap": svc.MARKETING_CAP,
        "testMode": not svc.brevo_ready(settings), "senderEmail": settings.sender_email,
        "linksReady": bool(settings.messaging_secret and settings.public_api_url),
        "cod": cod, "announcements": drafts, "lifecycle": lifecycle, "settings": _settings_out(db, settings),
    }


@router.put("/settings", summary="How the shop looks in emails")
def save_settings(body: SettingsIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    row = svc.get_settings_row(db)
    color = (body.brand_color or "").strip()
    if color and r.clean_color(color) != color:
        raise ApiError(422, "invalid_color", "The brand colour must look like #2563eb.")
    for url in (body.logo_url, body.store_url):
        if (url or "").strip() and not r.clean_url(url):
            raise ApiError(422, "invalid_url", "Web addresses must start with http:// or https://.")
    row.store_name, row.logo_url, row.brand_color = (body.store_name or "").strip() or None, (body.logo_url or "").strip() or None, color or None
    row.support_email, row.store_url = (body.support_email or "").strip() or None, (body.store_url or "").strip() or None
    db.commit()
    return _settings_out(db, settings)


@router.get("/previews", summary="Every template filled with sample data")
def previews(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> list[dict]:
    out = []
    for key, label in r.TEMPLATES.items():
        subject, html, text = r.render(key, {**r.sample_data(key), **svc.look(db, settings)})
        out.append({"key": key, "label": label, "subject": subject, "html": html, "text": text})
    return out


@router.post("/cod/{order_id}/send", summary="Send (or re-send as a reminder) the COD confirmation email for one order")
def send_cod(order_id: int, reminder: bool = False, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    order = db.get(Order, order_id)
    if order is None or order.payment_type != "cod":
        raise ApiError(404, "not_cod_order", "This is not a cash-on-delivery order.")
    row = svc.send_cod_email(db, settings, order, reminder=reminder)
    if row is None:
        raise ApiError(409, "no_email_address", "This customer has no email address, so nothing was sent.")
    db.commit()
    return {"status": row.status, "testMode": not svc.brevo_ready(settings)}


def _bulk(result: svc.BulkResult, settings: Settings) -> dict:
    return {"sent": result.sent, "failed": result.failed, "skipped": result.skipped, "remaining": result.remaining, "message": result.message, "testMode": not svc.brevo_ready(settings)}


@router.post("/lifecycle/refresh", summary="Mark customers at_risk (60+ days) or lost (180+ days)")
def refresh(db: Session = Depends(get_db)) -> dict:
    counts = svc.refresh_lifecycle(db)
    db.commit()
    return counts


@router.post("/winback/send", summary="Send win-back emails to at-risk and lost customers")
def send_winback(body: WinbackIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    result = svc.send_winback(db, settings, body.discount_code, body.discount_value)
    db.commit()
    return _bulk(result, settings)


@router.post("/announcements", summary="Make a draft announcement for a new product")
def announce(body: AnnounceIn, db: Session = Depends(get_db)) -> dict:
    ann = svc.create_announcement(db, name=body.name, category=body.category, price=body.price, description=body.description, image_url=body.image_url, product_url=body.product_url)
    db.commit()
    return {"id": ann.id}


@router.get("/announcements/{ann_id}/preview", summary="How the announcement looks, and who will get it")
def announcement_preview(ann_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    ann = db.get(EmailAnnouncement, ann_id)
    if ann is None:
        raise ApiError(404, "not_found", "That announcement does not exist.")
    customers, buyers, left_out = svc.audience(db, ann)
    sample = customers[0] if customers else None
    mail = svc.build_announcement(db, settings, ann, sample, bool(sample and sample.id in buyers), "https://example.com/unsubscribe")
    return {"id": ann.id, "status": ann.status, "subject": mail.subject, "html": mail.html, "text": mail.text,
            "audience": {"sameCategory": sum(1 for c in customers if c.id in buyers), "others": sum(1 for c in customers if c.id not in buyers), "leftOut": left_out}}


@router.post("/announcements/{ann_id}/send", summary="Send the announcement (same-category buyers first)")
def send_announcement(ann_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    ann = db.get(EmailAnnouncement, ann_id)
    if ann is None:
        raise ApiError(404, "not_found", "That announcement does not exist.")
    result = svc.send_announcement(db, settings, ann)
    db.commit()
    return _bulk(result, settings)


@router.post("/mock/load", summary="Test mode: add five sample customers, their orders and products")
def mock_load(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    out = svc.load_sample_data(db, settings)
    svc.refresh_lifecycle(db)
    sample = db.scalar(select(Order).where(Order.external_id == "MOCK-O1"))
    if sample is not None:
        svc.on_new_cod_order(db, settings, sample)          # the sample COD order gets its confirmation email, like a real new order
    db.commit()
    return out


@router.post("/test-send", summary="Send one test email of every template to SENDER_EMAIL")
def test_send(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    mails = svc.send_test_emails(settings, db)
    db.commit()
    return {"results": [{"subject": m.subject, "status": m.result, "error": m.error} for m in mails], "testMode": not svc.brevo_ready(settings)}


@router.get("/log", summary="The latest emails sent")
def log(db: Session = Depends(get_db)) -> list[dict]:
    return [{"to": e.to_email, "kind": e.kind, "subject": e.subject, "status": e.status, "error": e.error, "at": e.created_at}
            for e in db.scalars(select(EmailLog).order_by(EmailLog.id.desc()).limit(50))]
