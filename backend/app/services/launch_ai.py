"""Launch Studio AI helper: "Ask AI for ideas".

It REUSES the AI assistant's connection (`get_model`, the same provider and API key as the chat), so there
is no new key and no new library. Rules for every AI text in Launch Studio:
- It is only ever shown as an "AI suggestion". The seller can change it and nothing is used until they
  accept it (one click turns an idea into a launch project, with the name editable first).
- The prompt forbids invented numbers, customer reviews, testimonials and "sold" counts.
- Cost is kept low: a short prompt, and the answer is cached under a fingerprint of the inputs
  (table ai_cache), so asking the same question again costs nothing.
- If the key is missing or the call fails, get_model / the model raise a clear ApiError.
"""

import hashlib
import json
import re

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.launch import AiCache
from app.services.assistant import ChatTurn, get_model

KIND_IDEAS = "launch_ideas"
MAX_IDEAS = 5
NAME_LENGTH = (2, 80)
REASON_LENGTH = (5, 220)

INSTRUCTIONS = (
    "You help a small online seller in Pakistan choose products to launch. You are given search-interest "
    "trends (from Google Trends files the seller uploaded) and the categories and best-growing products "
    "from the seller's own shop. Suggest exactly 5 different product ideas that a small seller can source "
    "and sell with cash on delivery.\n"
    "Rules: use only the facts you are given. Do NOT invent numbers, prices, search volumes, customer "
    "reviews, testimonials or how many were sold. Each reason is ONE short sentence that points to a fact "
    "from the input (for example a rising keyword).\n"
    'Answer with JSON only, no other text, exactly in this shape: {"ideas":[{"name":"...","reason":"..."}]}'
)


def build_inputs(trends: list[dict], categories: list[str], growing: list[str]) -> dict:
    """The facts sent to the model: kept short on purpose (cheaper, and nothing private such as names or phones)."""
    return {
        "trends": [
            {
                "keyword": t["keyword"], "label": t.get("label"),
                "related": [r["query"] for r in (t.get("related") or [])[:5]],
            }
            for t in trends[:5]
        ],
        "shop_categories": categories[:10],
        "shop_growing_products": growing[:8],
    }


def validate_ideas(text: str) -> list[dict]:
    """Turn the model's answer into a clean list of ideas, or raise a plain error if it cannot be trusted."""
    data = parse_json_object(text)
    ideas = data.get("ideas") if isinstance(data, dict) else None
    if not isinstance(ideas, list):
        raise ApiError(502, "ai_bad_answer", "The AI did not answer in the expected format. Please try again.")
    result, seen = [], set()
    for item in ideas:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("reason"), str):
            continue
        name, reason = re.sub(r"\s+", " ", item["name"]).strip(), re.sub(r"\s+", " ", item["reason"]).strip()
        if not (NAME_LENGTH[0] <= len(name) <= NAME_LENGTH[1] and REASON_LENGTH[0] <= len(reason) <= REASON_LENGTH[1]):
            continue
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        result.append({"name": name, "reason": reason})
    if not result:
        raise ApiError(502, "ai_bad_answer", "The AI did not give usable ideas. Please try again.")
    return result[:MAX_IDEAS]


def cache_key(kind: str, inputs: dict) -> str:
    return hashlib.sha256((kind + json.dumps(inputs, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()


def parse_json_object(text: str) -> dict | None:
    """The first JSON object in a model answer (tolerates code fences and a sentence around it), or None."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        try:
            data = json.loads(cleaned[start : end + 1]) if 0 <= start < end else None
        except json.JSONDecodeError:
            data = None
    return data if isinstance(data, dict) else None


def run_cached(
    db: Session, settings: Settings, kind: str, inputs: dict, instructions: str, check, *, force: bool = False
) -> tuple[dict, bool, str | None]:
    """The one way every Launch Studio AI call is made.

    1. The answer for these exact inputs is looked up first (ai_cache): asking again costs nothing.
    2. Otherwise the model is called (a missing API key raises a clear 503), the answer is checked by
       `check(text) -> payload dict` (which raises a plain 502 if it cannot be trusted), and only a
       CHECKED answer is saved, so a bad answer is never served from the cache.
    Returns (payload, from_cache, model name).
    """
    key = cache_key(kind, inputs)
    cached = db.get(AiCache, key)
    if cached is not None and not force:
        return cached.payload["result"], True, cached.payload.get("model")
    model = get_model(settings)
    answer = model.answer(instructions, [ChatTurn("user", json.dumps(inputs, separators=(",", ":"), ensure_ascii=False))])
    result = check(answer)
    payload = {"result": result, "model": model.model}
    if cached is None:
        db.add(AiCache(key=key, kind=kind, payload=payload))
    else:
        cached.payload = payload
    db.commit()
    return result, False, model.model


def is_cached(db: Session, kind: str, inputs: dict) -> bool:
    return db.get(AiCache, cache_key(kind, inputs)) is not None


def ask_for_ideas(db: Session, settings: Settings, inputs: dict, *, force: bool = False) -> tuple[list[dict], bool, str | None]:
    """(ideas, from_cache, model name)."""
    result, cached, model = run_cached(
        db, settings, KIND_IDEAS, inputs, INSTRUCTIONS, lambda text: {"ideas": validate_ideas(text)}, force=force
    )
    return result["ideas"], cached, model
