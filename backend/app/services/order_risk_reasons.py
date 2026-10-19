"""The "Why?" of an order: its top reasons, in plain language.

Each reason comes straight from the model: for every input, coefficient x the order's value
(see `contributions`). The inputs that push the order's risk up the most become the reasons.
Nothing is made up and no reason appears unless the model really used it.

A reason is a TEMPLATE plus PARAMETERS, never a finished sentence. The frontend translates the
template with its normal translation table (which looks up the exact English text), then fills
in the numbers. So a reason is translated like any other text in the app. All templates are
listed in TEMPLATES, and a test checks that every one has an Urdu translation.
"""

from dataclasses import dataclass

from app.services.order_features import OrderFeatures, OrderInput, build_order_features
from app.services.order_risk_config import MAX_REASONS, MIN_REASON_WEIGHT
from app.services.order_risk_model import OrderRiskResult, contributions

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

T_RETURNED = "Returned {returned} of {total} earlier orders"
T_NEW = "New customer: no earlier orders to learn from"
T_MANY_ORDERS = "Has {total} earlier orders"
T_VALUE = "Order value is {ratio}x this customer's usual"
T_DAYS_FEWER = "Days since the previous order: {days} (fewer than usual)"
T_DAYS_MORE = "Days since the previous order: {days} (more than usual)"
T_ITEMS_MORE = "Number of items: {count} (more than usual)"
T_ITEMS_FEWER = "Number of items: {count} (fewer than usual)"
T_PRODUCTS_MORE = "Different products: {count} (more than usual)"
T_PRODUCTS_FEWER = "Different products: {count} (fewer than usual)"
T_HOUR = "Placed around {hour}:00"
T_ADDR_SHORT = "The address is shorter than usual ({characters} characters)"
T_ADDR_LONG = "The address is longer than usual ({characters} characters)"
T_ADDR_NO_NUMBER = "The address has no house number"
T_ADDR_MISSING = "No address was provided"
T_PHONE_INVALID = "The phone number does not look valid"
T_PHONE_MISSING = "No phone number was provided"
T_COUNTRY = "Orders from {country} are returned more often in past data"
T_WEEKDAY = {day: f"Placed on a {day}" for day in WEEKDAYS}

# Every template a reason can use (the Urdu table must contain each one).
TEMPLATES = tuple(
    value for name, value in sorted(globals().items()) if name.startswith("T_") and isinstance(value, str)
) + tuple(T_WEEKDAY.values())


# Inputs that are all just "this customer has no history yet".
_NEW_CUSTOMER_INPUTS = {
    "is_new_customer",
    "missingindicator_past_cancel_rate",
    "missingindicator_days_since_previous_order",
    "missingindicator_value_vs_customer_avg",
}


@dataclass(frozen=True)
class Reason:
    code: str                    # the model input behind it, e.g. "item_count"
    template: str                # English text with {placeholders}; translated by the frontend
    params: dict[str, str]       # the numbers/names for the placeholders, already formatted
    weight: float                # how much it raised the risk (log-odds); the biggest comes first

    @property
    def text(self) -> str:
        """The English sentence (the frontend translates `template` and fills `params` itself)."""
        return self.template.format(**self.params)


def _phrase(name: str, f: OrderFeatures, contribution: float, standardised: float) -> tuple[str, dict[str, str]] | None:
    """The reason for one model input, or None when it has no sensible plain-language form.
    `standardised` > 0 means the order's value is above the usual (average) value."""
    higher = standardised > 0
    if name == "past_cancel_rate" and f.past_orders:
        return T_RETURNED, {"returned": str(round((f.past_cancel_rate or 0) * f.past_orders)), "total": str(f.past_orders)}
    if f.is_new_customer and name in _NEW_CUSTOMER_INPUTS:
        return T_NEW, {}
    if name == "past_orders" and f.past_orders and higher:
        return T_MANY_ORDERS, {"total": str(f.past_orders)}
    if name == "value_vs_customer_avg" and f.value_vs_customer_avg is not None:
        return T_VALUE, {"ratio": f"{f.value_vs_customer_avg:.1f}"}
    if name == "days_since_previous_order" and f.days_since_previous_order is not None:
        return (T_DAYS_MORE if higher else T_DAYS_FEWER), {"days": str(f.days_since_previous_order)}
    if name == "item_count" and f.item_count is not None:
        return (T_ITEMS_MORE if higher else T_ITEMS_FEWER), {"count": str(f.item_count)}
    if name == "distinct_products" and f.distinct_products is not None:
        return (T_PRODUCTS_MORE if higher else T_PRODUCTS_FEWER), {"count": str(f.distinct_products)}
    if name == "hour" and f.hour is not None:
        return T_HOUR, {"hour": str(f.hour)}
    if name == "weekday":
        return T_WEEKDAY[WEEKDAYS[f.weekday]], {}
    if name == "address_length" and f.address_length is not None:
        return (T_ADDR_LONG if higher else T_ADDR_SHORT), {"characters": str(f.address_length)}
    if name == "missingindicator_address_length" and f.address_length is None:
        return T_ADDR_MISSING, {}
    if name == "has_house_number" and f.has_house_number == 0:
        return T_ADDR_NO_NUMBER, {}
    if name == "phone_valid" and f.phone_valid == 0:
        return T_PHONE_INVALID, {}
    if name == "missingindicator_phone_valid" and f.phone_valid is None:
        return T_PHONE_MISSING, {}
    if name.startswith("country=") and f.country == name.removeprefix("country="):
        return T_COUNTRY, {"country": f.country}
    return None


def explain_orders(
    result: OrderRiskResult, orders: list[OrderInput], order_ids: set[str] | None = None
) -> dict[str, list[Reason]]:
    """Top reasons for each order (or only for `order_ids`). {} when the model is not available.
    An order whose every input is about average gets an empty list: no single reason stands out."""
    if not result.available:
        return {}
    features = build_order_features(orders)  # each order still sees only EARLIER information
    ids = [i for i in features if order_ids is None or i in order_ids]
    rows = [features[i] for i in ids]
    pushes, standardised = contributions(result, rows)

    explained: dict[str, list[Reason]] = {}
    for r, (order_id, f) in enumerate(zip(ids, rows, strict=True)):
        merged: dict[str, Reason] = {}
        for c, name in enumerate(result.feature_names):
            weight = float(pushes[r, c])
            if weight < MIN_REASON_WEIGHT:
                continue
            phrase = _phrase(name, f, weight, float(standardised[r, c]))
            if phrase is None:
                continue
            template, params = phrase
            # Several inputs can give the same reason (e.g. "new customer"): show it once.
            previous = merged.get(template)
            merged[template] = Reason(name, template, params, weight + (previous.weight if previous else 0.0))
        explained[order_id] = sorted(merged.values(), key=lambda x: -x.weight)[:MAX_REASONS]
    return explained
