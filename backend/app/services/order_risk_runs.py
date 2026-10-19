"""Save and read the results of Order Risk training runs."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order_risk_run import OrderRiskRun
from app.services.order_risk_model import OrderRiskResult


def save_run(db: Session, result: OrderRiskResult) -> OrderRiskRun:
    run = OrderRiskRun(
        # The real time of the run (not the database's transaction time), so "latest" is exact.
        created_at=datetime.now(UTC),
        decision=result.status,
        reason=result.reason,
        label_source=result.label_source,
        metric=result.metric,
        model_score=result.model_auc,
        baseline_score=result.baseline_auc,
        top_fraction=result.top_fraction,
        model_precision_top=result.model_precision_top,
        baseline_precision_top=result.baseline_precision_top,
        split_date=result.split_date,
        train_end=result.train_end,
        as_of=result.as_of,
        maturity_days=result.maturity_days,
        train_rows=result.train_rows,
        test_rows=result.test_rows,
        test_return_rate=result.test_return_rate,
    )
    db.add(run)
    db.commit()
    return run


def latest_run(db: Session) -> OrderRiskRun | None:
    return db.scalar(select(OrderRiskRun).order_by(OrderRiskRun.created_at.desc()).limit(1))
