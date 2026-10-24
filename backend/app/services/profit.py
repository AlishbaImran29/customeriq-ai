"""Profit Check: will this product make money before any ad money is spent? ALL the formulas live here.

Everything is simple arithmetic on numbers the seller types in, so it can be checked on a calculator.
The results are ESTIMATES that are only as good as the inputs (especially the expected return rate), and
the page labels them so. Money is in rupees.

Cash-on-delivery model used (written down so it can be explained and changed in one place):
- A DELIVERED order: the customer pays the selling price. The seller has paid the product cost, the
  packing cost and the courier fee.
      profit_delivered = price - cost - packing - courier_fee
- A RETURNED order: nothing is collected. The product comes back and goes back on the shelf, so its cost
  is NOT lost, but the packing, the courier fee out and the courier fee for the return are.
      loss_returned = packing + courier_fee + return_shipping       (a negative profit)
  ("return_shipping" is the extra cost of the parcel coming back.)
- Of every order PLACED, a share `return_rate` comes back:
      profit_per_order_placed = (1 - return_rate) * profit_delivered - return_rate * loss_returned
  This is the profit before ads. An ad has to buy each order for less than this, or the seller loses money.
- Break-even cost per purchase (Meta) = profit_per_order_placed. (A "purchase" here is an order placed.)
- Break-even ROAS = price / break-even cost per purchase: how many rupees of sales each ad rupee must
  bring so that ads exactly pay for themselves. Higher is harder.
- Orders needed to recover the ad budget = ceil(ad_budget / profit_per_order_placed).
- Warnings: profit per order placed below zero (a loss on every order), or a margin
  (profit_per_order_placed / price) below 10%.
"""

from dataclasses import dataclass, field
from math import ceil

from app.core.errors import ApiError

THIN_MARGIN = 0.10                    # below 10% of the price is "thin"
MAX_MONEY = 100_000_000.0


@dataclass(frozen=True)
class ProfitInputs:
    cost: float                        # what one unit costs the seller (from the chosen vendor quote by default)
    price: float                       # selling price
    packing: float
    courier_fee: float
    return_shipping: float
    return_rate: float                 # 0 to 1, the expected share of placed orders that come back
    ad_budget: float


@dataclass
class ProfitResult:
    profit_delivered: float
    loss_returned: float               # a positive number: what a returned order costs
    profit_per_order_placed: float
    margin: float | None               # profit_per_order_placed / price
    break_even_cost_per_purchase: float | None      # None when the product cannot make money before ads
    break_even_roas: float | None
    orders_to_recover_budget: int | None            # None when there is no budget or the product cannot make money
    warnings: list[str] = field(default_factory=list)    # codes: loss_per_order, thin_margin, loss_when_delivered, no_budget


def validate(inputs: ProfitInputs) -> None:
    """Raise a plain ApiError for numbers that cannot be real."""
    for name, value in (
        ("cost", inputs.cost), ("price", inputs.price), ("packing", inputs.packing), ("courier_fee", inputs.courier_fee),
        ("return_shipping", inputs.return_shipping), ("ad_budget", inputs.ad_budget),
    ):
        if value != value or not 0 <= value <= MAX_MONEY:
            raise ApiError(422, "invalid_amount", f"{name}: enter an amount of 0 or more.", {"field": name})
    if inputs.price <= 0:
        raise ApiError(422, "invalid_amount", "price: enter the selling price (more than 0).", {"field": "price"})
    if not 0 <= inputs.return_rate <= 1:
        raise ApiError(422, "invalid_return_rate", "return_rate: enter a share from 0 to 1 (for example 0.25 for 25%).", {"field": "return_rate"})


def calculate(inputs: ProfitInputs) -> ProfitResult:
    validate(inputs)
    delivered = inputs.price - inputs.cost - inputs.packing - inputs.courier_fee
    loss_returned = inputs.packing + inputs.courier_fee + inputs.return_shipping
    per_order = (1 - inputs.return_rate) * delivered - inputs.return_rate * loss_returned
    warnings: list[str] = []
    positive = per_order > 0
    if per_order < 0:
        warnings.append("loss_per_order")
    elif per_order / inputs.price < THIN_MARGIN:
        warnings.append("thin_margin")
    if delivered < 0:
        warnings.append("loss_when_delivered")           # even a delivered order loses money
    needed = ceil(inputs.ad_budget / per_order) if positive and inputs.ad_budget > 0 else None
    if inputs.ad_budget <= 0:
        warnings.append("no_budget")
    return ProfitResult(
        profit_delivered=round(delivered, 2),
        loss_returned=round(loss_returned, 2),
        profit_per_order_placed=round(per_order, 2),
        margin=round(per_order / inputs.price, 4),
        break_even_cost_per_purchase=round(per_order, 2) if positive else None,
        break_even_roas=round(inputs.price / per_order, 2) if positive else None,
        orders_to_recover_budget=needed,
        warnings=warnings,
    )
