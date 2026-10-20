"""Season Forecast: how many units of each product to expect in a season (Eid, Christmas...).

HOW IT WORKS (simple enough to explain in a viva)
- Sales are weekly units per product (table product_sales). A season has a WINDOW each year (dates in
  app/data/seasons.json). A window is counted in whole weeks (a week counts if its middle day is inside).
- BASELINE = "seasonal naive": next season will sell what the same window sold last year. This is the
  number any forecast has to beat, and it is what the page shows when nothing better is proven.
- MODEL = a ridge regression (a straight-line fit with a small penalty) on log units. It predicts the
  season's units from: last year's window, the year before's window, the last 8 weeks of sales before the
  forecast is made, and the same 8 weeks a year earlier. One model is learned from all products and
  all earlier seasons together.
- The forecast is made HORIZON_DAYS (28) before the window starts, so every feature is something that
  was already known on that day.

NO LEAKAGE (the model never sees the answer)
- A row's features use only sales before its forecast date.
- To test season S of year Y, the model learns ONLY from rows whose season window had already ended
  before Y's forecast date. Later data is never used to judge earlier data.

THE TRUST RULE (project rule 1)
- The back-test replays every past season that has enough history, as if it were forecast live, and
  compares the model with the baseline on those held-out seasons (MAE = average error in units;
  MAPE = average percentage error on products that sold at least MIN_UNITS_FOR_MAPE).
- A forecast is shown for a season only if the model's MAE beats the baseline's by MIN_IMPROVEMENT (5%)
  AND its MAPE is no worse, on that season's held-out tests. Otherwise the page shows "Last year's sales (no reliable forecast)",
  or "Not enough data yet", together with both scores and the reason.
- A forecast always comes with a range (the middle 80% of the model's past errors), labelled as an estimate.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from math import ceil, floor

import numpy as np
from sklearn.linear_model import Ridge

from app.services import data_rules
from app.services import season_config as cfg
from app.services.seasons import Season, Window

ADVICE_MORE, ADVICE_SIMILAR, ADVICE_LESS = "stock_more", "similar", "stock_less"


# --- weekly sales matrix ---------------------------------------------------------------------------


def week_of(day: date) -> date:
    """The Monday of the week a day belongs to."""
    return day - timedelta(days=day.weekday())


class WeeklySales:
    """Units per product per week as a dense table, with running totals so any window is a subtraction."""

    def __init__(self, series: dict[str, dict[date, int]]):
        self.products = sorted(series)
        weeks = [w for s in series.values() for w in s]
        self.first = min(weeks) if weeks else None
        self.last_week = max(weeks) if weeks else None
        count = ((self.last_week - self.first).days // 7 + 1) if weeks else 0
        self.matrix = np.zeros((len(self.products), count))
        for i, product in enumerate(self.products):
            for week, units in series[product].items():
                self.matrix[i, (week - self.first).days // 7] = units
        self.cum = np.concatenate([np.zeros((len(self.products), 1)), np.cumsum(self.matrix, axis=1)], axis=1)

    @property
    def data_end(self) -> date | None:
        return self.last_week + timedelta(days=6) if self.last_week else None

    def covers(self, start: date, end: date) -> bool:
        """True when the data runs over the whole stretch (a half-empty window would give false low numbers)."""
        return self.first is not None and self.first <= start and self.data_end >= end

    def units_in(self, start: date, end: date) -> np.ndarray:
        """Units per product in the weeks whose middle day is between start and end."""
        n = self.matrix.shape[1]
        lo = max(0, ceil((start - timedelta(days=3) - self.first).days / 7))
        hi = min(n - 1, floor((end - timedelta(days=3) - self.first).days / 7))
        if hi < lo:
            return np.zeros(len(self.products))
        return self.cum[:, hi + 1] - self.cum[:, lo]


# --- rows: one per (product, season, year) -------------------------------------------------------


@dataclass
class RowSet:
    """All the products' rows for one season in one year."""

    season: str
    year: int
    window: Window
    origin: date                      # the day the forecast is made
    products: list[str]
    X: np.ndarray                     # features (log1p units): last year, two years ago, recent, recent a year ago; NaN = unknown
    last: np.ndarray                  # last year's units in the window = the baseline
    target: np.ndarray | None         # the season's real units, when the window is fully in the data

    @property
    def n(self) -> int:
        return len(self.products)


def build_rowset(sales: WeeklySales, season: Season, year: int) -> RowSet | None:
    """The rows for one season-year, or None when last year's window or the forecast date's data is missing."""
    window, previous = season.windows.get(year), season.windows.get(year - 1)
    if window is None or previous is None or sales.first is None:
        return None
    origin = window.start - timedelta(days=cfg.HORIZON_DAYS)
    if not sales.covers(previous.start, previous.end) or origin > sales.data_end:
        return None
    recent_start = origin - timedelta(days=7 * cfg.RECENT_WEEKS - 1)
    if recent_start < sales.first:
        return None
    nan = np.full(len(sales.products), np.nan)
    last = sales.units_in(previous.start, previous.end)
    before = season.windows.get(year - 2)
    two_ago = sales.units_in(before.start, before.end) if before and sales.covers(before.start, before.end) else nan
    recent = sales.units_in(recent_start, origin)
    year_ago_start, year_ago_end = recent_start - timedelta(days=364), origin - timedelta(days=364)
    recent_ly = sales.units_in(year_ago_start, year_ago_end) if sales.covers(year_ago_start, year_ago_end) else nan
    active = (last > 0) | (recent > 0)                       # a product that sold nothing lately is not forecast
    if not active.any():
        return None
    target = sales.units_in(window.start, window.end)[active] if sales.covers(window.start, window.end) else None
    X = np.log1p(np.column_stack([last, two_ago, recent, recent_ly]))[active]
    return RowSet(
        season.id, year, window, origin, [p for p, keep in zip(sales.products, active) if keep], X, last[active], target
    )


# --- the model --------------------------------------------------------------------------------------


class SeasonModel:
    """Ridge regression on log1p units. Unknown features (a missing earlier year) are filled with the
    training median and flagged with an indicator column, so "no data" is never mistaken for zero sales."""

    def __init__(self, X: np.ndarray, y: np.ndarray):
        known = [X[~np.isnan(X[:, j]), j] for j in range(X.shape[1])]
        self.fill = np.array([np.median(col) if len(col) else 0.0 for col in known])
        self.ridge = Ridge(alpha=1.0).fit(self._prepare(X), np.log1p(y))

    def _prepare(self, X: np.ndarray) -> np.ndarray:
        missing = np.isnan(X)
        return np.column_stack([np.where(missing, self.fill, X), missing[:, 1], missing[:, 3]])

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predicted units (never below zero)."""
        return np.clip(np.expm1(self.ridge.predict(self._prepare(X))), 0, None)


def _training_rows(rowsets: dict[tuple[str, int], RowSet], before: date) -> tuple[np.ndarray, np.ndarray]:
    """Rows whose season window had ended before `before`, so their real answer was known by then."""
    parts = [r for r in rowsets.values() if r.target is not None and r.window.end < before]
    if not parts:
        return np.empty((0, 4)), np.empty(0)
    return np.vstack([r.X for r in parts]), np.concatenate([r.target for r in parts])


# --- the back-test ----------------------------------------------------------------------------------


@dataclass
class BackTest:
    cases: int = 0                    # held-out season-years tested
    rows: int = 0                     # product forecasts compared
    model_mae: float | None = None
    baseline_mae: float | None = None
    model_mape: float | None = None
    baseline_mape: float | None = None
    improvement: float | None = None  # 1 - model_mae / baseline_mae
    passed: bool = False
    low_error: float = 0.0            # 10th and 90th percentile of the model's log errors (for the range)
    high_error: float = 0.0
    tested: list[str] = field(default_factory=list)   # "2024", "2025"...


def backtest_season(rowsets: dict[tuple[str, int], RowSet], season_id: str) -> BackTest:
    result = BackTest()
    model_err, base_err, model_pct, base_pct, log_err = [], [], [], [], []
    for (sid, year), rs in sorted(rowsets.items()):
        if sid != season_id or rs.target is None or not data_rules.enough(rs.n):
            continue
        X, y = _training_rows(rowsets, rs.origin)
        if len(y) < cfg.MIN_TRAIN_ROWS:
            continue
        predicted = SeasonModel(X, y).predict(rs.X)
        model_err.append(np.abs(predicted - rs.target))
        base_err.append(np.abs(rs.last - rs.target))
        big = rs.target >= cfg.MIN_UNITS_FOR_MAPE
        model_pct.append(np.abs(predicted - rs.target)[big] / rs.target[big])
        base_pct.append(np.abs(rs.last - rs.target)[big] / rs.target[big])
        log_err.append(np.log1p(rs.target) - np.log1p(predicted))
        result.cases += 1
        result.tested.append(str(year))
    if not result.cases:
        return result
    me, be = np.concatenate(model_err), np.concatenate(base_err)
    result.rows = len(me)
    result.model_mae, result.baseline_mae = float(me.mean()), float(be.mean())
    mp, bp = np.concatenate(model_pct), np.concatenate(base_pct)
    result.model_mape = float(mp.mean()) if len(mp) else None
    result.baseline_mape = float(bp.mean()) if len(bp) else None
    result.improvement = 1 - result.model_mae / result.baseline_mae if result.baseline_mae > 0 else None
    # Both scores must agree: a lower average error in units AND a percentage error that is not worse.
    # (MAPE is skipped only when no product sold enough to measure it.)
    mape_ok = result.model_mape is None or result.baseline_mape is None or result.model_mape <= result.baseline_mape
    result.passed = result.improvement is not None and result.improvement >= cfg.MIN_IMPROVEMENT and mape_ok
    residuals = np.concatenate(log_err)
    result.low_error = float(np.quantile(residuals, cfg.RANGE_LOW_QUANTILE))
    result.high_error = float(np.quantile(residuals, cfg.RANGE_HIGH_QUANTILE))
    return result


# --- the forecast for the next season ---------------------------------------------------------------


@dataclass
class ProductForecast:
    product: str
    last_year: int                    # the baseline
    forecast: int | None              # None unless the model is proven
    low: int | None
    high: int | None
    advice: str | None                # stock_more / similar / stock_less, or None when sales are too small to advise


@dataclass
class SeasonResult:
    season_id: str
    name: str
    status: str                       # "forecast", "last_year_only" or "not_enough_data"
    reason: str | None                # not_better, no_backtest, too_early, few_products, no_last_year, no_target
    target_year: int | None
    window: Window | None
    last_year_window: Window | None
    forecast_date: date | None        # the day the forecast is (or will be) made
    products: int
    backtest: BackTest
    rows: list[ProductForecast] = field(default_factory=list)


def _advice(last: int, forecast: int) -> str | None:
    if max(last, forecast) < cfg.MIN_UNITS_FOR_MAPE:
        return None                                              # too few sales to say anything
    ratio = forecast / max(last, 1)
    if ratio >= cfg.STOCK_MORE_RATIO:
        return ADVICE_MORE
    return ADVICE_LESS if ratio <= cfg.STOCK_LESS_RATIO else ADVICE_SIMILAR


def forecast_seasons(sales: WeeklySales, seasons: list[Season]) -> list[SeasonResult]:
    """One result per season: the next window (after the data ends) and whether a forecast can be trusted."""
    if sales.first is None:
        return [SeasonResult(s.id, s.name, "not_enough_data", "no_target", None, None, None, None, 0, BackTest()) for s in seasons]
    rowsets = {}
    for season in seasons:
        for year in season.windows:
            built = build_rowset(sales, season, year)
            if built is not None:
                rowsets[(season.id, year)] = built
    results = []
    for season in seasons:
        results.append(_one_season(sales, season, rowsets))
    return results


def _one_season(sales: WeeklySales, season: Season, rowsets: dict[tuple[str, int], RowSet]) -> SeasonResult:
    data_end = sales.data_end
    target_year = next((y for y, w in season.windows.items() if w.start > data_end), None)
    test = backtest_season(rowsets, season.id)

    def result(status, reason, rows=None, products=0, window=None, last_window=None, when=None):
        return SeasonResult(season.id, season.name, status, reason, target_year, window, last_window, when, products, test, rows or [])

    if target_year is None:
        return result("not_enough_data", "no_target")
    window, previous = season.windows[target_year], season.windows.get(target_year - 1)
    forecast_date = window.start - timedelta(days=cfg.HORIZON_DAYS)
    if previous is None or not sales.covers(previous.start, previous.end):
        return result("not_enough_data", "no_last_year", window=window, last_window=previous, when=forecast_date)

    # The baseline table works even before the forecast date: it only needs last year's window.
    last_all = sales.units_in(previous.start, previous.end)
    listed = [i for i in np.argsort(-last_all) if last_all[i] > 0]
    if not data_rules.enough(len(listed)):
        return result("not_enough_data", "few_products", window=window, last_window=previous, when=forecast_date, products=len(listed))
    base_rows = [ProductForecast(sales.products[i], int(last_all[i]), None, None, None, None) for i in listed[: cfg.MAX_LISTED_PRODUCTS]]

    def baseline(reason):
        return result("last_year_only", reason, base_rows, len(listed), window, previous, forecast_date)

    if forecast_date > data_end:
        return baseline("too_early")                              # the features do not exist yet
    if not test.cases:
        return baseline("no_backtest")
    if not test.passed:
        return baseline("not_better")
    rs = build_rowset(sales, season, target_year)
    X, y = _training_rows(rowsets, forecast_date)
    if rs is None or len(y) < cfg.MIN_TRAIN_ROWS:
        return baseline("no_backtest")
    predicted = SeasonModel(X, y).predict(rs.X)
    low = np.expm1(np.log1p(predicted) + test.low_error).clip(min=0)
    high = np.expm1(np.log1p(predicted) + test.high_error).clip(min=0)
    rows = []
    for i in np.argsort(-np.maximum(predicted, rs.last)):
        last, fc = int(rs.last[i]), int(round(predicted[i]))
        rows.append(ProductForecast(rs.products[i], last, fc, int(round(low[i])), int(round(max(high[i], predicted[i]))), _advice(last, fc)))
    return result("forecast", None, rows[: cfg.MAX_LISTED_PRODUCTS], len(rows), window, previous, forecast_date)
