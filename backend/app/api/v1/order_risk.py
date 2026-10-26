"""Order Risk Check: which recent orders look likely to come back, and why."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.models import Order
from app.models.cod_confirmation import CodConfirmation
from app.schemas.analytics import Meta, ModelInfo, ModelsMeta
from app.schemas.order_risk import (
    OrderRiskModelOut,
    OrderRiskOut,
    OrderRiskRowOut,
    ReasonOut,
    SavingsCountsOut,
)
from app.services import order_risk_config as config
from app.services import order_risk_reasons as reasons
from app.services.order_risk_savings import SavingsEstimate
from app.services.order_risk_service import OrderRiskReport, get_order_risk

logger = logging.getLogger(__name__)
router = APIRouter(tags=["order-risk"])


def _savings(est: SavingsEstimate | None) -> SavingsCountsOut | None:
    if est is None:
        return None
    return SavingsCountsOut(
        flagged_levels=list(est.flagged_levels),
        test_start=est.test_start,
        test_end=est.test_end,
        test_orders=est.test_orders,
        flagged_orders=est.flagged_orders,
        flagged_returned=est.flagged_returned,
        false_alarms=est.false_alarms,
        total_returned=est.total_returned,
    )


_ORDER = {"Low": 0, "Medium": 1, "High": 2}


def _raise(level: str) -> str:
    return {"Low": "Medium", "Medium": "High", "High": "High"}[level]


def row_action(row, raised: dict[str, str]) -> str:
    return config.RISK_ACTIONS[raised[row.order_id]] if row.order_id in raised else row.action


def _no_reply_reason(row, raised: dict[str, str]) -> list[ReasonOut]:
    if row.order_id not in raised:
        return []
    return [ReasonOut(template=reasons.T_COD_NO_REPLY, params={}, text=reasons.T_COD_NO_REPLY)]


def _out(report: OrderRiskReport, limit: int, no_reply: frozenset[str] = frozenset()) -> OrderRiskOut:
    r = report.result
    # Orders whose customer never answered the COD confirmation: a plain rule (not the model) raises them one level, and says so.
    raised = {row.order_id: _raise(row.level) for row in report.rows if row.order_id in no_reply}
    counts = dict(report.level_counts)
    for row in report.rows:
        if row.order_id in raised and raised[row.order_id] != row.level:
            counts[row.level] -= 1
            counts[raised[row.order_id]] += 1
    not_used = ModelInfo(status="unavailable", reason="Not used on this page.", metrics=[])
    return OrderRiskOut(
        meta=Meta(
            as_of=report.as_of,
            customer_count=report.customer_count,
            segmented=True,
            models=ModelsMeta(churn=not_used),
            unavailable=[],
        ),
        model=OrderRiskModelOut(
            status=r.status, reason=r.reason, metric=r.metric,
            model_score=r.model_auc, baseline_score=r.baseline_auc,
            model_precision_top=r.model_precision_top, baseline_precision_top=r.baseline_precision_top,
            top_fraction=r.top_fraction, split_date=r.split_date, train_end=r.train_end, as_of=r.as_of,
            maturity_days=r.maturity_days, train_rows=r.train_rows, test_rows=r.test_rows,
            test_return_rate=r.test_return_rate, label_source=r.label_source,
            low_below=config.RISK_LOW_BELOW, high_above=config.RISK_HIGH_ABOVE,
        ),
        window_days=config.RECENT_DAYS,
        window_start=report.window_start,
        window_orders=report.window_orders,
        level_counts=counts,
        orders=[
            OrderRiskRowOut(
                order_id=row.order_id, order_date=row.order_date, customer_id=row.customer_id,
                customer_name=row.customer_name, amount=row.amount, probability=row.probability,
                level=raised.get(row.order_id, row.level), action=row_action(row, raised), whatsapp_phone=row.whatsapp_phone,
                reasons=[ReasonOut(template=x.template, params=x.params, text=x.text) for x in row.reasons] + _no_reply_reason(row, raised),
            )
            for row in sorted(report.rows, key=lambda r: (-_ORDER[raised.get(r.order_id, r.level)], -r.order_date.toordinal(), -r.probability))[:limit]
        ],
        truncated=len(report.rows) > limit,
        savings_high=_savings(report.savings_high),
        savings_medium_high=_savings(report.savings_medium_high),
    )


@router.get("/order-risk", response_model=OrderRiskOut)
def order_risk(
    limit: int = Query(config.DEFAULT_TABLE_ROWS, ge=1, le=config.MAX_TABLE_ROWS),
    db: Session = Depends(get_db),
) -> OrderRiskOut:
    """Risk of each recent order being returned, only when the model passed the trust rule.

    When it did not, `model.status` is "unavailable" with the reason and both scores, and there
    are no orders and no savings: no number is shown that was not earned."""
    try:
        report = get_order_risk(db)
    except ProgrammingError as exc:
        # A missing column or table: the database was not updated for this feature yet.
        db.rollback()
        logger.error("Order Risk needs a database update: %s", type(exc.orig).__name__)
        raise ApiError(
            503,
            "database_out_of_date",
            "The database has not been updated for Order Risk yet. Run scripts/migrate_remote.py "
            "(see docs/DEPLOY.md), then import the orders file again.",
        ) from exc
    no_reply = frozenset(db.scalars(
        select(Order.external_id).join(CodConfirmation, CodConfirmation.order_id == Order.id).where(CodConfirmation.state == "needs_call")
    ))
    return _out(report, limit, no_reply)
