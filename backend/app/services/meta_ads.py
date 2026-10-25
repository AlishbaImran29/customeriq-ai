"""Meta Ads: audiences, delivered-only purchase events, ad spend, and true ROAS. Official APIs only, never scraping.

TEST MODE (META_ADS_DRY_RUN, ON by default): everything is prepared exactly as for Meta, hashes included, but NOTHING is sent. Turn it
off only after the Meta Business account, app, access token, ad account id, pixel id and the Custom Audience Terms are in place.

PRIVACY. Meta needs customer details to build an audience or match a purchase. They are sent only as SHA-256 hashes of the lower-cased
email or the digits of the phone number (as Meta requires), and ONLY for customers who agreed to be contacted on WhatsApp or email.
A customer who never agreed is not sent: they are "skipped" in the log.

DELIVERED-ONLY PURCHASES. A Purchase event is queued when a COD order is DELIVERED, not when it is placed, so Meta learns from customers who
really paid. The event id is "purchase-<order id>": unique here (an order is never sent twice) and used by Meta to de-duplicate.
"""

import csv
import hashlib
import io
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import Customer, Order
from app.models.meta_event import MetaEvent
from app.models.profit import AdSpend
from app.services import data_rules, profit_analytics
from app.services.channels import normalise_channel
from app.services.messaging import consent
from app.services.phone import normalise_pk_phone

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com"
TIMEOUT_SECONDS = 15
AUDIENCE_BATCH = 10_000
MAX_ATTEMPTS = 4
SEGMENTS = {"champions": "Champions (for lookalikes)", "lost": "Lost customers (to win back)", "buyers": "All buyers (to exclude from prospecting)"}
MAX_CSV_BYTES = 1_000_000
MAX_CSV_ROWS = 2_000


# --- hashing, the way Meta asks for it ---------------------------------------------------------------------------------------


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_email(email: str | None) -> str | None:
    address = (email or "").strip().lower()
    return _sha(address) if "@" in address and " " not in address else None


def hash_phone(phone: str | None) -> str | None:
    """Digits only, with the country code and no "+" or leading zeros: +92 300 1234567 -> 923001234567."""
    number = normalise_pk_phone(phone) if phone else None
    return _sha(number.lstrip("+")) if number else None


def agreed(db: Session, customer_id: int) -> bool:
    return any(consent.consent_state(db, customer_id, c) == "opted_in" for c in ("whatsapp", "email"))


def configured(settings: Settings) -> dict[str, bool]:
    token = bool(settings.meta_ads_access_token and settings.meta_ads_access_token.get_secret_value().strip())
    return {"accessToken": token, "adAccountId": bool(settings.meta_ad_account_id), "pixelId": bool(settings.meta_pixel_id)}


def _token(settings: Settings) -> str:
    token = settings.meta_ads_access_token.get_secret_value().strip() if settings.meta_ads_access_token else ""
    if not token:
        raise ApiError(503, "meta_not_configured", "Meta Ads is not connected. Add META_ADS_ACCESS_TOKEN (and the ad account / pixel id) to the backend settings.")
    return token


def _call(settings: Settings, method: str, path: str, params: dict[str, str]) -> dict:
    """One call to the Graph API. Meta's own error text is turned into a clear message; the token is never logged."""
    params = {**params, "access_token": _token(settings)}
    url = f"{GRAPH_URL}/{settings.whatsapp_api_version}/{path}"
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    request = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:         # noqa: S310 (a Meta address)
            return json.loads(response.read(1_000_000) or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            error = json.loads(exc.read(20_000)).get("error", {})
        except (ValueError, OSError):
            error = {}
        code, message = error.get("code"), str(error.get("message") or "Meta refused the request.")[:200]
        if code in (2663, 2664) or "terms" in message.lower():
            message = "Meta says the Custom Audience Terms have not been accepted for this ad account. Accept them in Meta Business Manager first."
        elif code in (190, 102):
            message = "The Meta access token is not valid or has expired."
        logger.warning("Meta call %s failed with code %s", path.split("/")[-1], code)
        raise ApiError(502, "meta_error", message, {"code": code}) from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise ApiError(502, "meta_unreachable", "Meta did not answer. Please try again in a few minutes.") from exc


# --- custom audiences ----------------------------------------------------------------------------------------------------------


def audience_rows(db: Session, segment: str) -> tuple[list[list[str]], int]:
    """([[email_hash, phone_hash], ...], customers left out because they never agreed or have no usable contact)."""
    if segment not in SEGMENTS:
        raise ApiError(422, "invalid_segment", "Choose champions, lost or buyers.")
    if segment == "buyers":
        ids = list(db.scalars(select(Order.customer_id).distinct()))
    else:
        from app.services.messaging import campaigns

        wanted = campaigns.SEGMENT_KEYS["Champions" if segment == "champions" else "Lost Customers"]
        ids = [cid for cid, key in campaigns.segment_by_customer(db).items() if key == wanted]
    rows, left_out = [], 0
    for start in range(0, len(ids), 1000):
        for customer in db.scalars(select(Customer).where(Customer.id.in_(ids[start:start + 1000]), Customer.status == "active")):
            email, phone = hash_email(customer.email), hash_phone(customer.phone)
            if not agreed(db, customer.id) or (email is None and phone is None):
                left_out += 1
                continue
            rows.append([email or "", phone or ""])
    return rows, left_out


def user_payload(rows: list[list[str]]) -> dict:
    return {"schema": ["EMAIL_SHA256", "PHONE_SHA256"], "data": rows}


def push_audience(db: Session, settings: Settings, segment: str, name: str) -> dict:
    rows, left_out = audience_rows(db, segment)
    result = {"segment": segment, "customers": len(rows), "leftOut": left_out, "dryRun": settings.meta_ads_dry_run, "audienceId": None, "sample": [[h[:10] + "…" if h else "" for h in r] for r in rows[:2]]}
    if not rows:
        raise ApiError(409, "empty_audience", "No customer in this group agreed to be contacted and has a usable email or phone, so there is nothing to send.", result)
    if settings.meta_ads_dry_run:
        return result                                         # test mode: prepared, not sent
    if not settings.meta_ad_account_id:
        raise ApiError(503, "meta_not_configured", "Add META_AD_ACCOUNT_ID to the backend settings.")
    created = _call(settings, "POST", f"act_{settings.meta_ad_account_id}/customaudiences", {
        "name": name[:100] or f"CustomerIQ {segment}", "subtype": "CUSTOM", "description": "Created by CustomerIQ AI from customers who agreed to be contacted", "customer_file_source": "USER_PROVIDED_ONLY",
    })
    audience_id = str(created.get("id") or "")
    if not audience_id:
        raise ApiError(502, "meta_error", "Meta did not return an audience id.")
    for start in range(0, len(rows), AUDIENCE_BATCH):
        _call(settings, "POST", f"{audience_id}/users", {"payload": json.dumps(user_payload(rows[start:start + AUDIENCE_BATCH]))})
    result["audienceId"] = audience_id
    return result


# --- purchase events (delivered only) ---------------------------------------------------------------------------------------------


def queue_purchase(db: Session, order: Order, when: datetime | None = None) -> MetaEvent | None:
    """Record that a Purchase event is due for this DELIVERED order. Once per order, however many times it is called."""
    event_id = f"purchase-{order.id}"
    existing = db.scalar(select(MetaEvent).where(MetaEvent.event_id == event_id))
    if existing is not None:
        return existing
    event = MetaEvent(order_id=order.id, event_id=event_id, status="pending", event_time=when or datetime.now(timezone.utc))
    db.add(event)
    db.flush()
    return event


def build_event(db: Session, event: MetaEvent, order: Order, customer: Customer) -> dict | None:
    em, ph = hash_email(customer.email), hash_phone(customer.phone)
    user = {k: [v] for k, v in (("em", em), ("ph", ph), ("country", _sha("pk"))) if v}
    if not em and not ph:
        return None
    return {
        "event_name": "Purchase", "event_time": int(event.event_time.timestamp()), "event_id": event.event_id,
        "action_source": "website" if order.sales_channel == "website" else "system_generated", "user_data": user,
        "custom_data": {"currency": "PKR", "value": float(order.order_value), "order_id": order.external_id},
    }


def send_pending(db: Session, settings: Settings, now: datetime | None = None, limit: int = 25) -> dict[str, int]:
    """Send (or, in test mode, only prepare) the Purchase events that are due. Safe to run again and again."""
    now = now or datetime.now(timezone.utc)
    counts = {"sent": 0, "dry_run": 0, "skipped": 0, "failed": 0, "waiting": 0}
    for event in list(db.scalars(select(MetaEvent).where(MetaEvent.status == "pending").order_by(MetaEvent.id).limit(limit))):
        order = db.get(Order, event.order_id)
        customer = db.get(Customer, order.customer_id) if order else None
        if order is None or customer is None or not agreed(db, customer.id):
            event.status, event.error = "skipped", "no_consent"
            counts["skipped"] += 1
            continue
        payload = build_event(db, event, order, customer)
        if payload is None:
            event.status, event.error = "skipped", "no_contact"
            counts["skipped"] += 1
            continue
        if settings.meta_ads_dry_run:
            event.status, event.sent_at = "dry_run", now
            counts["dry_run"] += 1
            continue
        if not settings.meta_pixel_id:
            counts["waiting"] += 1                                  # not set up yet: stays pending, nothing is lost
            continue
        event.attempts += 1
        try:
            _call(settings, "POST", f"{settings.meta_pixel_id}/events", {"data": json.dumps([payload])})
            event.status, event.sent_at, event.error = "sent", now, None
            counts["sent"] += 1
        except ApiError as exc:
            event.error = exc.message[:200]
            if event.attempts >= MAX_ATTEMPTS:
                event.status = "failed"
                counts["failed"] += 1
    db.flush()
    return counts


# --- ad spend: from a file or from Meta -----------------------------------------------------------------------------------------


@dataclass
class ImportResult:
    added: int = 0
    updated: int = 0
    rejected: int = 0
    errors: list[str] = None  # type: ignore[assignment]


def _date(text: str) -> date:
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("date")


def _money(text: str | None) -> Decimal | None:
    cleaned = (text or "").replace(",", "").replace("Rs", "").replace("PKR", "").strip()
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("number") from exc
    if value < 0 or value > Decimal("99999999"):
        raise ValueError("number")
    return value


def upsert_spend(db: Session, day: date, channel: str, campaign: str | None, amount: Decimal, purchases: int | None, revenue: Decimal | None, source: str) -> bool:
    """Add a row, or update the one for the same day + channel + campaign (so importing a file twice changes nothing). True when added."""
    campaign = (campaign or "").strip() or None
    existing = db.scalar(select(AdSpend).where(AdSpend.spend_date == day, AdSpend.channel == channel, AdSpend.campaign.is_(None) if campaign is None else AdSpend.campaign == campaign))
    if existing is None:
        db.add(AdSpend(spend_date=day, channel=channel, campaign=campaign, amount=amount, source=source, meta_purchases=purchases, meta_revenue=revenue))
        return True
    existing.amount, existing.source, existing.meta_purchases, existing.meta_revenue = amount, source, purchases, revenue
    return False


def import_spend_csv(db: Session, content: bytes) -> ImportResult:
    """Columns (any order, names not case sensitive): date, amount, and optionally channel, campaign, purchases, purchase_value."""
    if len(content) > MAX_CSV_BYTES:
        raise ApiError(413, "file_too_large", "The file is too large (1 MB at most).")
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    except UnicodeDecodeError as exc:
        raise ApiError(422, "not_text", "Save the file as CSV (UTF-8) and try again.") from exc
    headers = {(h or "").strip().lower().replace(" ", "_"): h for h in (reader.fieldnames or [])}
    for needed in ("date", "amount"):
        if needed not in headers:
            raise ApiError(422, "missing_column", f"The file needs a '{needed}' column.")
    result = ImportResult(errors=[])
    for number, row in enumerate(reader, start=2):
        if number > MAX_CSV_ROWS + 1:
            result.errors.append(f"Stopped after {MAX_CSV_ROWS} rows.")
            break
        get = lambda name: row.get(headers.get(name, ""), "") or ""  # noqa: E731
        try:
            day, amount = _date(get("date")), _money(get("amount"))
            if amount is None:
                raise ValueError("number")
            purchases = int(get("purchases")) if get("purchases").strip() else None
            revenue = _money(get("purchase_value"))
        except ValueError as exc:
            result.rejected += 1
            result.errors.append(f"Row {number}: the {exc} is not valid.")
            continue
        added = upsert_spend(db, day, normalise_channel(get("channel") or "facebook"), get("campaign"), amount, purchases, revenue, "csv")
        result.added += int(added)
        result.updated += int(not added)
    db.flush()
    result.errors = result.errors[:10]
    return result


def parse_insights(payload: dict) -> list[tuple[date, str | None, Decimal, int | None, Decimal | None]]:
    """Rows of the Marketing API Insights answer (level=campaign, daily): (day, campaign, spend, purchases, purchase value)."""
    rows = []
    for item in payload.get("data", []):
        try:
            day = date.fromisoformat(item["date_start"])
            spend = Decimal(str(item.get("spend", "0")))
        except (KeyError, ValueError, InvalidOperation):
            continue
        purchases = next((int(float(a["value"])) for a in item.get("actions", []) if a.get("action_type") in ("purchase", "omni_purchase")), None)
        revenue = next((Decimal(str(a["value"])) for a in item.get("action_values", []) if a.get("action_type") in ("purchase", "omni_purchase")), None)
        rows.append((day, item.get("campaign_name"), spend, purchases, revenue))
    return rows


def sync_spend(db: Session, settings: Settings, since: date, until: date) -> int:
    """Read daily campaign spend from the Marketing API (reading is harmless, so test mode does not block it)."""
    if not settings.meta_ad_account_id:
        raise ApiError(503, "meta_not_configured", "Add META_AD_ACCOUNT_ID to the backend settings.")
    answer = _call(settings, "GET", f"act_{settings.meta_ad_account_id}/insights", {
        "level": "campaign", "time_increment": "1", "fields": "campaign_name,spend,actions,action_values", "limit": "500",
        "time_range": json.dumps({"since": since.isoformat(), "until": until.isoformat()}),
    })
    rows = parse_insights(answer)
    for day, campaign, spend, purchases, revenue in rows:
        upsert_spend(db, day, "facebook", campaign, spend, purchases, revenue, "meta")
    db.flush()
    return len(rows)


# --- true ROAS --------------------------------------------------------------------------------------------------------------------


@dataclass
class RoasRow:
    campaign: str
    spend: Decimal
    meta_purchases: int | None
    meta_revenue: Decimal | None
    orders: int = 0
    delivered: int = 0
    returned: int = 0
    real_revenue: Decimal = Decimal(0)
    enough: bool = False
    meta_roas: float | None = None
    true_roas: float | None = None
    cost_per_delivered: float | None = None


def roas(db: Session, start: date, end: date) -> tuple[list[RoasRow], int]:
    """(one row per campaign, orders in the period that carry no campaign tag). True ROAS counts only DELIVERED, not-returned revenue."""
    spend: dict[str, RoasRow] = {}
    for row in db.scalars(select(AdSpend).where(AdSpend.spend_date >= start, AdSpend.spend_date <= end)):
        key = (row.campaign or "(no campaign name)").casefold()
        r = spend.setdefault(key, RoasRow(campaign=row.campaign or "(no campaign name)", spend=Decimal(0), meta_purchases=None, meta_revenue=None))
        r.spend += row.amount
        if row.meta_purchases is not None:
            r.meta_purchases = (r.meta_purchases or 0) + row.meta_purchases
        if row.meta_revenue is not None:
            r.meta_revenue = (r.meta_revenue or Decimal(0)) + row.meta_revenue
    untagged = 0
    campaign_of = dict(db.execute(select(Order.id, Order.utm_campaign).where(Order.order_date >= start, Order.order_date <= end)).all())
    for f in profit_analytics.load_facts(db, start, end):
        tag = (campaign_of.get(f.id) or "").strip().casefold()
        r = spend.get(tag) if tag else None
        if r is None:
            untagged += 1
            continue
        r.orders += 1
        r.delivered += f.fate == "delivered"
        r.returned += f.fate == "returned"
        r.real_revenue += f.value if f.fate == "delivered" else Decimal(0)
    for r in spend.values():
        r.enough = data_rules.enough(r.delivered)
        if r.spend > 0:
            r.meta_roas = float(r.meta_revenue / r.spend) if r.meta_revenue is not None else None
            r.true_roas = float(r.real_revenue / r.spend) if r.enough else None
            r.cost_per_delivered = float(r.spend / r.delivered) if r.enough and r.delivered else None
    return sorted(spend.values(), key=lambda r: r.spend, reverse=True), untagged
