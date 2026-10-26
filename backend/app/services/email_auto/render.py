"""Turns an email template plus data into subject, HTML and plain text. The wording lives in app/email_templates/.

Promise: a missing value is never shown as "None" or an empty gap. Every optional piece is wrapped in an `if` in the
template, and the helpers below return None (not "") for anything unusable, so the piece simply disappears.
"""

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "email_templates"
TEMPLATES = {
    "cod_confirmation": "COD confirmation",
    "cod_reminder": "COD reminder (after 24 hours)",
    "winback": "Win-back",
    "new_product": "New product",
}
DEFAULT_COLOR = "#2563eb"
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

# StrictUndefined: a typo in a template or a forgotten variable fails loudly in the tests instead of printing nothing.
_html_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]), undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
_text_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False, undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)

# Every variable a template may use. Optional ones default to None so that `{% if x %}` hides the piece.
DEFAULTS: dict = {
    "subject": "", "first_name": "there", "store_name": "Our Store", "store_logo_url": None, "brand_color": DEFAULT_COLOR,
    "support_email": None, "store_url": "#", "unsubscribe_url": None,
    "order_number": None, "items": [], "order_total": None, "delivery_city": None, "confirm_url": "#", "cancel_url": "#",
    "last_product_name": None, "days_since_last_order": None, "recommended_products": [], "discount_code": None, "discount_value": None,
    "product_name": "our newest arrival", "product_image": None, "product_price": None, "product_url": "#", "product_description": None, "same_category": False,
}


def price(value) -> str | None:
    """3500 -> "Rs. 3,500" (paisa only when there are some). None for a missing value."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return f"Rs. {number:,.0f}" if number == int(number) else f"Rs. {number:,.2f}"


def first_name(raw: str | None) -> str:
    """"mary-anne" -> "Mary-Anne". A name that already mixes cases ("McDonald") is kept. Missing -> "there"."""
    name = " ".join((raw or "").split()).split(" ")[0] if (raw or "").strip() else ""
    if not name:
        return "there"
    return re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), name) if name.islower() or name.isupper() else name


def clean_url(value: str | None) -> str | None:
    """Only web addresses go into images and buttons (never javascript: or data:)."""
    value = (value or "").strip()
    return value if re.match(r"^https?://\S+$", value, re.I) else None


def clean_color(value: str | None) -> str:
    return value if value and _COLOR.match(value) else DEFAULT_COLOR


def short(text: str | None, limit: int = 160) -> str | None:
    """A description cut to about two lines, at a word boundary."""
    text = " ".join((text or "").split())
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "..."


def render(template: str, data: dict) -> tuple[str, str, str]:
    """(subject, html, text). `data` is merged over DEFAULTS; unknown keys are an error in the template, not here."""
    if template not in TEMPLATES:
        raise ValueError(f"unknown email template {template}")
    context = {**DEFAULTS, **{k: v for k, v in data.items() if v is not None}}
    subject = " ".join(_text_env.get_template(f"{template}.subject").render(context).split())
    context["subject"] = subject
    html = _html_env.get_template(f"{template}.html").render(context)
    text = _text_env.get_template(f"{template}.txt").render(context)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return subject, html, text


def sample_data(template: str) -> dict:
    """Made-up data for the previews and the test emails."""
    base = {
        "first_name": "Ayesha", "store_name": "Sample Store", "support_email": "support@example.com", "store_url": "https://example.com",
        "brand_color": DEFAULT_COLOR,
    }
    picks = [
        {"name": "Classic Leather Wallet", "price": price(2500), "image": "https://placehold.co/160x160/e2e8f0/475569?text=Wallet", "url": "https://example.com/wallet"},
        {"name": "Canvas Weekender Bag", "price": price(4800), "image": "https://placehold.co/160x160/e2e8f0/475569?text=Bag", "url": "https://example.com/bag"},
        {"name": "Everyday Sneakers", "price": price(6200), "image": "https://placehold.co/160x160/e2e8f0/475569?text=Shoes", "url": "https://example.com/shoes"},
    ]
    if template in ("cod_confirmation", "cod_reminder"):
        return {**base, "order_number": "1042", "delivery_city": "Lahore", "order_total": price(8700), "confirm_url": "https://example.com/confirm", "cancel_url": "https://example.com/cancel",
                "items": [{"name": "Everyday Sneakers", "quantity": 1, "price": price(6200), "image": picks[2]["image"]}, {"name": "Classic Leather Wallet", "quantity": 1, "price": price(2500), "image": picks[0]["image"]}]}
    if template == "winback":
        return {**base, "last_product_name": "Everyday Sneakers", "days_since_last_order": 94, "recommended_products": picks, "discount_code": "COMEBACK10", "discount_value": "10%", "unsubscribe_url": "https://example.com/unsubscribe"}
    return {**base, "product_name": "Weekender Duffel", "product_price": price(5400), "product_image": "https://placehold.co/536x300/e2e8f0/475569?text=New+arrival",
            "product_url": "https://example.com/duffel", "product_description": "A roomy, water-resistant duffel with a padded shoulder strap, made for short trips.", "same_category": True, "unsubscribe_url": "https://example.com/unsubscribe"}
