"""The three ways a message can leave: WhatsApp Cloud API, email, or a dry run that sends nothing.

All three answer with the same SendResult, so the rest of the code never needs to know which one it used:
    ok          it was handed to the provider
    provider_id the provider's id for it (WhatsApp's "wamid..."), which later status updates refer to
    error       a short code such as whatsapp_131030 or email_sender_refused (never a token or a server message)
    transient   True when trying again later may work (network trouble, a rate limit); False when it never will

WHY WHATSAPP NEEDS TEMPLATES: Meta only lets a business start a conversation with a message from a template
that Meta approved. Free text is allowed only inside 24 hours of the customer's own last message. The WhatsApp
adapter therefore sends either a TEMPLATE message (name + the variable values in order) or plain TEXT.
"""

import html
import json
import logging
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import Settings
from app.core.errors import ApiError
from app.services import mailer

logger = logging.getLogger(__name__)

WHATSAPP_TIMEOUT_SECONDS = 15
GRAPH_URL = "https://graph.facebook.com"
TRANSIENT_EMAIL_REASONS = {"timeout", "disconnected", "network_blocked", "unreachable", "provider_limit", "host_not_found", "tls_failed", "port_closed"}


@dataclass
class Outbound:
    channel: str                           # "whatsapp" or "email"
    to: str                                # WhatsApp: digits such as 923001234567; email: the address
    text: str                              # the rendered message
    language: str = "en"                   # "ur" or "en"
    subject: str | None = None             # email only
    meta_template_name: str | None = None  # WhatsApp: send as this approved template (None = plain text)
    template_values: list[str] = field(default_factory=list)   # WhatsApp: the variable values, in the template's order
    unsubscribe_url: str | None = None     # email: shown at the bottom and put in the List-Unsubscribe header


@dataclass
class SendResult:
    ok: bool
    provider_id: str | None = None
    error: str | None = None
    transient: bool = False


class Adapter(Protocol):
    def send(self, out: Outbound) -> SendResult: ...


def mask(address: str) -> str:
    """For logs: enough to recognise, not enough to identify (923001***567, a***@example.com)."""
    if "@" in address:
        name, _, domain = address.partition("@")
        return f"{name[:1]}***@{domain}"
    return f"{address[:5]}***{address[-3:]}" if len(address) > 8 else "***"


# --- dry run -------------------------------------------------------------------------------------


class DryRunAdapter:
    """Sends NOTHING. The message is written to the log (and kept in the messages table by the caller), so the
    whole feature can be shown without a WhatsApp account, an email service, or any cost."""

    def send(self, out: Outbound) -> SendResult:
        logger.info("DRY RUN %s to %s: %s", out.channel, mask(out.to), " ".join(out.text.split())[:80])
        return SendResult(ok=True, provider_id=f"dryrun-{uuid.uuid4().hex[:16]}")


# --- WhatsApp Cloud API ----------------------------------------------------------------------------


def whatsapp_configured(settings: Settings) -> bool:
    return bool(
        settings.whatsapp_access_token and settings.whatsapp_access_token.get_secret_value().strip()
        and settings.whatsapp_phone_number_id and settings.whatsapp_phone_number_id.strip()
    )


def whatsapp_payload(out: Outbound) -> dict:
    """The JSON for POST /{phone-number-id}/messages."""
    base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": out.to}
    if out.meta_template_name:
        components = []
        if out.template_values:
            components = [{"type": "body", "parameters": [{"type": "text", "text": v} for v in out.template_values]}]
        return {**base, "type": "template", "template": {"name": out.meta_template_name, "language": {"code": out.language}, "components": components}}
    return {**base, "type": "text", "text": {"preview_url": False, "body": out.text}}


class WhatsAppAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, out: Outbound) -> SendResult:
        if not whatsapp_configured(self.settings):
            return SendResult(ok=False, error="whatsapp_not_configured")
        url = f"{GRAPH_URL}/{self.settings.whatsapp_api_version}/{self.settings.whatsapp_phone_number_id}/messages"
        request = urllib.request.Request(
            url, data=json.dumps(whatsapp_payload(out)).encode(), method="POST",
            headers={"Authorization": f"Bearer {self.settings.whatsapp_access_token.get_secret_value()}", "Content-Type": "application/json"},  # type: ignore[union-attr]
        )
        try:
            with urllib.request.urlopen(request, timeout=WHATSAPP_TIMEOUT_SECONDS) as response:     # noqa: S310 (fixed https address)
                answer = json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            code = _graph_error_code(exc)
            logger.warning("WhatsApp send refused: HTTP %s, code %s", exc.code, code)
            return SendResult(ok=False, error=f"whatsapp_{code or exc.code}", transient=exc.code >= 500 or exc.code == 429)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return SendResult(ok=False, error="whatsapp_network", transient=True)
        wamid = (answer.get("messages") or [{}])[0].get("id") if isinstance(answer, dict) else None
        return SendResult(ok=bool(wamid), provider_id=wamid, error=None if wamid else "whatsapp_no_id")


def _graph_error_code(exc: urllib.error.HTTPError) -> int | None:
    try:
        body = json.loads(exc.read() or b"{}")
        code = body.get("error", {}).get("code")
        return code if isinstance(code, int) else None
    except (ValueError, AttributeError):
        return None


# --- email -----------------------------------------------------------------------------------------


def email_html(text: str, unsubscribe_url: str | None) -> str:
    """The plain message as a small, safe HTML email. Everything typed by a person is escaped."""
    body = html.escape(text).replace("\n", "<br>")
    footer = ""
    if unsubscribe_url:
        footer = (
            '<hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0 12px">'
            '<p style="font-size:12px;color:#64748b">You get this email because you agreed to hear from us. '
            f'<a href="{html.escape(unsubscribe_url)}">Unsubscribe</a> at any time.</p>'
        )
    return f'<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#0f172a;line-height:1.5">{body}{footer}</div>'


class EmailAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, out: Outbound) -> SendResult:
        text = out.text + (f"\n\n--\nUnsubscribe: {out.unsubscribe_url}" if out.unsubscribe_url else "")
        headers = {}
        if out.unsubscribe_url:
            headers = {"List-Unsubscribe": f"<{out.unsubscribe_url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
        try:
            mailer.send_email(self.settings, out.to, out.subject or "A message from us", text, email_html(out.text, out.unsubscribe_url), headers)
        except ApiError as exc:
            reason = (exc.details or {}).get("reason", "failed") if isinstance(exc.details, dict) else "failed"
            return SendResult(ok=False, error=f"email_{reason}", transient=reason in TRANSIENT_EMAIL_REASONS)
        return SendResult(ok=True, provider_id=f"email-{uuid.uuid4().hex[:16]}")


def adapter_for(channel: str, settings: Settings, dry_run: bool) -> Adapter:
    if dry_run:
        return DryRunAdapter()
    return WhatsAppAdapter(settings) if channel == "whatsapp" else EmailAdapter(settings)
