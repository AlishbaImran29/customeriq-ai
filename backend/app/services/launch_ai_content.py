"""AI helpers for Launch Studio steps 2-4: the vendor message, the competitor-ad analysis, and ad creatives.

Shared rules (the same as the Trend Finder ideas):
- It reuses the assistant's AI connection; there is no new key. Every call goes through `run_cached`, so the
  same inputs are never paid for twice, and a missing key or a failed call gives a clear error.
- Every AI text is an "AI suggestion". The seller can edit it, and nothing is sent, published or saved as
  final until the seller chooses to. The app never sends a message by itself.
- NOTHING IS INVENTED. Prompts forbid made-up numbers, reviews, testimonials, "sold" counts and fake
  scarcity, and the answers are CHECKED in code afterwards: `unprovable_claim` removes any ad text that still
  makes such a claim, and numbers in the competitor analysis must appear in what the seller saved.
"""

import re

from app.core.errors import ApiError
from app.services.launch_ai import parse_json_object

KIND_VENDOR_MESSAGE = "vendor_message"
KIND_AD_ANALYSIS = "ad_analysis"
KIND_CREATIVES = "creatives"
KIND_CREATIVE_ONE = "creative_one"

LANGUAGES = {"ur": "Urdu (in Urdu script)", "roman_ur": "Roman Urdu (Urdu written in English letters)", "en": "English"}

NO_INVENTION = (
    "Rules: use ONLY the facts you are given. Do NOT invent numbers, prices, discounts, delivery times, stock "
    "levels, customer reviews, testimonials, star ratings, awards, or how many were sold or how many customers "
    "you have. Do not claim anything that was not given."
)


def _bad(message: str = "The AI did not answer in the expected format. Please try again.") -> ApiError:
    return ApiError(502, "ai_bad_answer", message)


def _text(value, low: int, high: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"[ \t]+", " ", value).strip()
    return cleaned if low <= len(cleaned) <= high else None


# --- claims that cannot be proven -------------------------------------------------------------

_CLAIMS = re.compile(
    r"\b\d[\d,.]*\s*\+?\s*[kKmM]?\s*(?:sold|customers?|orders?|reviews?|buyers?|ratings?|happy|sales)\b"   # "5000 sold", "10k customers"
    r"|\bonly\s+\d+\s+(?:left|pieces?|units?|remaining|in stock)\b"                                          # invented scarcity
    r"|\btestimonials?\b|\bverified buyers?\b|\bcustomers? (?:say|love|rated)\b|\breviews? say\b"
    r"|\b(?:5|five)[\s-]*stars?\b|★|⭐|\brated\s+\d|\bbest[\s-]?sellers?\b|\bas seen on\b|(?<!\w)#1\b",
    re.IGNORECASE,
)


def unprovable_claim(text: str) -> bool:
    """True when the text makes a claim the seller never provided: a sold count, a review, a rating, fake scarcity."""
    return bool(_CLAIMS.search(text))


# --- step 2: the message to a vendor --------------------------------------------------------------


VENDOR_MESSAGE_INSTRUCTIONS = (
    "You write a short, polite WhatsApp message from a small online seller in Pakistan to a supplier, asking "
    "for a quote. Mention the product and the quantity the seller is thinking of, and ask for: the price per "
    "piece, the minimum order quantity, the delivery time, whether a sample is possible, and the payment terms. "
    "Keep it under 90 words, friendly and respectful, with a greeting. No links. " + NO_INVENTION + " Write in: {language}. "
    'Answer with JSON only: {{"message":"..."}}'
)


def vendor_message_instructions(language: str) -> str:
    return VENDOR_MESSAGE_INSTRUCTIONS.format(language=LANGUAGES[language])


def check_vendor_message(text: str) -> dict:
    data = parse_json_object(text)
    message = _text(data.get("message") if data else None, 20, 900)
    if message is None:
        raise _bad()
    if re.search(r"https?://|www\.", message, re.IGNORECASE):
        raise _bad("The AI included a link, which is not allowed in this message. Please try again.")
    return {"message": message}


# --- step 3: competitor ads ---------------------------------------------------------------------

HOOK_TYPES = ("question", "problem", "discount", "social_proof", "urgency", "benefit", "curiosity", "other")
AD_LANGUAGES = ("urdu", "roman_urdu", "english", "mixed", "other")

AD_ANALYSIS_INSTRUCTIONS = (
    "You study competitor ads that a seller saved while researching a product. For EACH ad give: hook_type "
    "(one of: " + ", ".join(HOOK_TYPES) + "), offer (what is offered, or null), price (a number copied from the ad "
    "text or the saved price, or null if none was given), cta (the call to action wording, or null), "
    "cod_mentioned (true only if the ad mentions cash on delivery), language (one of: " + ", ".join(AD_LANGUAGES) + "). "
    "Then write a summary: 'patterns' (what the ads have in common) and 'gaps' (what none of them do that this "
    "seller could use), each 1 to 5 short sentences. " + NO_INVENTION +
    ' Answer with JSON only: {"ads":[{"id":1,"hook_type":"","offer":null,"price":null,"cta":null,"cod_mentioned":false,"language":""}],'
    '"summary":{"patterns":[""],"gaps":[""]}}'
)


def _numbers_in(text: str) -> set[float]:
    found = set()
    for token in re.findall(r"\d[\d,]*(?:\.\d+)?", text or ""):
        try:
            found.add(float(token.replace(",", "")))
        except ValueError:
            continue
    return found


def make_ad_analysis_checker(ads: list[dict]):
    """A checker for the model's answer, knowing which ads were sent (so every number can be verified)."""
    by_id = {a["id"]: a for a in ads}

    def check(text: str) -> dict:
        data = parse_json_object(text)
        rows, summary = (data or {}).get("ads"), (data or {}).get("summary")
        if not isinstance(rows, list) or not isinstance(summary, dict):
            raise _bad()
        cleaned = []
        for row in rows:
            if not isinstance(row, dict) or row.get("id") not in by_id:
                continue
            source = by_id[row["id"]]
            hook = row.get("hook_type") if row.get("hook_type") in HOOK_TYPES else "other"
            language = row.get("language") if row.get("language") in AD_LANGUAGES else "other"
            allowed = _numbers_in(source.get("ad_text", "")) | ({float(source["price"])} if source.get("price") is not None else set())
            price = row.get("price")
            price = float(price) if isinstance(price, (int, float)) and not isinstance(price, bool) and float(price) in allowed else None
            cleaned.append({
                "id": row["id"], "hook_type": hook, "language": language, "price": price,
                "offer": _text(row.get("offer"), 2, 200), "cta": _text(row.get("cta"), 2, 80),
                "cod_mentioned": row.get("cod_mentioned") is True,
            })
        if not cleaned:
            raise _bad("The AI did not give a usable analysis. Please try again.")
        lists = {}
        for key in ("patterns", "gaps"):
            items = [_text(x, 5, 300) for x in summary.get(key, [])] if isinstance(summary.get(key), list) else []
            lists[key] = [x for x in items if x][:5]
        if not lists["patterns"] and not lists["gaps"]:
            raise _bad("The AI did not give a usable summary. Please try again.")
        return {"ads": cleaned, **lists}

    return check


# --- step 4: creatives ---------------------------------------------------------------------------

ANGLES = ("price", "quality", "urgency", "social_proof", "cod_trust")
MAX_META_ADS = 5

CREATIVES_INSTRUCTIONS = (
    "You write ad copy for a small online seller in Pakistan who sells with cash on delivery. Write in the "
    "requested language and tone. Produce: 'meta_ads': exactly 5 different Facebook/Instagram ads, each with "
    "hook (the first line that stops the scroll), primary_text (the body, short, can use line breaks), headline, "
    "cta (a short button wording such as Order Now) and angle (one of: " + ", ".join(ANGLES) + "; use each angle at "
    "most once; 'social_proof' may only use facts that were given, such as cash on delivery being offered); "
    "'instagram': {caption, hashtags (up to 12, each starting with #)}; 'whatsapp_status': one short status text. "
    "If competitor findings are given, use their gaps to stand out, but never copy their wording. " + NO_INVENTION +
    ' Answer with JSON only: {"meta_ads":[{"hook":"","primary_text":"","headline":"","cta":"","angle":""}],'
    '"instagram":{"caption":"","hashtags":[""]},"whatsapp_status":""}'
)

CREATIVE_ONE_INSTRUCTIONS = (
    "Write ONE new version of the following ad content for a small online seller in Pakistan who sells with cash on "
    "delivery, different from the earlier version you are shown. " + NO_INVENTION + " Answer with JSON only, in the same "
    "shape as the earlier version."
)


def check_meta_ad(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    hook, body = _text(item.get("hook"), 3, 200), _text(item.get("primary_text"), 5, 1200)
    headline, cta = _text(item.get("headline"), 2, 100), _text(item.get("cta"), 2, 40)
    angle = item.get("angle")
    if not (hook and body and headline and cta) or angle not in ANGLES:
        return None
    if any(unprovable_claim(part) for part in (hook, body, headline, cta)):
        return None
    return {"hook": hook, "primary_text": body, "headline": headline, "cta": cta, "angle": angle}


def check_instagram(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    caption = _text(item.get("caption"), 5, 2000)
    tags = []
    for raw in item.get("hashtags", []) if isinstance(item.get("hashtags"), list) else []:
        tag = "#" + re.sub(r"[^\w]", "", str(raw))
        if len(tag) > 1 and tag not in tags:
            tags.append(tag[:50])
    if not caption or unprovable_claim(caption):
        return None
    return {"caption": caption, "hashtags": tags[:12]}


def check_whatsapp_status(item) -> dict | None:
    value = _text(item, 3, 700)
    return {"text": value} if value and not unprovable_claim(value) else None


def check_creatives(text: str) -> dict:
    """All creatives. Items that make unprovable claims are removed and counted, never shown."""
    data = parse_json_object(text)
    if not data or not isinstance(data.get("meta_ads"), list):
        raise _bad()
    ads = [check_meta_ad(i) for i in data["meta_ads"]]
    kept = [a for a in ads if a][:MAX_META_ADS]
    instagram, status = check_instagram(data.get("instagram")), check_whatsapp_status(data.get("whatsapp_status"))
    dropped = (len(ads) - len(kept)) + (0 if instagram else 1) + (0 if status else 1)
    if not kept and not instagram and not status:
        raise _bad("The AI did not give usable ad copy. Please try again.")
    return {"meta_ads": kept, "instagram": instagram, "whatsapp_status": status, "removed": dropped}


def make_one_checker(kind: str):
    """Check a single regenerated item: kind is meta_ad, instagram or whatsapp_status."""

    def check(text: str) -> dict:
        data = parse_json_object(text)
        if kind == "whatsapp_status":
            item = check_whatsapp_status((data or {}).get("whatsapp_status") or (data or {}).get("text"))
        elif kind == "instagram":
            item = check_instagram((data or {}).get("instagram") or data)
        else:
            item = check_meta_ad((data or {}).get("meta_ad") or data)
        if item is None:
            raise _bad("The AI answer could not be used (it was incomplete or made a claim that cannot be proven). Please try again.")
        return item

    return check
