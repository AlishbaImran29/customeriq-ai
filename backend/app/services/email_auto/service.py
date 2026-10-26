"""Email Automations: COD confirmation emails, win-back emails and new-product emails through Brevo.

RULES (all enforced here, not in the page)
- Marketing emails (win-back, new product) go only to customers who agreed to email and never to anyone who unsubscribed,
  and always carry an unsubscribe link. Without MESSAGING_SECRET and PUBLIC_API_URL no marketing email is sent.
- Brevo's free plan allows 300 emails a day. COD emails are sent first: marketing stops at MARKETING_CAP, which keeps
  the rest of the day for COD confirmations.
- A customer gets at most one win-back email every 30 days, and one email per announcement.
- Without BREVO_API_KEY nothing leaves the server: the email is rendered and logged as "mock" (test mode).
"""

import base64
import hashlib
import hmac
import json
import logging
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import CatalogProduct, CodEmail, Customer, EmailAnnouncement, EmailLog, EmailSettings, Order
from app.services.email_auto import render as r
from app.services.mailer import BREVO_URL
from app.services.messaging import consent as consent_service
from app.services.messaging.tokens import unsubscribe_link
from app.services.order_status import order_number

logger = logging.getLogger(__name__)

DAILY_LIMIT = 300                 # Brevo free plan
MARKETING_CAP = 270               # marketing stops here; the last 30 are kept for COD emails
BATCH = 100                       # emails per button press, so one request stays short
WINBACK_GAP_DAYS = 30
AT_RISK_DAYS, LOST_DAYS = 60, 180
COD_LINK_DAYS = 7
REMINDER_AFTER_HOURS = 24
_CODE = re.compile(r"^[A-Za-z0-9_-]{1,30}$")


# --- the shop's look ----------------------------------------------------------------------------------------------------


def get_settings_row(db: Session) -> EmailSettings:
    row = db.get(EmailSettings, 1)
    if row is None:
        row = EmailSettings(id=1)
        db.add(row)
        db.flush()
    return row


def look(db: Session, settings: Settings) -> dict:
    """store_name, store_logo_url, brand_color, support_email, store_url with safe defaults."""
    row = get_settings_row(db)
    return {
        "store_name": (row.store_name or settings.sender_name or "Our Store").strip(),
        "store_logo_url": r.clean_url(row.logo_url),
        "brand_color": r.clean_color(row.brand_color),
        "support_email": (row.support_email or settings.sender_email or None),
        "store_url": r.clean_url(row.store_url) or r.clean_url(settings.app_url) or "#",
    }


# --- sending ------------------------------------------------------------------------------------------------------------


def brevo_ready(settings: Settings) -> bool:
    return bool(settings.brevo_api_key and settings.brevo_api_key.get_secret_value().strip() and (settings.sender_email or settings.mail_from))


def _sender(settings: Settings) -> tuple[str, str]:
    return (settings.sender_name or "CustomerIQ"), (settings.sender_email or settings.mail_from or "")


def _brevo_send(settings: Settings, to: str, subject: str, html: str, text: str, headers: dict[str, str] | None, reply_to: str | None) -> None:
    name, email = _sender(settings)
    body = {"sender": {"name": name, "email": email}, "to": [{"email": to}], "subject": subject, "htmlContent": html, "textContent": text}
    if headers:
        body["headers"] = headers
    if reply_to:
        body["replyTo"] = {"email": reply_to}
    request = urllib.request.Request(
        BREVO_URL, data=json.dumps(body).encode(), method="POST",
        headers={"api-key": settings.brevo_api_key.get_secret_value(), "content-type": "application/json", "accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 (fixed https URL)
        response.read()


def _failure(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return {401: "Brevo refused the API key", 403: "Brevo refused the API key", 400: "Brevo refused the message (is SENDER_EMAIL verified in Brevo?)", 402: "Brevo plan limit", 429: "Brevo daily limit reached"}.get(exc.code, f"Brevo error {exc.code}")
    return "Could not reach Brevo"


@dataclass
class Outgoing:
    customer_id: int | None
    to: str
    kind: str
    subject: str
    html: str
    text: str
    ref_id: int | None = None
    headers: dict[str, str] | None = None
    result: str = ""                  # "sent", "mock" or "failed"
    error: str | None = None


def sent_today(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(db.scalar(select(func.count()).select_from(EmailLog).where(EmailLog.created_at >= start, EmailLog.status.in_(("sent", "mock")))) or 0)


def deliver(db: Session, settings: Settings, mails: list[Outgoing], now: datetime | None = None) -> list[Outgoing]:
    """Send (or, in test mode, only log) each email and write the log. Commits nothing. Never raises for a failed email."""
    now = now or datetime.now(timezone.utc)
    live = brevo_ready(settings)
    support = (settings.sender_email or None)

    def one(mail: Outgoing) -> Outgoing:
        if not live:
            mail.result = "mock"
            return mail
        try:
            _brevo_send(settings, mail.to, mail.subject, mail.html, mail.text, mail.headers, support)
            mail.result = "sent"
        except Exception as exc:  # noqa: BLE001 (one bad address must not stop the rest)
            mail.result, mail.error = "failed", _failure(exc)
            logger.warning("Email failed (%s): %s", mail.kind, type(exc).__name__)
        return mail

    if live and len(mails) > 1:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(one, mails))
    else:
        for mail in mails:
            one(mail)
    for mail in mails:
        db.add(EmailLog(customer_id=mail.customer_id, to_email=mail.to[:320], kind=mail.kind, subject=mail.subject[:300], status=mail.result, error=mail.error, ref_id=mail.ref_id, created_at=now))
    db.flush()
    return mails


def _marketing_headers(url: str) -> dict[str, str]:
    return {"List-Unsubscribe": f"<{url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}


def _need_unsubscribe_support(settings: Settings) -> None:
    if unsubscribe_link(settings, 0) is None:
        raise ApiError(503, "unsubscribe_not_configured", "Marketing emails need an unsubscribe link. Set MESSAGING_SECRET and PUBLIC_API_URL on the server first.")


# --- customer data for personalising ----------------------------------------------------------------------------------


def _can_market(db: Session, customer: Customer) -> bool:
    return bool(customer.email) and customer.status == "active" and consent_service.consent_state(db, customer.id, "email") == "opted_in"


def _last_order(db: Session, customer_id: int) -> Order | None:
    return db.scalar(select(Order).where(Order.customer_id == customer_id).order_by(Order.order_date.desc(), Order.id.desc()).limit(1))


def _product_names(order: Order | None) -> list[str]:
    return [p.strip() for p in (order.products or "").split(",") if p.strip()] if order else []


def _catalog_card(p: CatalogProduct, look_: dict) -> dict:
    return {"name": p.name, "price": r.price(p.price), "image": r.clean_url(p.image_url), "url": r.clean_url(p.product_url) or (look_["store_url"] if look_["store_url"] != "#" else None)}


def recommended(db: Session, customer_id: int, look_: dict, exclude: str | None = None, limit: int = 3) -> list[dict]:
    """Up to 3 products from the categories this customer bought before; the newest products if there are none."""
    categories = {c.lower() for c in db.scalars(select(Order.product_category).where(Order.customer_id == customer_id, Order.product_category.is_not(None)).distinct()) if c}
    newest = list(db.scalars(select(CatalogProduct).order_by(CatalogProduct.created_at.desc(), CatalogProduct.id.desc()).limit(60)))
    pool = [p for p in newest if (p.name or "").lower() != (exclude or "").lower()]
    same = [p for p in pool if (p.category or "").lower() in categories]
    chosen = (same + [p for p in pool if p not in same])[:limit] if same else pool[:limit]
    return [_catalog_card(p, look_) for p in chosen]


def order_items(db: Session, order: Order) -> list[dict]:
    names = _product_names(order)
    items = []
    for name in names:
        p = db.scalar(select(CatalogProduct).where(func.lower(CatalogProduct.name) == name.lower()).limit(1))
        qty = order.item_count if len(names) == 1 and order.item_count else None
        items.append({"name": name, "quantity": qty, "price": r.price(p.price) if p and p.price is not None else None, "image": r.clean_url(p.image_url) if p else None})
    return items


# --- COD confirmation ---------------------------------------------------------------------------------------------------


def _secret(settings: Settings) -> bytes:
    if not settings.messaging_secret or not settings.messaging_secret.get_secret_value().strip():
        raise ApiError(503, "secret_not_configured", "Set MESSAGING_SECRET on the server first: it signs the confirm and cancel links.")
    return settings.messaging_secret.get_secret_value().encode()


def make_cod_token(settings: Settings, order_id: int, action: str, now: datetime | None = None) -> str:
    expires = int(((now or datetime.now(timezone.utc)) + timedelta(days=COD_LINK_DAYS)).timestamp())
    body = f"cod.{order_id}.{action}.{expires}"
    sig = hmac.new(_secret(settings), body.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{body}.{sig}".encode()).decode().rstrip("=")


def read_cod_token(settings: Settings, token: str, now: datetime | None = None) -> tuple[int, str] | None:
    """(order id, "confirm" | "cancel") for a genuine link that has not expired, else None."""
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        tag, order_id, action, expires, sig = raw.split(".")
        order_id, expires = int(order_id), int(expires)
        expected = hmac.new(_secret(settings), f"{tag}.{order_id}.{action}.{expires}".encode(), hashlib.sha256).hexdigest()[:32]
    except (ValueError, UnicodeDecodeError, ApiError):
        return None
    if tag != "cod" or action not in ("confirm", "cancel") or not hmac.compare_digest(sig, expected):
        return None
    if (now or datetime.now(timezone.utc)).timestamp() > expires:
        return None
    return order_id, action


def _cod_url(settings: Settings, order_id: int, action: str) -> str:
    base = (settings.public_api_url or "").rstrip("/")
    if not base:
        raise ApiError(503, "public_url_not_configured", "Set PUBLIC_API_URL on the server first: the confirm and cancel links point to it.")
    return f"{base}/api/v1/email/cod/{make_cod_token(settings, order_id, action)}"


def cod_email_for(db: Session, order_id: int) -> CodEmail | None:
    return db.scalar(select(CodEmail).where(CodEmail.order_id == order_id))


def build_cod(db: Session, settings: Settings, order: Order, customer: Customer, reminder: bool) -> Outgoing:
    look_ = look(db, settings)
    data = {
        **look_, "first_name": r.first_name(customer.first_name), "order_number": order_number(order), "items": order_items(db, order),
        "order_total": r.price(order.order_value), "delivery_city": (order.city or "").strip() or None,
        "confirm_url": _cod_url(settings, order.id, "confirm"), "cancel_url": _cod_url(settings, order.id, "cancel"),
    }
    template = "cod_reminder" if reminder else "cod_confirmation"
    subject, html, text = r.render(template, data)
    return Outgoing(customer.id, customer.email or "", "cod_reminder" if reminder else "cod", subject, html, text, ref_id=order.id)


def send_cod_email(db: Session, settings: Settings, order: Order, reminder: bool = False, now: datetime | None = None) -> CodEmail | None:
    """The COD confirmation (or reminder) email for one order. None when nothing can be sent (not COD, no email address).
    Commits nothing."""
    now = now or datetime.now(timezone.utc)
    customer = db.get(Customer, order.customer_id)
    if order.payment_type != "cod" or customer is None or not customer.email or customer.status != "active":
        return None
    row = cod_email_for(db, order.id)
    if row is not None and (row.status != "pending" or (not reminder and row.sent_at) or (reminder and row.reminder_sent_at)):
        return row                                   # already asked, answered, or reminded: never twice
    if sent_today(db, now) >= DAILY_LIMIT:
        raise ApiError(429, "daily_limit", f"The daily limit of {DAILY_LIMIT} emails is reached. Try again tomorrow.")
    mail = deliver(db, settings, [build_cod(db, settings, order, customer, reminder)], now)[0]
    if mail.result == "failed":
        raise ApiError(503, "email_send_failed", mail.error or "The email could not be sent.")
    if row is None:
        row = CodEmail(order_id=order.id, status="pending")
        db.add(row)
    if reminder:
        row.reminder_sent_at = now
    else:
        row.sent_at = now
    db.flush()
    return row


def on_new_cod_order(db: Session, settings: Settings, order: Order) -> None:
    """Called when an order is created. Never fails the order: a problem is logged and the order goes on."""
    try:
        with db.begin_nested():
            send_cod_email(db, settings, order)
    except Exception:  # noqa: BLE001
        logger.exception("COD email for order %s was not sent", order.id)


def send_due_reminders(db: Session, settings: Settings, now: datetime | None = None, limit: int = 50) -> dict[str, int]:
    """Orders that got the email more than 24 hours ago and still have no answer get one reminder. Safe to run again."""
    now = now or datetime.now(timezone.utc)
    due = list(db.scalars(select(CodEmail).where(CodEmail.status == "pending", CodEmail.reminder_sent_at.is_(None), CodEmail.sent_at <= now - timedelta(hours=REMINDER_AFTER_HOURS)).limit(limit)))
    sent = 0
    for row in due:
        order = db.get(Order, row.order_id)
        try:
            with db.begin_nested():
                if order is not None and send_cod_email(db, settings, order, reminder=True, now=now) is not None:
                    sent += 1
        except ApiError as exc:
            if exc.code == "daily_limit":
                break
    return {"reminders": sent}


def answer_cod(db: Session, order_id: int, action: str, now: datetime | None = None) -> CodEmail:
    """The customer pressed the button. Only the first answer counts. Cancelling gives the reserved stock back."""
    from app.services.messaging import cod_confirm

    now = now or datetime.now(timezone.utc)
    row = cod_email_for(db, order_id)
    if row is None:
        row = CodEmail(order_id=order_id, status="pending")
        db.add(row)
        db.flush()
    if row.status != "pending":
        return row
    row.status, row.answered_at = ("confirmed" if action == "confirm" else "cancelled"), now
    cod_confirm.resolve(db, order_id, row.status, now)     # the COD board, stock and order risk follow the answer
    db.flush()
    return row


# --- win-back -----------------------------------------------------------------------------------------------------------


def refresh_lifecycle(db: Session, today: date | None = None) -> dict[str, int]:
    """at_risk = no order for 60+ days, lost = 180+ days (from the last order date). Customers with no order are left alone."""
    today = today or date.today()
    counts = {"active": 0, "at_risk": 0, "lost": 0}
    for customer, last in db.execute(select(Customer, func.max(Order.order_date)).join(Order, Order.customer_id == Customer.id).group_by(Customer.id)):
        days = (today - last).days
        state = "lost" if days >= LOST_DAYS else "at_risk" if days >= AT_RISK_DAYS else "active"
        customer.lifecycle = state
        counts[state] += 1
    db.flush()
    return counts


def clean_discount(code: str | None, value: str | None) -> tuple[str | None, str | None]:
    code = (code or "").strip()
    if not code:
        return None, None
    if not _CODE.match(code):
        raise ApiError(422, "invalid_discount_code", "The discount code can use letters, numbers, - and _ only (up to 30 characters).")
    value = " ".join((value or "").split())[:20] or None
    return code.upper(), value


@dataclass
class BulkResult:
    sent: int = 0
    failed: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    remaining: int = 0
    message: str | None = None


def _room(db: Session, now: datetime) -> int:
    return max(0, MARKETING_CAP - sent_today(db, now))


def build_winback(db: Session, settings: Settings, customer: Customer, code: str | None, value: str | None, today: date | None = None) -> Outgoing:
    look_ = look(db, settings)
    last = _last_order(db, customer.id)
    names = _product_names(last)
    url = unsubscribe_link(settings, customer.id)
    if url is None:
        raise ApiError(503, "unsubscribe_not_configured", "Set MESSAGING_SECRET and PUBLIC_API_URL on the server first.")
    data = {
        **look_, "first_name": r.first_name(customer.first_name), "last_product_name": names[0] if names else None,
        "days_since_last_order": (((today or date.today()) - last.order_date).days if last else None),
        "recommended_products": recommended(db, customer.id, look_, exclude=names[0] if names else None),
        "discount_code": code, "discount_value": value, "unsubscribe_url": url,
    }
    subject, html, text = r.render("winback", data)
    return Outgoing(customer.id, customer.email or "", "winback", subject, html, text, headers=_marketing_headers(url))


def send_winback(db: Session, settings: Settings, code: str | None = None, value: str | None = None, now: datetime | None = None, limit: int = BATCH) -> BulkResult:
    """Win-back emails to at-risk and lost customers. Commits nothing."""
    now = now or datetime.now(timezone.utc)
    _need_unsubscribe_support(settings)
    code, value = clean_discount(code, value)
    refresh_lifecycle(db, now.date())
    recent = {cid for cid in db.scalars(select(EmailLog.customer_id).where(EmailLog.kind == "winback", EmailLog.status.in_(("sent", "mock")), EmailLog.created_at >= now - timedelta(days=WINBACK_GAP_DAYS))) if cid}
    result = BulkResult()
    room = _room(db, now)
    if room <= 0:
        result.message = f"The daily email limit is reached ({sent_today(db, now)} of {DAILY_LIMIT} today; the last {DAILY_LIMIT - MARKETING_CAP} are kept for COD emails). Marketing emails were skipped. Try again tomorrow."
        return result
    todo, skipped = [], {"sent in the last 30 days": 0, "no consent or unsubscribed": 0}
    for customer in db.scalars(select(Customer).where(Customer.lifecycle.in_(("at_risk", "lost")), Customer.email.is_not(None)).order_by(Customer.id)):
        if customer.id in recent:
            skipped["sent in the last 30 days"] += 1
        elif not _can_market(db, customer):
            skipped["no consent or unsubscribed"] += 1
        else:
            todo.append(customer)
    take = todo[: min(limit, room)]
    result.remaining = len(todo) - len(take)
    for mail in deliver(db, settings, [build_winback(db, settings, c, code, value, now.date()) for c in take], now):
        result.sent += mail.result != "failed"
        result.failed += mail.result == "failed"
    result.skipped = {k: v for k, v in skipped.items() if v}
    if result.remaining and len(take) == room:
        result.message = "The daily email limit was reached. The rest can be sent tomorrow."
    return result


# --- new product --------------------------------------------------------------------------------------------------------


def create_announcement(db: Session, *, name: str, category: str | None, price, description: str | None, image_url: str | None, product_url: str | None, external_id: str | None = None, source: str = "manual") -> EmailAnnouncement:
    """Save the product and make its DRAFT email. Nothing is sent."""
    name = " ".join((name or "").split())[:120]
    if not name:
        raise ApiError(422, "name_required", "Give the product a name.")
    product = CatalogProduct(name=name, category=(category or "").strip()[:100] or None, price=price, description=(description or "").strip() or None, source=source, external_id=external_id, image_url=r.clean_url(image_url), product_url=r.clean_url(product_url))
    db.add(product)
    db.flush()
    return draft_for(db, product)


def draft_for(db: Session, product: CatalogProduct) -> EmailAnnouncement:
    known = db.scalar(select(EmailAnnouncement).where(EmailAnnouncement.product_id == product.id).limit(1))
    if known is not None:
        return known
    ann = EmailAnnouncement(product_id=product.id, status="draft")
    db.add(ann)
    db.flush()
    return ann


def _buyer_ids(db: Session, category: str | None) -> set[int]:
    if not category:
        return set()
    return set(db.scalars(select(Order.customer_id).where(func.lower(Order.product_category) == category.lower()).distinct()))


def build_announcement(db: Session, settings: Settings, ann: EmailAnnouncement, customer: Customer | None, same_category: bool, unsubscribe_url: str | None) -> Outgoing:
    product = db.get(CatalogProduct, ann.product_id)
    look_ = look(db, settings)
    data = {
        **look_, "first_name": r.first_name(customer.first_name if customer else "Ayesha"), "product_name": product.name, "product_price": r.price(product.price),
        "product_image": r.clean_url(product.image_url), "product_url": r.clean_url(product.product_url) or look_["store_url"],
        "product_description": r.short(product.description), "same_category": same_category, "unsubscribe_url": unsubscribe_url,
    }
    subject, html, text = r.render("new_product", data)
    return Outgoing(customer.id if customer else None, (customer.email if customer else "") or "", "new_product", subject, html, text, ref_id=ann.id, headers=_marketing_headers(unsubscribe_url) if unsubscribe_url else None)


def audience(db: Session, ann: EmailAnnouncement) -> tuple[list[Customer], set[int], int]:
    """(customers still to email, ids of those who bought from the same category, how many were left out)."""
    product = db.get(CatalogProduct, ann.product_id)
    done = {cid for cid in db.scalars(select(EmailLog.customer_id).where(EmailLog.kind == "new_product", EmailLog.ref_id == ann.id, EmailLog.status.in_(("sent", "mock")))) if cid}
    buyers = _buyer_ids(db, product.category)
    eligible, left_out = [], 0
    for customer in db.scalars(select(Customer).where(Customer.email.is_not(None)).order_by(Customer.id)):
        if customer.id in done:
            continue
        if _can_market(db, customer):
            eligible.append(customer)
        else:
            left_out += 1
    eligible.sort(key=lambda c: (c.id not in buyers, c.id))          # same-category buyers first
    return eligible, buyers, left_out


def send_announcement(db: Session, settings: Settings, ann: EmailAnnouncement, now: datetime | None = None, limit: int = BATCH) -> BulkResult:
    """Send the draft: same-category buyers first, then the rest. Press again to continue if there are more. Commits nothing."""
    now = now or datetime.now(timezone.utc)
    _need_unsubscribe_support(settings)
    result = BulkResult()
    customers, buyers, left_out = audience(db, ann)
    if left_out:
        result.skipped["no consent or unsubscribed"] = left_out
    room = _room(db, now)
    if room <= 0 and customers:
        result.remaining = len(customers)
        result.message = f"The daily email limit is reached ({sent_today(db, now)} of {DAILY_LIMIT} today). Marketing emails were skipped. Try again tomorrow."
        return result
    take = customers[: min(limit, room)]
    result.remaining = len(customers) - len(take)
    mails = [build_announcement(db, settings, ann, c, c.id in buyers, unsubscribe_link(settings, c.id)) for c in take]
    for mail in deliver(db, settings, mails, now):
        result.sent += mail.result != "failed"
        result.failed += mail.result == "failed"
    ann.sent_count += result.sent
    if result.remaining == 0:
        ann.status, ann.sent_at = "sent", now
    elif len(take) == room:
        result.message = "The daily email limit was reached. The rest can be sent tomorrow."
    db.flush()
    return result


# --- test mode: sample customers, and a test email of every template ---------------------------------------------------


def load_sample_data(db: Session, settings: Settings, today: date | None = None) -> dict[str, int]:
    """Five sample customers (two at risk, one lost), their orders, four products and one COD order. Safe to press twice.
    Emails go to SENDER_EMAIL (plus-addressing) when it is set, so tests land in your own inbox."""
    today = today or date.today()
    local, _, domain = (settings.sender_email or "").partition("@")
    people = [("Ayesha", "khan", 5), ("bilal", "AHMED", 75), ("SANA", "malik", 90), ("usman", "Ali", 220), ("Zara", "Sheikh", 300)]
    products = [("Everyday Sneakers", "Shoes", 6200), ("Classic Leather Wallet", "Accessories", 2500), ("Canvas Weekender Bag", "Bags", 4800), ("Leather Belt", "Accessories", 1800)]
    created = 0
    for name, category, cost in products:
        if db.scalar(select(CatalogProduct.id).where(CatalogProduct.external_id == f"MOCK-{name}")) is None:
            db.add(CatalogProduct(name=name, category=category, price=cost, source="manual", external_id=f"MOCK-{name}", image_url=f"https://placehold.co/160x160/e2e8f0/475569?text={category}", product_url=r.clean_url(settings.app_url)))
            created += 1
    for n, (first, last, age) in enumerate(people, start=1):
        email = f"{local}+mock{n}@{domain}" if local and domain else f"mock{n}@example.com"
        customer = db.scalar(select(Customer).where(Customer.external_id == f"MOCK-C{n}"))
        if customer is None:
            customer = Customer(external_id=f"MOCK-C{n}", first_name=first, last_name=last, email=email, country="Pakistan")
            db.add(customer)
            db.flush()
            consent_service.set_consent(db, customer.id, "email", True, "manual", note="Sample customer (test mode)")
            created += 1
        if db.scalar(select(Order.id).where(Order.external_id == f"MOCK-O{n}")) is None:
            product = products[n % len(products)]
            db.add(Order(external_id=f"MOCK-O{n}", customer_id=customer.id, order_date=today - timedelta(days=age), order_value=product[2], product_category=product[1], products=product[0], payment_type="cod" if n == 1 else "prepaid", city="Lahore", item_count=1, source="mock"))
    db.flush()
    return {"created": created}


def send_test_emails(settings: Settings, db: Session | None = None) -> list[Outgoing]:
    """One email of every template, with sample data, to SENDER_EMAIL. Needs no customers."""
    if not settings.sender_email:
        raise ApiError(422, "sender_not_configured", "Set SENDER_EMAIL first.")
    mails = []
    for key in r.TEMPLATES:
        data = {**r.sample_data(key), "store_name": settings.sender_name or "Sample Store"}
        subject, html, text = r.render(key, data)
        mails.append(Outgoing(None, settings.sender_email, "test", f"[Test] {subject}", html, text))
    if db is not None:
        return deliver(db, settings, mails)
    for mail in mails:                                           # the script path: no database needed
        if brevo_ready(settings):
            try:
                _brevo_send(settings, mail.to, mail.subject, mail.html, mail.text, None, None)
                mail.result = "sent"
            except Exception as exc:  # noqa: BLE001
                mail.result, mail.error = "failed", _failure(exc)
        else:
            mail.result = "mock"
    return mails
