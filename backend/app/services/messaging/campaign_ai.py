"""The AI draft of a campaign's messages (project rules 3 and 4).

ONE AI call writes the base message of every segment, in English and Urdu, plus an email subject in each language. That
keeps the cost low (a campaign for 2,000 customers is still one call) and it is cached, so asking again for the same
product, offer and segments costs nothing. The per-customer parts (name, last purchase) are filled in by code, not by AI.

The answer is an "AI draft": the seller reads and edits it, and nothing is sent until they approve. It is also CHECKED
in code before the seller even sees it:
- only known {{variables}} may appear (and {{price}} / {{offer_text}} only when there is a price / an offer);
- no claim that cannot be proven (a "sold" count, reviews, fake scarcity: launch_ai_content.unprovable_claim);
- no discount, "free" or "sale" wording unless the seller typed an offer (an invented discount is refused).
"""

import re

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import Campaign, CatalogProduct
from app.services.launch_ai import parse_json_object, run_cached
from app.services.launch_ai_content import NO_INVENTION, unprovable_claim
from app.services.messaging import campaigns
from app.services.messaging.render import check_template_text, variables_in

KIND = "campaign_messages"
MAX_MESSAGE = 600
MAX_SUBJECT = 100

SEGMENT_HINTS = {
    "champions": "the shop's best customers: give them early access and thank them",
    "loyal": "regular, loyal customers: a warm thank-you and the new product",
    "potential": "customers who could become regulars: a friendly invitation to buy again",
    "at_risk": "customers who have not bought for a while: a warm, low-pressure win-back",
    "lost": "customers gone quiet for a long time: one gentle reminder, no pressure",
    "other": "customers of the shop: a friendly announcement",
}

INSTRUCTIONS = (
    "You write short WhatsApp announcements of a NEW PRODUCT for a small online seller in Pakistan. For EACH customer "
    "segment given, write ONE message in English AND ONE in Urdu (Urdu script), under 400 characters, with a friendly, "
    "personal tone suited to that segment. Also write one short email subject in each language.\n"
    "Use ONLY these placeholders, exactly like this: {{first_name}}, {{product_name}}, {{store_name}}, "
    "{{last_purchase_line}} (a ready sentence about the customer's last purchase; it may be empty, so write it on its own line), "
    "{{price}} (ONLY if a price is given), {{offer_text}} (ONLY if an offer is given). Never write a customer's name or product "
    "yourself: use the placeholders. " + NO_INVENTION + " Do not invent discounts, deadlines, stock levels or product features: use only the description "
    "given. If no offer is given, do not mention any discount, sale or free item. Do not mention opting out: that is added for you.\n"
    'Answer with JSON only: {"messages":{"<segment>":{"en":"...","ur":"..."}},"subject":{"en":"...","ur":"..."}}'
)


def _bad(message: str = "The AI did not answer in the expected format. Please try again.") -> ApiError:
    return ApiError(502, "ai_bad_answer", message)


def make_checker(segments: list[str], has_price: bool, offer_text: str | None):
    def check(text: str) -> dict:
        data = parse_json_object(text)
        messages, subject = (data or {}).get("messages"), (data or {}).get("subject")
        if not isinstance(messages, dict) or not isinstance(subject, dict):
            raise _bad()
        clean: dict[str, dict[str, str]] = {}
        for key in segments:
            entry = messages.get(key)
            if not isinstance(entry, dict):
                raise _bad(f"The AI did not write a message for the {key} segment. Please try again.")
            clean[key] = {}
            for language in campaigns.LANGUAGES:
                body = entry.get(language)
                if not isinstance(body, str) or not (10 <= len(body.strip()) <= MAX_MESSAGE):
                    raise _bad(f"The {language.upper()} message for {key} was missing or the wrong length. Please try again.")
                body = body.strip()
                _check_body(body, has_price, offer_text)
                clean[key][language] = body
        clean_subject = {}
        for language in campaigns.LANGUAGES:
            line = subject.get(language)
            if not isinstance(line, str) or not (3 <= len(line.strip()) <= MAX_SUBJECT):
                raise _bad("The email subject was missing or the wrong length. Please try again.")
            _check_body(line.strip(), has_price, offer_text)
            clean_subject[language] = " ".join(line.split())
        return {"messages": clean, "subject": clean_subject}

    return check


def _check_body(body: str, has_price: bool, offer_text: str | None) -> None:
    try:
        check_template_text(body)
    except ApiError as error:
        raise _bad(f"The AI used something that is not allowed ({error.message}). Please try again.") from None
    used = set(variables_in(body))
    if "price" in used and not has_price:
        raise _bad("The AI used a price, but this product has none. Please try again.")
    if "offer_text" in used and not (offer_text or "").strip():
        raise _bad("The AI mentioned an offer you did not give. Please try again.")
    if unprovable_claim(body) or campaigns.invents_an_offer(re.sub(r"\{\{[^}]*\}\}", "", body), offer_text):
        raise _bad("The AI made a claim or an offer that was not given to it, so the draft was thrown away. Please try again.")


def build_inputs(campaign: Campaign, product: CatalogProduct | None, segments: list[str], store_name: str | None) -> dict:
    """The facts sent to the AI. Kept short, and the same facts always give the same cache key."""
    return {
        "product": {"name": product.name if product else campaign.name, "category": product.category if product else None,
                    "price_given": bool(product and product.price is not None), "description": (product.description if product else None)},
        "offer": (campaign.offer_text or "").strip() or None, "shop": store_name or None,
        "segments": {key: SEGMENT_HINTS.get(key, SEGMENT_HINTS["other"]) for key in segments},
    }


def generate(db: Session, settings: Settings, campaign: Campaign, product: CatalogProduct | None, segments: list[str], store_name: str | None, *, force: bool):
    """The AI draft for the given segment keys. Returns (messages dict, from_cache, model)."""
    return run_cached(
        db, settings, KIND, build_inputs(campaign, product, segments, store_name), INSTRUCTIONS,
        make_checker(segments, bool(product and product.price is not None), campaign.offer_text), force=force,
    )
