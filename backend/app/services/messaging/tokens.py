"""Signed unsubscribe links for email.

The link carries the customer and the channel plus a signature made with MESSAGING_SECRET. Without the secret
nobody can make a valid link, so nobody can unsubscribe someone else by guessing numbers. The signature uses
HMAC-SHA256 and is compared in constant time.
"""

import base64
import hashlib
import hmac

from app.core.config import Settings


def _signature(secret: str, customer_id: int, channel: str) -> str:
    return hmac.new(secret.encode(), f"unsubscribe:{customer_id}:{channel}".encode(), hashlib.sha256).hexdigest()[:32]


def make_unsubscribe_token(settings: Settings, customer_id: int, channel: str) -> str | None:
    """The token for a link, or None when MESSAGING_SECRET is not set (the caller then refuses to send marketing email)."""
    if not settings.messaging_secret or not settings.messaging_secret.get_secret_value().strip():
        return None
    raw = f"{customer_id}.{channel}.{_signature(settings.messaging_secret.get_secret_value(), customer_id, channel)}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def read_unsubscribe_token(settings: Settings, token: str) -> tuple[int, str] | None:
    """(customer id, channel) when the token is genuine, else None."""
    if not settings.messaging_secret or not settings.messaging_secret.get_secret_value().strip():
        return None
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        customer, channel, signature = raw.split(".")
        customer_id = int(customer)
    except (ValueError, UnicodeDecodeError):
        return None
    expected = _signature(settings.messaging_secret.get_secret_value(), customer_id, channel)
    if channel not in ("email", "whatsapp") or not hmac.compare_digest(signature, expected):
        return None
    return customer_id, channel


def unsubscribe_link(settings: Settings, customer_id: int, channel: str = "email") -> str | None:
    token = make_unsubscribe_token(settings, customer_id, channel)
    base = (settings.public_api_url or "").rstrip("/")
    return f"{base}/api/v1/unsubscribe?token={token}" if token and base else None
