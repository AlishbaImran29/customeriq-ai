"""Cached AI calls for the Auto Messenger campaign drafts.

It uses the shared AI connection (`llm.get_model`: one provider and one API key). The answer is cached under a
fingerprint of the inputs (table ai_cache), so asking the same question again costs nothing. If the key is missing or
the call fails, get_model / the model raise a clear ApiError.
"""

import hashlib
import json
import re

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.ai_cache import AiCache
from app.services.llm import ChatTurn, get_model


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
    """The one way every AI call is made.

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
