"""What a workflow may contain. Everything a seller can choose is listed here, and anything else is refused.

This is the allowlist that keeps the engine safe: a workflow is DATA (a trigger name, rules made of a field, an operator and a
value, and actions with parameters). No text a user types is ever run as code or evaluated as an expression.
"""

from app.models.order_status import ORDER_STATUSES

MAX_RULES = 10
MAX_ACTIONS = 8
MAX_DELAY_MINUTES = 60 * 24 * 90          # three months
MAX_DEPTH = 3                              # a workflow started by a workflow started by a workflow... stops here

# trigger -> (what the event carries, label)
TRIGGERS: dict[str, tuple[frozenset[str], str]] = {
    "customer_created": (frozenset({"customer"}), "A new customer is added"),
    "order_created": (frozenset({"customer", "order"}), "A new order is added"),
    "order_status_changed": (frozenset({"customer", "order"}), "An order's status changes"),
    "stock_below_threshold": (frozenset({"stock"}), "Stock falls to the warning level"),
    "message_received": (frozenset({"customer", "message"}), "A customer sends a WhatsApp message"),
    "customer_inactive": (frozenset({"customer"}), "A customer has not ordered for N days"),
    "schedule_daily": (frozenset(), "Every day"),
    "schedule_weekly": (frozenset(), "Every Monday"),
}

# field -> (type, what the event must carry, label). The type decides which operators make sense.
FIELDS: dict[str, tuple[str, str, str]] = {
    "order_total": ("number", "order", "Order total"),
    "order_payment_type": ("text", "order", "Payment type (cod or prepaid)"),
    "order_city": ("text", "order", "Order city"),
    "order_status": ("text", "order", "Order status"),
    "customer_orders": ("number", "customer", "Customer's number of orders"),
    "customer_total_spent": ("number", "customer", "Customer's total spend"),
    "customer_days_since_last_order": ("number", "customer", "Days since the customer's last order"),
    "customer_segment": ("text", "customer", "Customer segment"),
    "customer_tags": ("list", "customer", "Customer tags"),
    "customer_whatsapp_consent": ("bool", "customer", "Customer agreed to WhatsApp"),
    "customer_email_consent": ("bool", "customer", "Customer agreed to email"),
    "message_text": ("text", "message", "What the customer wrote"),
    "stock_available": ("number", "stock", "Units available"),
    "stock_item_name": ("text", "stock", "Stock item name"),
}

OPERATORS: dict[str, frozenset[str]] = {
    "number": frozenset({"eq", "ne", "gt", "gte", "lt", "lte"}),
    "text": frozenset({"eq", "ne", "in", "contains"}),
    "list": frozenset({"contains", "not_contains"}),
    "bool": frozenset({"eq"}),
}
OPERATOR_LABELS = {
    "eq": "is", "ne": "is not", "gt": "is more than", "gte": "is at least", "lt": "is less than", "lte": "is at most",
    "in": "is one of", "contains": "contains", "not_contains": "does not contain",
}

# action type -> (what the event must carry, label)
ACTIONS: dict[str, tuple[frozenset[str], str]] = {
    "send_message": (frozenset({"customer"}), "Send a WhatsApp or email message"),
    "add_tag": (frozenset({"customer"}), "Add a tag to the customer"),
    "remove_tag": (frozenset({"customer"}), "Remove a tag from the customer"),
    "create_task": (frozenset(), "Make a to-do for me"),
    "notify": (frozenset(), "Show me a notification"),
    "update_order_status": (frozenset({"order"}), "Change the order's status"),
    "call_webhook": (frozenset(), "Call an approved web address"),
}
CHANNELS = ("whatsapp", "email")
UPDATABLE_STATUSES = ORDER_STATUSES


def check(trigger: str, trigger_config: dict, conditions: dict, actions: list) -> list[str]:
    """Every problem with a workflow definition, in plain words. Empty list = valid."""
    problems: list[str] = []
    if trigger not in TRIGGERS:
        return [f"Unknown trigger '{trigger}'."]
    carries = TRIGGERS[trigger][0]

    if trigger == "customer_inactive":
        days = (trigger_config or {}).get("days")
        if not isinstance(days, int) or isinstance(days, bool) or not 7 <= days <= 730:
            problems.append("Choose how many days of silence (7 to 730).")

    rules = (conditions or {}).get("rules", []) if conditions else []
    if conditions and conditions.get("op", "and") not in ("and", "or"):
        problems.append("Conditions must be joined with 'and' or 'or'.")
    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        problems.append(f"At most {MAX_RULES} conditions.")
        rules = []
    for i, rule in enumerate(rules, 1):
        if not isinstance(rule, dict) or rule.get("field") not in FIELDS:
            problems.append(f"Condition {i}: unknown field.")
            continue
        kind, needs, _ = FIELDS[rule["field"]]
        if needs not in carries:
            problems.append(f"Condition {i}: '{FIELDS[rule['field']][2]}' is not known for this trigger.")
        if rule.get("operator") not in OPERATORS[kind]:
            problems.append(f"Condition {i}: '{rule.get('operator')}' cannot be used with {FIELDS[rule['field']][2]}.")
            continue
        value = rule.get("value")
        if kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
            problems.append(f"Condition {i}: the value must be a number.")
        elif kind == "bool" and not isinstance(value, bool):
            problems.append(f"Condition {i}: the value must be yes or no.")
        elif kind in ("text", "list") and rule["operator"] != "in" and (not isinstance(value, str) or not value.strip() or len(value) > 200):
            problems.append(f"Condition {i}: the value must be some text.")
        elif rule["operator"] == "in" and (not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value)):
            problems.append(f"Condition {i}: give a list of words.")

    if not isinstance(actions, list) or not actions:
        problems.append("Add at least one action.")
        return problems
    if len(actions) > MAX_ACTIONS:
        problems.append(f"At most {MAX_ACTIONS} actions.")
    for i, action in enumerate(actions[:MAX_ACTIONS], 1):
        if not isinstance(action, dict) or action.get("type") not in ACTIONS:
            problems.append(f"Action {i}: unknown action.")
            continue
        if ACTIONS[action["type"]][0] - carries:
            problems.append(f"Action {i}: '{ACTIONS[action['type']][1]}' needs a {sorted(ACTIONS[action['type']][0] - carries)[0]}, which this trigger does not have.")
        delay = action.get("delayMinutes", 0)
        if isinstance(delay, bool) or not isinstance(delay, int) or not 0 <= delay <= MAX_DELAY_MINUTES:
            problems.append(f"Action {i}: the wait must be between 0 minutes and 90 days.")
        problems.extend(_check_params(i, action["type"], action.get("params") or {}))
    return problems


def _check_params(i: int, kind: str, p: dict) -> list[str]:
    out = []
    text = lambda key, limit=200: isinstance(p.get(key), str) and 0 < len(p[key].strip()) <= limit  # noqa: E731
    if kind == "send_message":
        if p.get("channel") not in CHANNELS:
            out.append(f"Action {i}: choose WhatsApp or email.")
        if not text("event", 60):
            out.append(f"Action {i}: choose which message (template event) to send.")
    elif kind in ("add_tag", "remove_tag") and not text("tag", 30):
        out.append(f"Action {i}: write the tag (up to 30 characters).")
    elif kind in ("create_task", "notify") and not text("title"):
        out.append(f"Action {i}: write the title.")
    elif kind == "update_order_status" and p.get("status") not in UPDATABLE_STATUSES:
        out.append(f"Action {i}: choose a status.")
    elif kind == "call_webhook" and not (isinstance(p.get("url"), str) and p["url"].startswith("https://")):
        out.append(f"Action {i}: the web address must start with https://.")
    return out
