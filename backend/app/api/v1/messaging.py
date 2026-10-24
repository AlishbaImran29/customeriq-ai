"""Auto Messenger endpoints (signed-in): settings, test send, templates, consent, the message log, the queue.

The WhatsApp webhook and the email unsubscribe link are in webhooks.py, because they are public.
"""

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Form, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_user
from app.api.v1.shipments import _read_limited
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import ConsentEvent, Customer, CustomerConsent, IncomingMessage, Message, MessageTemplate, User
from app.schemas.messaging import (
    ChannelConsentOut, ConnectionOut, ConsentChangeIn, ConsentCountOut, ConsentCustomerOut, ConsentImportOut, ConsentPage, IncomingOut,
    MessageOut, PreviewIn, PreviewOut, QueueOut, SettingsIn, SettingsOut, SimulateIncomingIn, SimulateStatusIn, TemplateIn,
    TemplateOut, TemplatePatch, TestSendIn, TestSendOut, VariableOut,
)
from app.services import mailer
from app.services.import_files import file_type_of, parse_file
from app.services.import_validation import RowError, _as_text, _parse_date, normalise_header
from app.services.messaging import adapters, consent as consent_service, service, webhook
from app.services.messaging.adapters import Outbound, mask, whatsapp_configured
from app.services.messaging.render import OPTIONAL, VARIABLES, MissingVariable, check_template_text, meta_style, render, variables_in
from app.services.messaging.settings_store import dry_run_forced, effective_dry_run, get_row
from app.services.messaging.tokens import unsubscribe_link
from app.services.phone import normalise_pk_phone
from app.services.rate_limit import check_rate_limit

router = APIRouter(prefix="/messaging", tags=["messaging"])

TEST_SENDS_PER_WINDOW = 5
TEST_WINDOW_SECONDS = 600
TEST_TEXT = "This is a test message from CustomerIQ AI. If you can read it, your messaging connection works."
MAX_IMPORT_ROWS = 50_000


def _hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def _parse_hhmm(text: str) -> time:
    hour, minute = text.split(":")
    return time(int(hour), int(minute))


# =========================== settings ===========================


def _email_provider(settings: Settings) -> str | None:
    if not settings.email_configured:
        return None
    return "webhook" if settings.mail_webhook_url else "brevo" if settings.brevo_api_key else "smtp"


def _settings_out(db: Session, settings: Settings) -> SettingsOut:
    row = get_row(db)
    base = (settings.public_api_url or "").rstrip("/")
    secret_ok = bool(settings.messaging_secret and settings.messaging_secret.get_secret_value().strip())
    counts = consent_service.consent_counts(db)
    return SettingsOut(
        dry_run=row.dry_run, dry_run_forced=dry_run_forced(settings), effective_dry_run=effective_dry_run(settings, row),
        quiet_start=_hhmm(row.quiet_start), quiet_end=_hhmm(row.quiet_end), timezone=row.timezone,
        weekly_marketing_cap=row.weekly_marketing_cap, default_language=row.default_language,  # type: ignore[arg-type]
        store_name=row.store_name, review_url=row.review_url,
        cost_utility=float(row.cost_utility) if row.cost_utility is not None else None,
        cost_marketing=float(row.cost_marketing) if row.cost_marketing is not None else None,
        campaign_batch_size=row.campaign_batch_size, early_access_hours=row.early_access_hours, holdout_percent=row.holdout_percent,
        whatsapp=ConnectionOut(
            configured=whatsapp_configured(settings),
            details={
                "accessToken": bool(settings.whatsapp_access_token and settings.whatsapp_access_token.get_secret_value().strip()),
                "phoneNumberId": bool(settings.whatsapp_phone_number_id),
                "appSecret": bool(settings.whatsapp_app_secret and settings.whatsapp_app_secret.get_secret_value().strip()),
                "verifyToken": bool(settings.whatsapp_verify_token and settings.whatsapp_verify_token.get_secret_value().strip()),
            },
        ),
        email=ConnectionOut(configured=settings.email_configured, details={}, provider=_email_provider(settings)),
        unsubscribe_ready=secret_ok and bool(base),
        webhook_url=f"{base}/api/v1/webhooks/whatsapp" if base else None,
        consent={k: ConsentCountOut(**v) for k, v in counts.items()},
        development=settings.app_env != "production",
        scheduler_ready=bool(settings.scheduler_secret and settings.scheduler_secret.get_secret_value().strip()),
        shopify_ready=bool(settings.shopify_webhook_secret and settings.shopify_webhook_secret.get_secret_value().strip()),
    )


@router.get("/settings", response_model=SettingsOut, summary="Messaging settings and connection status")
def get_messaging_settings(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> SettingsOut:
    return _settings_out(db, settings)


@router.put("/settings", response_model=SettingsOut, summary="Change the messaging settings")
def put_messaging_settings(body: SettingsIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> SettingsOut:
    row = get_row(db)
    sent = body.model_fields_set
    if "dry_run" in sent and body.dry_run is not None:
        if body.dry_run is False and dry_run_forced(settings):
            raise ApiError(409, "dry_run_forced", "The server is set to dry run (MESSAGING_DRY_RUN=true), so it cannot be turned off here.")
        row.dry_run = body.dry_run
    if body.quiet_start is not None:
        row.quiet_start = _parse_hhmm(body.quiet_start)
    if body.quiet_end is not None:
        row.quiet_end = _parse_hhmm(body.quiet_end)
    if row.quiet_start == row.quiet_end:
        raise ApiError(422, "invalid_quiet_hours", "Quiet hours cannot start and end at the same time.")
    for field in ("weekly_marketing_cap", "default_language", "campaign_batch_size", "early_access_hours", "holdout_percent"):
        if field in sent and getattr(body, field) is not None:
            setattr(row, field, getattr(body, field))
    if "store_name" in sent:
        row.store_name = (body.store_name or "").strip() or None
    if "review_url" in sent:
        url = (body.review_url or "").strip() or None
        if url and not url.startswith("https://"):
            raise ApiError(422, "invalid_link", "The review link must start with https://", {"field": "reviewUrl"})
        row.review_url = url
    for field in ("cost_utility", "cost_marketing"):
        if field in sent:
            setattr(row, field, getattr(body, field))
    db.commit()
    return _settings_out(db, settings)


@router.post("/test-send", response_model=TestSendOut, summary="Send one test message to yourself")
def test_send(
    body: TestSendIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings), user: User = Depends(require_user),
) -> TestSendOut:
    """A test goes to ONE address you control: your own email, or a mobile number you type (Meta's test number only
    reaches the numbers you have added in Meta). It is rate limited and uses fixed text, so it cannot be used to
    message other people. It needs no consent because it is not a message to a customer, and it is not saved."""
    check_rate_limit(f"messaging-test:{user.id}", limit=TEST_SENDS_PER_WINDOW, window_seconds=TEST_WINDOW_SECONDS, what="test messages")
    dry = effective_dry_run(settings, get_row(db))
    if body.channel == "email":
        target = (getattr(user, "email", "") or "").strip()
        if not target:
            raise ApiError(422, "no_email", "Your account has no email address to send the test to.")
        out = Outbound("email", target, TEST_TEXT, body.language, subject="CustomerIQ AI test message", unsubscribe_url=unsubscribe_link(settings, 0))
    else:
        phone = normalise_pk_phone(body.to or "")
        if phone is None:
            raise ApiError(422, "invalid_phone", "Type a Pakistani mobile number like 0300 1234567.", {"field": "to"})
        target = phone.lstrip("+")
        out = Outbound("whatsapp", target, TEST_TEXT, body.language)
    result = adapters.adapter_for(body.channel, settings, dry).send(out)
    return TestSendOut(ok=result.ok, dry_run=dry, error=result.error, sent_to=mask(target))


# =========================== templates ===========================

SAMPLE_VALUES = {
    "en": {
        "first_name": "Ali", "last_name": "Khan", "store_name": "Example Shop", "order_number": "ORD-1001", "items": "Red shoes x1",
        "amount": "Rs 2,500", "courier": "TCS", "tracking_number": "TRK123456", "tracking_line": "Courier: TCS, tracking number TRK123456.",
        "cod_note": "Please keep Rs 2,500 ready.", "review_link": "https://example.com/review", "product_name": "Example product",
        "price": "Rs 1,999", "category": "Shoes", "last_product": "Red shoes", "last_category": "Shoes", "segment": "Champions",
        "offer_text": "Free delivery this week",
    },
    "ur": {
        "first_name": "علی", "last_name": "خان", "store_name": "مثال شاپ", "order_number": "ORD-1001", "items": "سرخ جوتے x1",
        "amount": "Rs 2,500", "courier": "TCS", "tracking_number": "TRK123456", "tracking_line": "کورئیر: TCS، ٹریکنگ نمبر TRK123456۔",
        "cod_note": "براہ کرم Rs 2,500 تیار رکھیں۔", "review_link": "https://example.com/review", "product_name": "مثال کی پروڈکٹ",
        "price": "Rs 1,999", "category": "جوتے", "last_product": "سرخ جوتے", "last_category": "جوتے", "segment": "Champions",
        "offer_text": "اس ہفتے مفت ڈیلیوری",
    },
}


def _template_out(t: MessageTemplate) -> TemplateOut:
    names = variables_in(t.body) + [n for n in variables_in(t.subject or "") if n not in variables_in(t.body)]
    return TemplateOut(
        id=t.id, name=t.name, channel=t.channel, category=t.category, language=t.language, event=t.event, subject=t.subject,  # type: ignore[arg-type]
        body=t.body, variables=names, meta_template_name=t.meta_template_name, meta_approval_status=t.meta_approval_status,  # type: ignore[arg-type]
        approved_by_seller=t.approved_by_seller, approved_at=t.approved_at, is_default=t.is_default,
    )


def _get_template(db: Session, template_id: int) -> MessageTemplate:
    template = db.get(MessageTemplate, template_id)
    if template is None:
        raise ApiError(404, "template_not_found", "That template was not found.")
    return template


@router.get("/variables", response_model=list[VariableOut], summary="The {{variables}} a template may use")
def list_variables() -> list[VariableOut]:
    return [VariableOut(name=n, description=d, optional=n in OPTIONAL) for n, d in VARIABLES.items()]


@router.get("/templates", response_model=list[TemplateOut], summary="Message templates")
def list_templates(channel: str | None = Query(default=None, pattern="^(whatsapp|email)$"), db: Session = Depends(get_db)) -> list[TemplateOut]:
    query = select(MessageTemplate).order_by(MessageTemplate.event.is_(None), MessageTemplate.event, MessageTemplate.channel, MessageTemplate.language, MessageTemplate.name)
    if channel:
        query = query.where(MessageTemplate.channel == channel)
    return [_template_out(t) for t in db.scalars(query.limit(500))]


@router.post("/templates/preview", response_model=PreviewOut, summary="Show a template with example values")
def preview_template(body: PreviewIn) -> PreviewOut:
    try:
        names = check_template_text(body.body, body.subject)
    except ApiError as error:
        return PreviewOut(text=None, subject=None, variables=[], meta_body="", meta_variables=[], error=error.message)
    values = SAMPLE_VALUES[body.language]
    try:
        text = render(body.body, values)
        subject = render(body.subject, values) if body.subject else None
    except MissingVariable as missing:
        return PreviewOut(text=None, subject=None, variables=names, meta_body="", meta_variables=[], error=f"No example value for {missing.name}.")
    meta_body, meta_names = meta_style(body.body)
    return PreviewOut(text=text, subject=subject, variables=names, meta_body=meta_body, meta_variables=meta_names, error=None)


def _check_new_text(channel: str, body: str, subject: str | None) -> str | None:
    check_template_text(body, subject)
    if channel == "email":
        if not (subject or "").strip():
            raise ApiError(422, "invalid_template", "An email template needs a subject.", {"field": "subject"})
        return subject.strip() if subject else None
    return None


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED, summary="Create a template (not approved yet)")
def create_template(body: TemplateIn, db: Session = Depends(get_db)) -> TemplateOut:
    subject = _check_new_text(body.channel, body.body, body.subject)
    template = MessageTemplate(
        name=body.name.strip(), channel=body.channel, category=body.category, language=body.language, event=(body.event or "").strip() or None,
        subject=subject, body=body.body.strip(), meta_template_name=(body.meta_template_name or "").strip() or None,
    )
    try:
        with db.begin_nested():
            db.add(template)
            db.flush()
    except IntegrityError:
        raise ApiError(409, "template_exists", "A template with this name, channel and language already exists.") from None
    db.commit()
    return _template_out(template)


@router.patch("/templates/{template_id}", response_model=TemplateOut, summary="Change a template")
def edit_template(template_id: int, body: TemplatePatch, db: Session = Depends(get_db)) -> TemplateOut:
    template = _get_template(db, template_id)
    sent = body.model_fields_set
    new_body = body.body.strip() if "body" in sent and body.body else template.body
    new_subject = ((body.subject or "").strip() or None) if "subject" in sent else template.subject
    wording_changed = new_body != template.body or new_subject != template.subject
    if wording_changed:
        new_subject = _check_new_text(template.channel, new_body, new_subject)
        # The seller approved THIS wording (and Meta approved it too): a different text needs a new approval.
        template.body, template.subject = new_body, new_subject
        template.approved_by_seller, template.approved_at = False, None
        template.meta_approval_status = "not_submitted"
    if "name" in sent and body.name:
        template.name = body.name.strip()
    if "category" in sent and body.category:
        template.category = body.category
        template.approved_by_seller, template.approved_at = False, None
    if "event" in sent:
        template.event = (body.event or "").strip() or None
    if "meta_template_name" in sent:
        template.meta_template_name = (body.meta_template_name or "").strip() or None
    if "meta_approval_status" in sent and body.meta_approval_status:
        template.meta_approval_status = body.meta_approval_status
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "template_exists", "A template with this name, channel and language already exists.") from None
    db.commit()
    return _template_out(template)


@router.post("/templates/{template_id}/approve", response_model=TemplateOut, summary="Approve a template so it may be sent")
def approve_template(template_id: int, db: Session = Depends(get_db)) -> TemplateOut:
    """Project rule 3: nothing is sent from a template until the seller approves it."""
    template = _get_template(db, template_id)
    check_template_text(template.body, template.subject)
    if template.channel == "whatsapp" and template.category == "marketing" and "stop" not in template.body.casefold():
        raise ApiError(
            422, "needs_stop_instruction",
            "A marketing message on WhatsApp must tell people how to stop, for example: Reply STOP to stop messages.", {"field": "body"},
        )
    template.approved_by_seller, template.approved_at = True, datetime.now(timezone.utc)
    db.commit()
    return _template_out(template)


@router.post("/templates/{template_id}/unapprove", response_model=TemplateOut, summary="Take a template out of use")
def unapprove_template(template_id: int, db: Session = Depends(get_db)) -> TemplateOut:
    template = _get_template(db, template_id)
    template.approved_by_seller, template.approved_at = False, None
    db.commit()
    return _template_out(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a template")
def delete_template(template_id: int, db: Session = Depends(get_db)) -> Response:
    db.delete(_get_template(db, template_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =========================== consent ===========================


def _like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _channel_consent(rows: dict[tuple[int, str], CustomerConsent], customer_id: int, channel: str) -> ChannelConsentOut:
    row = rows.get((customer_id, channel))
    if row is None:
        return ChannelConsentOut(state="none", changed_on=None, source=None)
    return ChannelConsentOut(state="opted_in" if row.opted_in else "opted_out", changed_on=row.changed_on, source=row.source)


@router.get("/consent", response_model=ConsentPage, summary="Customers and their consent")
def list_consent(
    search: str | None = Query(default=None, max_length=80),
    channel: str | None = Query(default=None, pattern="^(whatsapp|email)$"),
    state: str | None = Query(default=None, pattern="^(opted_in|opted_out|none)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ConsentPage:
    query = select(Customer)
    if search and search.strip():
        pattern = f"%{_like(search.strip())}%"
        query = query.where(or_(*(col.ilike(pattern, escape="\\") for col in (Customer.first_name, Customer.last_name, Customer.email, Customer.phone, Customer.phone_normalised, Customer.external_id))))
    if channel and state:
        match = exists().where(CustomerConsent.customer_id == Customer.id, CustomerConsent.channel == channel)
        if state == "none":
            query = query.where(~match)
        else:
            query = query.where(match.where(CustomerConsent.opted_in.is_(state == "opted_in")))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    customers = list(db.scalars(query.order_by(Customer.id.desc()).limit(limit).offset(offset)))
    rows = {(c.customer_id, c.channel): c for c in db.scalars(select(CustomerConsent).where(CustomerConsent.customer_id.in_([c.id for c in customers])))} if customers else {}
    return ConsentPage(total=int(total), customers=[
        ConsentCustomerOut(
            id=c.id, name=" ".join(p for p in (c.first_name, c.last_name) if p) or c.external_id, phone=c.phone_normalised or c.phone, email=c.email,
            whatsapp=_channel_consent(rows, c.id, "whatsapp"), email_consent=_channel_consent(rows, c.id, "email"),
        ) for c in customers
    ])


@router.patch("/consent/{customer_id}", response_model=ConsentCustomerOut, summary="Record that a customer agreed, or stopped")
def change_consent(customer_id: int, body: ConsentChangeIn, db: Session = Depends(get_db)) -> ConsentCustomerOut:
    """The seller records what the customer told them. Only record an opt-in when the customer really agreed."""
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise ApiError(404, "customer_not_found", "That customer was not found.")
    consent_service.set_consent(db, customer_id, body.channel, body.opted_in, "manual", note=body.note)
    db.commit()
    rows = {(c.customer_id, c.channel): c for c in db.scalars(select(CustomerConsent).where(CustomerConsent.customer_id == customer_id))}
    return ConsentCustomerOut(
        id=customer.id, name=" ".join(p for p in (customer.first_name, customer.last_name) if p) or customer.external_id,
        phone=customer.phone_normalised or customer.phone, email=customer.email,
        whatsapp=_channel_consent(rows, customer_id, "whatsapp"), email_consent=_channel_consent(rows, customer_id, "email"),
    )


@router.get("/consent/{customer_id}/history", summary="Every consent change of one customer")
def consent_history(customer_id: int, db: Session = Depends(get_db)) -> list[dict]:
    events = db.scalars(select(ConsentEvent).where(ConsentEvent.customer_id == customer_id).order_by(ConsentEvent.at.desc(), ConsentEvent.id.desc()).limit(100))
    return [{"channel": e.channel, "action": e.action, "source": e.source, "note": e.note, "at": e.at.isoformat()} for e in events]


_YES = {"yes", "y", "true", "1", "opt in", "opted in", "opt_in", "opted_in", "agreed"}
_NO = {"no", "n", "false", "0", "opt out", "opted out", "opt_out", "opted_out", "stop"}
_ALIASES = {"mobile": "phone", "phone_number": "phone", "whatsapp": "phone", "e_mail": "email", "email_address": "email", "consent": "opted_in", "opt_in": "opted_in", "agreed": "opted_in", "answer": "opted_in"}


@router.post("/consent/import", response_model=ConsentImportOut, summary="Import consent you collected elsewhere (CSV or Excel)")
async def import_consent(file: UploadFile, confirm: bool = Form(default=False), db: Session = Depends(get_db)) -> ConsentImportOut:
    """Columns: phone and/or email, channel (whatsapp or email), opted_in (yes/no), date (optional), source (optional).

    The seller confirms the customers really agreed. The import can only record what the file says: it never
    guesses, and a row it cannot match to a customer is listed, not created."""
    if not confirm:
        raise ApiError(422, "not_confirmed", "Tick the box to confirm that these customers really agreed to be messaged.")
    content = await _read_limited(file)
    parsed = await run_in_threadpool(parse_file, content, file_type_of((file.filename or "consent")[:255]))
    positions: dict[str, int] = {}
    for index, raw in enumerate(parsed.headers):
        name = normalise_header(raw)
        name = _ALIASES.get(name, name)
        if name in ("phone", "email", "channel", "opted_in", "date", "source") and name not in positions:
            positions[name] = index
    if "channel" not in positions or "opted_in" not in positions or not ({"phone", "email"} & positions.keys()):
        raise ApiError(422, "missing_columns", "The file needs the columns: channel, opted_in, and phone and/or email.")
    if len(parsed.rows) > MAX_IMPORT_ROWS:
        raise ApiError(422, "too_many_rows", f"The file has more than {MAX_IMPORT_ROWS:,} rows.")

    result = ConsentImportOut(rows_in_file=len(parsed.rows), changed=0, unchanged=0, not_found=0, rejected=0, errors=[])
    by_phone: dict[str, Customer] = {}
    by_email: dict[str, Customer] = {}
    for start in range(0, len(parsed.rows), 1000):
        chunk = parsed.rows[start:start + 1000]
        phones, emails = set(), set()
        for r in chunk:
            p = normalise_pk_phone(_as_text(r.values[positions["phone"]]) or "") if "phone" in positions and positions["phone"] < len(r.values) else None
            e = (_as_text(r.values[positions["email"]]) or "").lower() if "email" in positions and positions["email"] < len(r.values) else ""
            if p:
                phones.add(p)
            if e:
                emails.add(e)
        if phones:
            by_phone.update({c.phone_normalised: c for c in db.scalars(select(Customer).where(Customer.phone_normalised.in_(phones)))})
        if emails:
            by_email.update({c.email.lower(): c for c in db.scalars(select(Customer).where(func.lower(Customer.email).in_(emails)))})

    for r in parsed.rows:
        n = r.number

        def cell(column: str):
            i = positions.get(column)
            return r.values[i] if i is not None and i < len(r.values) else None

        channel = (_as_text(cell("channel")) or "").lower()
        answer = (_as_text(cell("opted_in")) or "").lower()
        if channel not in ("whatsapp", "email"):
            result.errors.append(RowError(n, "channel", "Must be whatsapp or email.").as_dict())
            result.rejected += 1
            continue
        if answer not in _YES and answer not in _NO:
            result.errors.append(RowError(n, "opted_in", "Must be yes or no.").as_dict())
            result.rejected += 1
            continue
        when = None
        if _as_text(cell("date")) is not None:
            when = _parse_date(cell("date"), n, [])
            if when is None:
                result.errors.append(RowError(n, "date", "Enter a valid date (DD/MM/YYYY or YYYY-MM-DD) that is not in the future.").as_dict())
                result.rejected += 1
                continue
        phone = normalise_pk_phone(_as_text(cell("phone")) or "")
        email = (_as_text(cell("email")) or "").lower()
        customer = by_phone.get(phone) if phone else None
        customer = customer or (by_email.get(email) if email else None)
        if customer is None:
            result.not_found += 1
            continue
        source = (_as_text(cell("source")) or "import")[:40]
        before = consent_service.consent_state(db, customer.id, channel)
        consent_service.set_consent(db, customer.id, channel, answer in _YES, source, note="Imported from a file", today=when)
        result.changed += int(before != consent_service.consent_state(db, customer.id, channel))
        result.unchanged += int(before == consent_service.consent_state(db, customer.id, channel))
    db.commit()
    result.errors = result.errors[:200]
    return result


# =========================== messages and the queue ===========================


@router.get("/messages", response_model=list[MessageOut], summary="The message log")
def list_messages(
    status_filter: str | None = Query(default=None, alias="status", pattern="^(queued|sent|delivered|read|failed|replied|skipped)$"),
    channel: str | None = Query(default=None, pattern="^(whatsapp|email)$"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    query = select(Message).order_by(Message.id.desc()).limit(limit)
    if status_filter:
        query = query.where(Message.status == status_filter)
    if channel:
        query = query.where(Message.channel == channel)
    messages = list(db.scalars(query))
    names = {c.id: (" ".join(p for p in (c.first_name, c.last_name) if p) or c.external_id) for c in db.scalars(select(Customer).where(Customer.id.in_({m.customer_id for m in messages})))} if messages else {}
    templates = {t.id: t.name for t in db.scalars(select(MessageTemplate).where(MessageTemplate.id.in_({m.template_id for m in messages if m.template_id})))} if messages else {}
    return [
        MessageOut(
            id=m.id, customer_id=m.customer_id, customer_name=names.get(m.customer_id, "?"), channel=m.channel, category=m.category,  # type: ignore[arg-type]
            subject=m.subject, text=m.rendered_text, status=m.status, error=m.error, attempts=m.attempts, dry_run=m.dry_run,  # type: ignore[arg-type]
            template_name=templates.get(m.template_id) if m.template_id else None, campaign_id=m.campaign_id, journey_id=m.journey_id,
            order_id=m.order_id, queued_at=m.queued_at, sent_at=m.sent_at, next_attempt_at=m.next_attempt_at,
        ) for m in messages
    ]


@router.get("/incoming", response_model=list[IncomingOut], summary="Messages customers sent to you")
def list_incoming(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)) -> list[IncomingOut]:
    rows = list(db.scalars(select(IncomingMessage).order_by(IncomingMessage.id.desc()).limit(limit)))
    names = {c.id: (" ".join(p for p in (c.first_name, c.last_name) if p) or c.external_id) for c in db.scalars(select(Customer).where(Customer.id.in_({r.customer_id for r in rows if r.customer_id})))} if rows else {}
    return [IncomingOut(id=r.id, customer_name=names.get(r.customer_id) if r.customer_id else None, from_address=r.from_address, message_type=r.message_type, body=r.body, is_stop=r.is_stop, answer=r.answer, received_at=r.received_at) for r in rows]


@router.post("/process-queue", response_model=QueueOut, summary="Send the messages that were waiting (quiet hours or a retry)")
def process_queue_now(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> QueueOut:
    counts = service.process_queue(db, settings)
    db.commit()
    return QueueOut(**counts)


# =========================== demo helpers (never in production) ===========================


def _dev_only(settings: Settings) -> None:
    if settings.app_env == "production":
        raise ApiError(404, "not_found", "Not found.")


@router.post("/dev/simulate-incoming", summary="Pretend a customer sent a WhatsApp message (development and demos only)")
def simulate_incoming(body: SimulateIncomingIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    """Runs the same code as the real webhook, without Meta, so STOP can be shown in a demo. Off in production."""
    _dev_only(settings)
    phone = normalise_pk_phone(body.phone)
    if phone is None:
        raise ApiError(422, "invalid_phone", "Type a Pakistani mobile number like 0300 1234567.")
    stamp = int(datetime.now(timezone.utc).timestamp())
    payload = {"entry": [{"changes": [{"value": {"messages": [{"id": f"sim-{stamp}-{phone}", "from": phone.lstrip("+"), "type": "text", "timestamp": str(stamp), "text": {"body": body.text}}]}}]}]}
    counts = webhook.process_whatsapp_payload(db, payload)
    db.commit()
    return counts


@router.post("/dev/simulate-status", summary="Pretend WhatsApp reported a status (development and demos only)")
def simulate_status(body: SimulateStatusIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    _dev_only(settings)
    message = db.get(Message, body.message_id)
    if message is None or not message.provider_message_id:
        raise ApiError(404, "message_not_found", "That message was not found, or it was never sent.")
    changed = webhook.apply_status(db, message.provider_message_id, body.status, datetime.now(timezone.utc), "131026" if body.status == "failed" else None)
    db.commit()
    return {"changed": changed, "status": message.status}
