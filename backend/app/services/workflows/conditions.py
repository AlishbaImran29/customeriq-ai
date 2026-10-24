"""Check a workflow's conditions against the facts of an event.

Pure functions, no database, and no eval: each rule is looked up in a small table of comparisons. A fact that is missing
(None) never matches, so "order total > 5000" is false for an event without an order rather than an error.
"""

from collections.abc import Callable
from typing import Any

from app.services.workflows.spec import FIELDS


def _text(x: Any) -> str:
    return str(x).strip().casefold()


_COMPARE: dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda a, b: _text(a) == _text(b) if isinstance(a, str) or isinstance(b, str) else a == b,
    "ne": lambda a, b: _text(a) != _text(b) if isinstance(a, str) or isinstance(b, str) else a != b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "in": lambda a, b: _text(a) in {_text(x) for x in b},
}


def _contains(actual: Any, wanted: Any) -> bool:
    if isinstance(actual, (list, tuple, set)):
        return _text(wanted) in {_text(x) for x in actual}
    return _text(wanted) in _text(actual)


def rule_matches(rule: dict, facts: dict[str, Any]) -> bool:
    actual = facts.get(rule["field"])
    if actual is None:
        return False
    operator, wanted = rule["operator"], rule.get("value")
    if operator == "contains":
        return _contains(actual, wanted)
    if operator == "not_contains":
        return not _contains(actual, wanted)
    try:
        return bool(_COMPARE[operator](actual, wanted))
    except TypeError:
        return False


def evaluate(conditions: dict | None, facts: dict[str, Any]) -> tuple[bool, list[dict]]:
    """(does the event match, one trace line per rule). No rules = always matches. Rules are joined by 'and' (default) or 'or'."""
    rules = (conditions or {}).get("rules") or []
    if not rules:
        return True, []
    trace = [{"field": r["field"], "label": FIELDS[r["field"]][2], "operator": r["operator"], "value": r.get("value"),
              "actual": facts.get(r["field"]), "matched": rule_matches(r, facts)} for r in rules]
    hits = [t["matched"] for t in trace]
    return (any(hits) if (conditions or {}).get("op") == "or" else all(hits)), trace


def fields_used(conditions: dict | None) -> set[str]:
    return {r["field"] for r in ((conditions or {}).get("rules") or []) if isinstance(r, dict) and r.get("field") in FIELDS}
