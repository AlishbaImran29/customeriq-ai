"""Google Trends CSV parser and the rising / stable / falling rule.
Every file here is a small MADE-UP test file in the format Google exports (not real search data)."""

from datetime import date, timedelta

import pytest

from app.core.errors import ApiError
from app.services.google_trends import parse_google_trends
from app.services.trend_label import label_trend

INTEREST = (
    "Category: All categories\n\n"
    "Week,test sneakers: (Pakistan)\n"
    "2026-01-04,10\n2026-01-11,<1\n2026-01-18,55\n"
)

RELATED = (
    "Category: All categories\n\n"
    "TOP\nquery,value\ntest sneakers cheap,100\ntest sneakers white,64\n\n"
    "RISING\nquery,value\ntest sneakers sale,Breakout\ntest sneakers kids,+250%\n"
)


def test_interest_over_time_header_lines_and_less_than_one():
    result = parse_google_trends(INTEREST.encode())
    assert len(result.series) == 1
    one = result.series[0]
    assert (one.keyword, one.region, one.granularity) == ("test sneakers", "Pakistan", "week")
    assert one.points == [(date(2026, 1, 4), 10.0), (date(2026, 1, 11), 0.5), (date(2026, 1, 18), 55.0)]


def test_several_keywords_in_one_file():
    text = "Week,test a: (Pakistan),test b: (Pakistan)\n2026-01-04,10,20\n2026-01-11,30,40\n"
    result = parse_google_trends(text.encode())
    assert [(s.keyword, [v for _, v in s.points]) for s in result.series] == [("test a", [10, 30]), ("test b", [20, 40])]


def test_daily_and_monthly_exports():
    assert parse_google_trends(b"Day,test x: (Pakistan)\n2026-01-04,5\n").series[0].granularity == "day"
    month = parse_google_trends(b"Month,test x: (Pakistan)\n2026-01,5\n2026-02,7\n").series[0]
    assert month.granularity == "month" and month.points[0][0] == date(2026, 1, 1)


def test_related_queries_top_and_rising():
    result = parse_google_trends(RELATED.encode())
    assert result.series == []
    assert [(r.kind, r.query, r.value) for r in result.related] == [
        ("top", "test sneakers cheap", "100"), ("top", "test sneakers white", "64"),
        ("rising", "test sneakers sale", "Breakout"), ("rising", "test sneakers kids", "+250%"),
    ]


def test_a_file_with_both_tables():
    result = parse_google_trends((INTEREST + "\n" + RELATED).encode())
    assert len(result.series[0].points) == 3 and len(result.related) == 4


def test_bom_and_utf16_files_are_read():
    assert parse_google_trends(b"\xef\xbb\xbf" + INTEREST.encode()).series
    assert parse_google_trends(INTEREST.encode("utf-16")).series


@pytest.mark.parametrize("content", [b"", b"name,price\nshoe,100\n", b"just some text", b"\x00\x01\x02\xff\xfe\xfd"])
def test_files_that_are_not_trends_exports_are_rejected_plainly(content):
    with pytest.raises(ApiError) as caught:
        parse_google_trends(content)
    assert caught.value.status_code in (413, 422) and caught.value.code in ("not_a_trends_file", "file_too_large")


def test_a_huge_file_is_refused():
    with pytest.raises(ApiError) as caught:
        parse_google_trends(b"x" * (3 * 1024 * 1024))
    assert caught.value.status_code == 413


def test_values_outside_0_to_100_are_skipped():
    result = parse_google_trends(b"Week,test x: (Pakistan)\n2026-01-04,150\n2026-01-11,20\n")
    assert [v for _, v in result.series[0].points] == [20.0]


# --- the label rule ------------------------------------------------------------------------------


def weekly(values, last=date(2026, 6, 28)):
    """One point per week, ending on `last`, with the given values (oldest first)."""
    return [(last - timedelta(days=7 * (len(values) - 1 - i)), v) for i, v in enumerate(values)]


def test_rising_when_the_last_four_weeks_are_15_percent_higher():
    assert label_trend(weekly([10] * 8 + [12, 12, 12, 12]))[0] == "rising"          # ratio 1.2
    label, ratio = label_trend(weekly([10] * 8 + [20] * 4))
    assert (label, ratio) == ("rising", 2.0)


def test_falling_and_stable():
    assert label_trend(weekly([20] * 8 + [10] * 4)) == ("falling", 0.5)
    assert label_trend(weekly([10] * 8 + [11] * 4))[0] == "stable"                  # ratio 1.1 is inside the stable band
    assert label_trend(weekly([10] * 8 + [8.5] * 4))[0] == "falling"                # exactly 0.85


def test_the_boundary_is_inclusive_at_1_15():
    assert label_trend(weekly([100] * 8 + [115] * 4))[0] == "rising"
    assert label_trend(weekly([100] * 8 + [114] * 4))[0] == "stable"


def test_not_enough_data_gives_no_label():
    assert label_trend(weekly([10, 20, 30, 40, 50])) == (None, None)               # 5 weeks
    assert label_trend(weekly([10] * 11)) == (None, None)                           # 11 weeks: just short
    assert label_trend([]) == (None, None)


def test_monthly_data_gets_no_label():
    months = [(date(2025, m, 1), 10.0 + m) for m in range(1, 13)]
    assert label_trend(months) == (None, None)


def test_daily_data_works_too():
    last = date(2026, 6, 28)
    days = [(last - timedelta(days=89 - i), 10.0 if i < 62 else 30.0) for i in range(90)]
    assert label_trend(days)[0] == "rising"


def test_an_all_zero_earlier_period_gives_no_label():
    assert label_trend(weekly([0] * 8 + [5] * 4)) == (None, None)
