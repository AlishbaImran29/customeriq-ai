"""Response shapes of the Season Forecast (camelCase, matching frontend/lib/api/seasons.ts)."""

from datetime import date

from app.schemas.imports import CamelModel, ImportRowError


class WindowOut(CamelModel):
    start: date
    end: date


class BackTestOut(CamelModel):
    cases: int                         # held-out season-years tested
    rows: int                          # product forecasts compared
    tested: list[str]                  # the years tested
    model_mae: float | None            # average error in units
    baseline_mae: float | None
    model_mape: float | None           # average percentage error (0-1) on products that sold enough
    baseline_mape: float | None
    improvement: float | None          # 1 - model_mae / baseline_mae
    passed: bool                       # the model beat the baseline by the required margin


class ProductForecastOut(CamelModel):
    product: str
    last_year: int                     # the baseline: what the same window sold last year
    forecast: int | None               # None unless the model is proven
    low: int | None                    # the range is an estimate: the middle 80% of past errors
    high: int | None
    advice: str | None                 # stock_more / similar / stock_less; None = sales too small to advise


class SeasonOut(CamelModel):
    id: str
    name: str
    status: str                        # forecast / last_year_only / not_enough_data
    reason: str | None                 # not_better / no_backtest / too_early / few_products / no_last_year / no_target
    target_year: int | None
    window: WindowOut | None
    last_year_window: WindowOut | None
    forecast_date: date | None         # when the forecast is (or will be) made
    products: int
    backtest: BackTestOut
    rows: list[ProductForecastOut]


class SeasonsOut(CamelModel):
    source_used: str                   # "real" or "demo"
    real_weeks: int
    demo_weeks: int
    data_from: date | None
    data_to: date | None
    min_group_count: int
    seasons: list[SeasonOut]


class ProductSalesImportOut(CamelModel):
    rows_in_file: int
    weeks_created: int
    weeks_updated: int
    rejected: int
    products: int
    first_week: date | None
    last_week: date | None
    error_count: int
    errors: list[ImportRowError]
    errors_truncated: bool


class ProductSalesSummaryOut(CamelModel):
    product_weeks: int
    demo_product_weeks: int
