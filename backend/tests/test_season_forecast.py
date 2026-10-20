"""Season Forecast: season dates, weekly sums, no leakage, and the trust rule. All sales here are MADE UP
for the tests (products are called "Test product N")."""

import io
from collections import defaultdict
from datetime import date, timedelta
from importlib import util
from pathlib import Path

import numpy as np
import pytest

from app.core.errors import ApiError
from app.models import ProductSale
from app.services import season_forecast as sf
from app.services.product_sales_import import import_product_sales, load_weekly_sales
from app.services.seasons import Season, SeasonConfigError, Window, parse_seasons

ROOT = Path(__file__).resolve().parents[2]
spec = util.spec_from_file_location("generate_demo_product_sales", ROOT / "backend" / "scripts" / "generate_demo_product_sales.py")
demo = util.module_from_spec(spec)
spec.loader.exec_module(demo)


def to_sales(rows):
    series = defaultdict(dict)
    for r in rows:
        series[r["product"]][date.fromisoformat(r["date"])] = int(r["units"])
    return sf.WeeklySales(dict(series))


def yearly_season(years, start=(5, 1), end=(5, 31), sid="test_season"):
    return Season(sid, "Test season", {y: Window(date(y, *start), date(y, *end)) for y in years})


def steady_sales(per_week=lambda p, w: 10, products=30, first=date(2020, 1, 6), last=date(2024, 12, 30)):
    rows, week = [], first
    while week <= last:
        for p in range(products):
            rows.append({"product": f"Test product {p}", "date": week.isoformat(), "units": str(per_week(p, week))})
        week += timedelta(days=7)
    return to_sales(rows)


# --- season date tables -------------------------------------------------------------------------


def test_moving_season_window_is_the_lead_days_up_to_the_festival():
    seasons = parse_seasons({"seasons": [{"id": "x", "name": "X", "kind": "moving", "lead_days": 14, "dates": {"2026": "2026-05-27"}}]})
    assert seasons[0].windows[2026] == Window(date(2026, 5, 14), date(2026, 5, 27)) and seasons[0].windows[2026].days == 14


def test_fixed_season_repeats_each_listed_year():
    seasons = parse_seasons({"seasons": [{"id": "x", "name": "X", "kind": "fixed", "start": "11-01", "end": "12-08", "years": [2010, 2011]}]})
    assert seasons[0].windows[2011] == Window(date(2011, 11, 1), date(2011, 12, 8))


@pytest.mark.parametrize("entry", [
    {"id": "x", "name": "X", "kind": "moving", "lead_days": 14, "dates": {"2026": "27/05/2026"}},     # not an ISO date
    {"id": "x", "name": "X", "kind": "moving", "lead_days": 14, "dates": {"2026": "2025-05-27"}},     # wrong year
    {"id": "x", "name": "X", "kind": "fixed", "start": "12-08", "end": "11-01", "years": [2010]},      # end before start
    {"id": "x", "name": "X", "kind": "weekly"},
    {"id": "x", "name": "X", "kind": "moving", "lead_days": 14, "dates": {}},                          # no years
])
def test_a_mistake_in_the_seasons_file_is_a_clear_error(entry):
    with pytest.raises(SeasonConfigError):
        parse_seasons({"seasons": [entry]})


def test_the_real_seasons_file_loads():
    from app.services.seasons import SEASONS

    assert {s.id for s in SEASONS} == {"eid_ul_fitr", "eid_ul_adha", "christmas"}


# --- weekly sums -----------------------------------------------------------------------------------


def test_window_units_count_whole_weeks_by_their_middle_day():
    sales = to_sales([{"product": "Test product 1", "date": (date(2025, 1, 6) + timedelta(days=7 * i)).isoformat(), "units": str(i + 1)} for i in range(10)])
    # weeks start 6, 13, 20, 27 Jan...; their middle days (Thursdays) are 9, 16, 23, 30 Jan...
    assert sales.units_in(date(2025, 1, 9), date(2025, 1, 23))[0] == 1 + 2 + 3
    assert sales.units_in(date(2025, 1, 10), date(2025, 1, 22))[0] == 2          # only the 16 Jan middle day is inside


def test_a_window_the_data_does_not_cover_is_not_complete():
    sales = steady_sales(last=date(2024, 5, 13))
    assert sales.covers(date(2024, 5, 1), date(2024, 5, 10)) and not sales.covers(date(2024, 5, 1), date(2024, 5, 31))


# --- no leakage ----------------------------------------------------------------------------------


def test_features_never_use_sales_after_the_forecast_date():
    season = yearly_season([2022, 2023, 2024])
    sales = steady_sales()
    before = sf.build_rowset(sales, season, 2024)
    # Change every sale AFTER the forecast date (including the answer): the features must not move.
    changed = defaultdict(dict)
    for i, product in enumerate(sales.products):
        for j in range(sales.matrix.shape[1]):
            week = sales.first + timedelta(days=7 * j)
            changed[product][week] = int(sales.matrix[i, j]) + (500 if week + timedelta(days=6) > before.origin else 0)
    after = sf.build_rowset(sf.WeeklySales(dict(changed)), season, 2024)
    assert np.array_equal(before.X, after.X, equal_nan=True) and np.array_equal(before.last, after.last)
    assert not np.array_equal(before.target, after.target)                   # only the answer differs


def test_the_model_learns_only_from_seasons_that_ended_before_the_forecast_date():
    season = yearly_season([2021, 2022, 2023, 2024])
    sales = steady_sales()
    rowsets = {(season.id, y): sf.build_rowset(sales, season, y) for y in season.windows}
    rowsets = {k: v for k, v in rowsets.items() if v is not None}
    origin_2024 = rowsets[("test_season", 2024)].origin
    _, y = sf._training_rows(rowsets, origin_2024)
    used = [k for k, v in rowsets.items() if v.target is not None and v.window.end < origin_2024]
    assert ("test_season", 2024) not in used and len(y) == sum(rowsets[k].n for k in used)


# --- the trust rule ---------------------------------------------------------------------------------


def test_a_perfect_baseline_cannot_be_beaten_so_no_model_forecast_is_shown():
    # Every year is identical: last year's window is exactly right, the model has nothing to add.
    season = yearly_season([2021, 2022, 2023, 2024, 2025])
    sales = steady_sales(per_week=lambda p, w: 10 + (20 if w.month == 5 else 0) + p, last=date(2025, 4, 14))
    result = sf.forecast_seasons(sales, [season])[0]
    assert result.status == "last_year_only" and result.reason in ("not_better", "no_backtest")
    assert all(row.forecast is None for row in result.rows) and result.rows[0].last_year > 0


def test_the_demo_data_shows_the_trust_rule_working_per_season():
    sales = to_sales(demo.generate())
    from app.services.seasons import SEASONS

    by_id = {r.season_id: r for r in sf.forecast_seasons(sales, SEASONS)}
    adha = by_id["eid_ul_adha"]
    assert adha.target_year == 2026 and adha.backtest.cases == 4 and adha.backtest.rows == 400
    # Whatever the scores are, a forecast is shown ONLY when the model passed the back-test.
    assert (adha.status == "forecast") == adha.backtest.passed
    for result in by_id.values():
        shown = [r for r in result.rows if r.forecast is not None]
        assert (result.status == "forecast") == bool(shown)
        if result.status != "forecast":
            assert all(r.low is None and r.high is None and r.advice is None for r in result.rows)
    assert by_id["eid_ul_fitr"].reason == "too_early" and by_id["christmas"].reason == "too_early"


def test_a_model_that_clearly_beats_last_year_is_shown_with_ranges_and_advice():
    """A made-up shop where some products rise fast and some fall: last year's window is out of date."""
    rng = np.random.default_rng(3)
    season = yearly_season([2020, 2021, 2022, 2023, 2024, 2025])
    rows, week = [], date(2020, 1, 6)
    level = {p: rng.uniform(5, 40) for p in range(60)}
    while week <= date(2025, 4, 14):
        years = (week - date(2020, 1, 6)).days / 365
        for p in range(60):
            seasonal = 3.0 if week.month == 5 else 1.0
            growth = (1 + 0.6 * (p % 3 - 1)) ** years if p % 3 else 1.0       # some products rise fast, some fall
            rows.append({"product": f"Test product {p}", "date": week.isoformat(), "units": str(rng.poisson(level[p] * seasonal * growth))})
        week += timedelta(days=7)
    result = sf.forecast_seasons(to_sales(rows), [season])[0]
    b = result.backtest
    assert b.cases >= 2 and b.model_mae < b.baseline_mae
    assert result.status == "forecast" and b.passed and b.improvement >= 0.05
    top = result.rows[0]
    assert top.forecast is not None and top.low <= top.forecast <= top.high
    assert {r.advice for r in result.rows} <= {"stock_more", "similar", "stock_less", None}


def test_too_few_products_means_not_enough_data():
    season = yearly_season([2022, 2023, 2024])
    result = sf.forecast_seasons(steady_sales(products=5, last=date(2024, 4, 15)), [season])[0]
    assert result.status == "not_enough_data" and result.reason == "few_products"


def test_no_data_at_all():
    result = sf.forecast_seasons(sf.WeeklySales({}), [yearly_season([2024])])[0]
    assert result.status == "not_enough_data"


def test_advice_labels_and_the_tiny_sales_exception():
    assert sf._advice(100, 130) == "stock_more" and sf._advice(100, 100) == "similar" and sf._advice(100, 70) == "stock_less"
    assert sf._advice(2, 4) is None                                           # too few units to advise on


# --- importing product sales ------------------------------------------------------------------------


def test_import_adds_days_into_weeks_tidies_names_and_replaces_on_reupload(db_session):
    text = "product,date,units\nTest product 1,2025-01-06,3\nTest product 1,2025-01-08,4\n Test   product 1 ,2025-01-14,5\n"
    first = import_product_sales(db_session, text.encode(), "csv")
    assert (first.weeks_created, first.weeks_updated, first.rejected, first.products) == (2, 0, 0, 1)
    rows = {r.week_start: r.units for r in db_session.query(ProductSale)}
    assert rows == {date(2025, 1, 6): 7, date(2025, 1, 13): 5}
    again = import_product_sales(db_session, text.encode(), "csv")
    assert (again.weeks_created, again.weeks_updated) == (0, 2)                  # replaced, not added twice
    assert {r.units for r in db_session.query(ProductSale)} == {7, 5}


def test_import_rejects_bad_rows_without_echoing_them(db_session):
    text = "product,date,units\n,2025-01-06,3\nTest product 1,nonsense-date,3\nTest product 1,2025-01-06,-4\nTest product 1,2025-01-06,2.5\nTest product 1,2025-01-06,9\n"
    result = import_product_sales(db_session, text.encode(), "csv")
    assert result.rejected == 4 and result.weeks_created == 1
    assert {(e["row"], e["column"]) for e in result.errors} == {(2, "product"), (3, "date"), (4, "units"), (5, "units")}
    assert "nonsense-date" not in " ".join(e["message"] for e in result.errors)


def test_import_needs_the_three_columns():
    from app.services.product_sales_import import _positions

    with pytest.raises(ApiError):
        _positions(["product", "units"])


def test_real_data_hides_demo_data(db_session):
    db_session.add_all([
        ProductSale(product="Demo product 1", week_start=date(2025, 1, 6), units=5, source="demo (synthetic)"),
        ProductSale(product="Test product 1", week_start=date(2025, 1, 6), units=7, source="import"),
    ])
    db_session.flush()
    used, real, demo_weeks, sales = load_weekly_sales(db_session)
    assert (used, real, demo_weeks, sales.products) == ("real", 1, 1, ["Test product 1"])
    assert load_weekly_sales(db_session, "demo")[3].products == ["Demo product 1"]


def test_api_forecast_and_import(db_client, db_session):
    files = {"file": ("sales.csv", io.BytesIO(b"product,date,units\nTest product 1,2025-01-06,3\n"), "text/csv")}
    assert db_client.post("/api/v1/seasons/sales/import", files=files).json()["weeksCreated"] == 1
    body = db_client.get("/api/v1/seasons/forecast").json()
    assert body["minGroupCount"] == 20 and len(body["seasons"]) == 3
    assert all(s["status"] != "forecast" for s in body["seasons"])
    assert db_client.get("/api/v1/seasons/forecast?source=bogus").status_code == 422
