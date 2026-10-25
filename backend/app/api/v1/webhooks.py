"""PUBLIC endpoints: Meta's WhatsApp webhook, and the email unsubscribe link.

They have no sign-in, because Meta and a mail client cannot sign in. They protect themselves instead:
the WhatsApp webhook checks Meta's HMAC signature before it reads anything, and the unsubscribe link carries a
signed token that cannot be made without the server's secret.
"""

import json
import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import error_body
from app.db.session import get_db
from app.services import shopify_hooks
from app.services.messaging import webhook

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])

MAX_WEBHOOK_BYTES = 1_000_000


@router.get("/webhooks/whatsapp", response_class=PlainTextResponse, summary="Meta's check when the webhook is registered")
def whatsapp_verify(
    mode: str | None = Query(default=None, alias="hub.mode"), token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"), settings: Settings = Depends(get_settings),
):
    if webhook.verify_challenge(settings, mode, token) and challenge is not None:
        return PlainTextResponse(challenge)
    return JSONResponse(status_code=403, content=error_body("forbidden", "The verify token does not match."))


@router.post("/webhooks/whatsapp", summary="Delivery status and replies from WhatsApp")
async def whatsapp_receive(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        return JSONResponse(status_code=413, content=error_body("payload_too_large", "The request is too large."))
    secret = settings.whatsapp_app_secret.get_secret_value() if settings.whatsapp_app_secret else None
    if not webhook.verify_signature(secret, body, request.headers.get("x-hub-signature-256")):
        logger.warning("WhatsApp webhook refused: bad or missing signature")
        return JSONResponse(status_code=403, content=error_body("bad_signature", "The signature is not valid."))
    try:
        payload = json.loads(body)
    except ValueError:
        return JSONResponse(status_code=400, content=error_body("bad_json", "The body is not JSON."))
    counts = webhook.process_whatsapp_payload(db, payload)
    db.commit()
    if counts["incoming"]:
        _store_waiting_media(db, settings)
    return {"ok": True, **counts}


def _store_waiting_media(db: Session, settings: Settings) -> None:
    """Try one waiting customer file right away (a video can take a few seconds). Anything left is picked up later by the
    scheduler. It must never turn Meta's call into an error: Meta would send the same call again."""
    from app.services.messaging import media

    try:
        media.process_pending_media(db, settings, limit=1)
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Could not store a customer file straight away")
        db.rollback()


def _page(title: str, message: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        status_code=status_code,
        content=(
            '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{title}</title></head><body style=\"font-family:Arial,sans-serif;max-width:480px;margin:15vh auto;padding:0 16px;color:#0f172a\">"
            f"<h1 style=\"font-size:22px\">{title}</h1><p>{message}</p></body></html>"
        ),
    )


@router.get("/unsubscribe", response_class=HTMLResponse, summary="The unsubscribe link in an email")
def unsubscribe_link(token: str = Query(min_length=8, max_length=300), db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    if not webhook.unsubscribe(db, settings, token):
        return _page("This link is not valid", "The unsubscribe link is damaged or has expired. Reply to the email and ask to be removed.", 400)
    db.commit()
    return _page("You are unsubscribed", "You will not get these messages any more. If this was a mistake, tell the shop and they can add you back.")


@router.post("/unsubscribe", summary="One-click unsubscribe (used by mail apps)")
def unsubscribe_one_click(token: str = Query(min_length=8, max_length=300), db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    if not webhook.unsubscribe(db, settings, token):
        return JSONResponse(status_code=400, content=error_body("bad_token", "The unsubscribe link is not valid."))
    db.commit()
    return {"ok": True}


@router.post("/webhooks/shopify", summary="Order and fulfillment events from Shopify")
async def shopify_receive(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        return JSONResponse(status_code=413, content=error_body("payload_too_large", "The request is too large."))
    secret = settings.shopify_webhook_secret.get_secret_value() if settings.shopify_webhook_secret else None
    if not shopify_hooks.verify_hmac(secret, body, request.headers.get("x-shopify-hmac-sha256")):
        logger.warning("Shopify webhook refused: bad or missing signature")
        return JSONResponse(status_code=403, content=error_body("bad_signature", "The signature is not valid."))
    if not shopify_hooks.shop_allowed(settings, request.headers.get("x-shopify-shop-domain")):
        return JSONResponse(status_code=403, content=error_body("wrong_shop", "This shop is not allowed."))
    try:
        payload = json.loads(body)
    except ValueError:
        return JSONResponse(status_code=400, content=error_body("bad_json", "The body is not JSON."))
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content=error_body("bad_json", "The body must be a JSON object."))
    if shopify_hooks.already_handled(db, request.headers.get("x-shopify-webhook-id")):
        db.commit()
        return {"ok": True, "duplicate": True}
    result = shopify_hooks.handle(db, settings, request.headers.get("x-shopify-topic", ""), payload)
    db.commit()
    return {"ok": True, **result}


# --- leads -------------------------------------------------------------------------------------------------------------------


@router.get("/webhooks/meta-leads", response_class=PlainTextResponse, summary="Meta's check when the Lead Ads webhook is registered")
def meta_leads_verify(
    mode: str | None = Query(default=None, alias="hub.mode"), token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"), settings: Settings = Depends(get_settings),
):
    if webhook.verify_challenge(settings, mode, token) and challenge is not None:
        return PlainTextResponse(challenge)
    return JSONResponse(status_code=403, content=error_body("forbidden", "The verify token does not match."))


@router.post("/webhooks/meta-leads", summary="New Lead Ads leads from Meta")
async def meta_leads_receive(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    from app.core.errors import ApiError
    from app.services import leads as lead_service

    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        return JSONResponse(status_code=413, content=error_body("payload_too_large", "The request is too large."))
    secret = settings.whatsapp_app_secret.get_secret_value() if settings.whatsapp_app_secret else None
    if not webhook.verify_signature(secret, body, request.headers.get("x-hub-signature-256")):
        logger.warning("Meta leads webhook refused: bad or missing signature")
        return JSONResponse(status_code=403, content=error_body("bad_signature", "The signature is not valid."))
    try:
        payload = json.loads(body)
    except ValueError:
        return JSONResponse(status_code=400, content=error_body("bad_json", "The body is not JSON."))
    saved = 0
    for entry in payload.get("entry", []) if isinstance(payload, dict) else []:
        for change in entry.get("changes", []) if isinstance(entry, dict) else []:
            value = change.get("value", {}) if isinstance(change, dict) and change.get("field") == "leadgen" else {}
            leadgen_id = str(value.get("leadgen_id") or "")
            if not leadgen_id:
                continue
            try:
                details = lead_service.fetch_meta_lead(settings, leadgen_id)
                _, created = lead_service.from_meta_fields(db, leadgen_id, details.get("field_data") or [], campaign=str(value.get("ad_id") or value.get("form_id") or "") or None)
                saved += int(created)
            except ApiError as exc:
                if exc.status_code == 502:
                    db.rollback()
                    return JSONResponse(status_code=502, content=error_body(exc.code, exc.message))      # Meta will send it again
                logger.warning("Lead %s not saved: %s", leadgen_id, exc.code)                            # not configured, or an unusable lead: do not make Meta retry forever
    db.commit()
    return {"ok": True, "saved": saved}


@router.post("/public/leads", summary="Your website's contact form (off until PUBLIC_LEADS_ENABLED is set)")
async def public_lead(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    from app.core.errors import ApiError
    from app.services import leads as lead_service
    from app.services.rate_limit import check_rate_limit

    if not settings.public_leads_enabled:
        return JSONResponse(status_code=404, content=error_body("not_found", "Not found."))
    body = await request.body()
    if len(body) > 10_000:
        return JSONResponse(status_code=413, content=error_body("payload_too_large", "The request is too large."))
    try:
        data = json.loads(body)
    except ValueError:
        return JSONResponse(status_code=400, content=error_body("bad_json", "The body is not JSON."))
    if not isinstance(data, dict):
        return JSONResponse(status_code=400, content=error_body("bad_json", "The body is not JSON."))
    if data.get("website"):                                          # a hidden field a person never fills: only bots do
        return {"ok": True}
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")).split(",")[0].strip()
    check_rate_limit(f"lead-form:{ip}", limit=10, window_seconds=3600, what="the form")
    check_rate_limit("lead-form:all", limit=300, window_seconds=3600, what="the form")
    try:
        lead_service.create_lead(
            db, source="website_form", name=data.get("name"), phone=data.get("phone"), email=data.get("email"), campaign=data.get("campaign"),
            utm_source=data.get("utmSource"), utm_medium=data.get("utmMedium"), utm_campaign=data.get("utmCampaign"),
            product_interest=data.get("productInterest"), notes=data.get("message"),
        )
    except ApiError as exc:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))
    db.commit()
    return {"ok": True}
