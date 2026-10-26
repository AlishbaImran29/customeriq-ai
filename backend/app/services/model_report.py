"""The Model Report Card: every model's score next to its simple baseline, and the trust rule's decision.

The scores come from the training that already happens (churn, CLV, revenue forecast: services/predictions.py; Order Risk:
the saved runs; Season Forecast: its back-test). Nothing is recomputed differently here, so the card cannot disagree with
the pages. Each time the card is built, a new history line is saved for a model whose decision or scores changed. That is
the "auto re-test" record: after an import the models retrain by themselves, and if one no longer beats its baseline it is
hidden everywhere and the reason is kept here.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.model_report import ModelReport
from app.services import predictions as pr
from app.services.analytics_data import load_snapshot
from app.services.order_risk_runs import latest_run

# A score that moved by less than this is not a new line in the history.
_SAME = 1e-6


@dataclass
class Row:
    model: str
    label: str
    decision: str  # "shown" | "hidden"
    reason: str | None = None
    metric: str | None = None
    model_score: float | None = None
    baseline_score: float | None = None
    higher_is_better: bool = True
    test_size: int | None = None
    split_date: date | None = None


def _from_result(model: str, label: str, r: pr.ModelResult) -> Row:
    return Row(
        model, label, "shown" if r.available else "hidden", r.reason, r.metric, r.model_score, r.baseline_score,
        r.higher_is_better, r.test_size, r.split_date,
    )


def _order_risk_row(db: Session) -> Row:
    run = latest_run(db)
    if run is None:
        return Row("order_risk", "Order Risk", "hidden", "Not trained yet: open the Order Risk page once.", "ROC-AUC")
    return Row(
        "order_risk", "Order Risk", "shown" if run.decision == "available" else "hidden", run.reason, run.metric,
        run.model_score, run.baseline_score, True, run.test_rows, run.split_date,
    )


_SEASON_REASONS = {
    "not_better": "The model did not beat last year's sales on past seasons.",
    "no_backtest": "Not enough past seasons to test the model.",
    "too_early": "Too early for this season: the forecast date has not arrived yet.",
}


def _season_rows(db: Session) -> list[Row]:
    from app.services.product_sales_import import load_weekly_sales
    from app.services.season_forecast import forecast_seasons
    from app.services.seasons import SEASONS

    try:
        _, _, _, sales = load_weekly_sales(db, "auto")
        results = forecast_seasons(sales, SEASONS)
    except Exception:  # no sales yet, or the table is not migrated: the card still shows the other models
        return []
    rows = []
    for r in results:
        b = r.backtest
        if not b.cases:
            continue
        rows.append(Row(
            f"season:{r.season_id}", f"Season Forecast: {r.name}", "shown" if r.status == "forecast" else "hidden",
            None if r.status == "forecast" else _SEASON_REASONS.get(r.reason or "", r.reason), "MAE (units)", b.model_mae, b.baseline_mae,
            False, b.rows, None,
        ))
    return rows


def current_rows(db: Session) -> list[Row]:
    snapshot = load_snapshot(db)
    if snapshot.empty:
        none = pr.ModelResult.unavailable("No customer data has been imported yet.")
        churn = none
    else:
        p = pr.get_predictions(snapshot)
        churn = p.churn
    return [
        _from_result("churn", "Churn prediction", churn),
        _order_risk_row(db),
        *_season_rows(db),
    ]


def _far(a: float | None, b: float | None) -> bool:
    return (a is None) != (b is None) or (a is not None and b is not None and abs(a - b) > _SAME)


def _differs(row: Row, last: ModelReport) -> bool:
    return row.decision != last.decision or row.reason != last.reason or _far(row.model_score, last.model_score) or _far(row.baseline_score, last.baseline_score)


def record_changes(db: Session, rows: list[Row]) -> int:
    """Save a history line for every model whose decision or scores changed since its last line. Returns how many."""
    saved = 0
    for row in rows:
        last = db.scalar(select(ModelReport).where(ModelReport.model == row.model).order_by(ModelReport.id.desc()).limit(1))
        if last is not None and not _differs(row, last):
            continue
        db.add(ModelReport(
            model=row.model, label=row.label, decision=row.decision, reason=row.reason, metric=row.metric, model_score=row.model_score,
            baseline_score=row.baseline_score, higher_is_better=row.higher_is_better, test_size=row.test_size, split_date=row.split_date,
        ))
        saved += 1
    if saved:
        db.commit()
    return saved


def history(db: Session, limit: int = 40) -> list[ModelReport]:
    return list(db.scalars(select(ModelReport).order_by(ModelReport.id.desc()).limit(limit)))
