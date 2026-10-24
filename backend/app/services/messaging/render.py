"""Fill {{variables}} into a message template.

Two promises (project rule 4: never invent facts in a message):
- Only variables from the VARIABLES list below may appear in a template. A typo is refused when the template is
  saved, not discovered when a customer receives "Hello {{frist_name}}".
- At send time every variable the template uses must have a value. A missing one stops the message (it is
  recorded as skipped, with the name of the variable). Only the OPTIONAL variables may be empty: they are
  parts of a sentence that exist for some orders and not others (the cash-on-delivery note, the tracking
  line, and so on), and an empty one is simply left out.
"""

import re
from collections.abc import Mapping

from app.core.errors import ApiError

# name -> short description (shown to the seller next to the template editor)
VARIABLES: dict[str, str] = {
    "first_name": "The customer's first name",
    "last_name": "The customer's last name",
    "store_name": "Your shop's name (from the settings)",
    "order_number": "The order number",
    "items": "The products in the order",
    "amount": "The order total, with the currency",
    "courier": "The courier's name",
    "tracking_number": "The courier's tracking number",
    "tracking_line": "A ready sentence with the courier and tracking number (empty if unknown)",
    "cod_note": "For cash on delivery: a sentence asking to keep the amount ready (empty otherwise)",
    "review_link": "Your review page link (from the settings)",
    "product_name": "The product being announced",
    "price": "The product's price, with the currency",
    "category": "The product's category",
    "last_product": "The last product this customer bought",
    "last_category": "The category this customer last bought from",
    "last_purchase_line": "A ready sentence about their last purchase (empty if unknown)",
    "segment": "The customer's segment, for example Champions",
    "offer_text": "The offer you typed for the campaign (empty if none)",
}
OPTIONAL = {"tracking_line", "cod_note", "last_product", "last_category", "last_purchase_line", "offer_text", "items"}

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
MAX_BODY = 1600                                  # WhatsApp templates allow about 1,024; email bodies can be longer
MAX_SUBJECT = 150


def variables_in(text: str) -> list[str]:
    """The variable names used in a text, in order of first appearance, without repeats."""
    seen: list[str] = []
    for name in _PLACEHOLDER.findall(text or ""):
        if name not in seen:
            seen.append(name)
    return seen


def check_template_text(body: str, subject: str | None = None) -> list[str]:
    """Variable names in the template. Raises a plain 422 for an unknown variable or text that is too long."""
    if not body.strip():
        raise ApiError(422, "invalid_template", "The message cannot be empty.", {"field": "body"})
    if len(body) > MAX_BODY:
        raise ApiError(422, "invalid_template", f"The message is longer than {MAX_BODY} characters.", {"field": "body"})
    if subject is not None and len(subject) > MAX_SUBJECT:
        raise ApiError(422, "invalid_template", f"The subject is longer than {MAX_SUBJECT} characters.", {"field": "subject"})
    names = variables_in(body) + [n for n in variables_in(subject or "") if n not in variables_in(body)]
    unknown = [n for n in names if n not in VARIABLES]
    if unknown:
        raise ApiError(
            422, "unknown_variable",
            "Unknown variable: " + ", ".join("{{" + n + "}}" for n in unknown) + ". Use only the variables listed beside the editor.",
            {"field": "body", "variables": unknown},
        )
    return names


class MissingVariable(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


def render(text: str, values: Mapping[str, str | None]) -> str:
    """The text with every {{variable}} replaced. Raises MissingVariable for a required one without a value."""

    def replace(match: re.Match) -> str:
        name = match.group(1)
        value = values.get(name)
        if value is None or str(value).strip() == "":
            if name in OPTIONAL:
                return ""
            raise MissingVariable(name)
        return str(value).strip()

    rendered = _PLACEHOLDER.sub(replace, text)
    # An optional part left out can leave a blank line or a double space behind: tidy that, keep real paragraphs.
    rendered = re.sub(r"[ \t]{2,}", " ", rendered)
    rendered = re.sub(r"[ \t]+\n", "\n", rendered)
    return re.sub(r"\n{3,}", "\n\n", rendered).strip()


def meta_style(body: str) -> tuple[str, list[str]]:
    """The body as Meta wants it for a template ({{1}}, {{2}}...) and the variable behind each number.

    The seller pastes this text into WhatsApp Manager when they create the template there; at send time the
    values are passed in the same order.
    """
    order = variables_in(body)
    index = {name: i + 1 for i, name in enumerate(order)}
    return _PLACEHOLDER.sub(lambda m: "{{" + str(index[m.group(1)]) + "}}", body), order
