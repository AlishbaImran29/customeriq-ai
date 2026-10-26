"""Formula tests for the descriptive analytics (no database)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services import analytics as a

AS_OF = date(2026, 10, 13)


def order(customer: str, days_ago: int, value: float = 100.0, engagement: float | None = None,
          category: str = "Skincare", channel: str = "Shopify") -> a.OrderFact:
    return a.OrderFact(
        customer_id=customer,
        name=customer,
        email=f"{customer.lower()}@example.com",
        order_date=AS_OF - timedelta(days=days_ago),
        value=Decimal(str(value)),
        channel=channel,
        category=category,
        country="US",
        engagement=Decimal(str(engagement)) if engagement is not None else None,
    )


def by_id(snapshot: a.Snapshot) -> dict[str, a.CustomerMetrics]:
    return {c.customer_id: c for c in snapshot.customers}


# --- helpers ------------------------------------------------------------------

def test_round_half_up():
    assert [a.round_half_up(x) for x in (2.5, 3.5, 2.4)] == [3, 4, 2]


def test_midrank_percentiles_share_value_for_ties():
    assert a.midrank_percentiles([1, 1, 3, 4]) == [25.0, 25.0, 62.5, 87.5]


@pytest.mark.parametrize("r, fm, segment", [
    (5, 5, "Champions"), (4, 4, "Champions"),
    (5, 3, "Loyal Customers"), (3, 4, "Loyal Customers"),
    (4, 2, "Potential Loyalists"), (3, 1, "Potential Loyalists"),
    (2, 3, "At-Risk Customers"), (1, 5, "At-Risk Customers"),
    (2, 2, "Lost Customers"), (1, 1, "Lost Customers"),
])
def test_segment_rules_first_match_wins(r, fm, segment):
    assert a.segment_for(r, fm) == segment


@pytest.mark.parametrize("ratio, level", [
    (0.5, "Low"), (1.0, "Low"), (1.2, "Medium"), (1.5, "Medium"),
    (2.0, "High"), (2.5, "High"), (2.6, "Critical"),
])
def test_inactivity_levels(ratio, level):
    assert a.inactivity_level(ratio) == level


# --- snapshot -----------------------------------------------------------------

def test_empty_data_gives_empty_snapshot():
    snapshot = a.build_snapshot([])
    assert snapshot.empty and a.kpis(snapshot)[0]["revenue"] is None
    assert a.monthly_revenue(snapshot) == [] and a.recommendations(snapshot) == []


def test_as_of_is_latest_order_date_not_today():
    snapshot = a.build_snapshot([order("A", 400), order("A", 30)])
    assert snapshot.as_of == AS_OF - timedelta(days=30)


def test_activity_ratio_and_typical_gap():
    # Orders every 30 days, last one 60 days ago -> ratio 2.0 -> "High".
    c = by_id(a.build_snapshot([order("A", 120), order("A", 90), order("A", 60), order("Z", 0)]))["A"]
    assert c.typical_gap_days == 30 and c.recency_days == 60
    assert c.activity_ratio == 2.0 and c.inactivity_level == "High"


def test_single_order_uses_90_day_gap():
    c = by_id(a.build_snapshot([order("A", 45), order("Z", 0)]))["A"]
    assert c.typical_gap_days == 90 and c.activity_ratio == 0.5


def test_segmentation_needs_twenty_customers():
    few = a.build_snapshot([order(f"C{i}", i) for i in range(19)])
    assert not few.segmented and all(c.segment is None for c in few.customers)
    assert a.segment_summaries(few) == []
    enough = a.build_snapshot([order(f"C{i}", i) for i in range(20)])
    assert enough.segmented and all(c.segment for c in enough.customers)


def test_rfm_separates_best_and_worst_customers():
    facts = []
    for i in range(10):  # frequent, recent, high spend
        facts += [order(f"BEST{i}", d, 300) for d in (1, 20, 40, 60, 80, 100)]
    for i in range(10):  # one small, old order
        facts.append(order(f"LOST{i}", 400 + i, 20))
    segments = {c.customer_id: c.segment for c in a.build_snapshot(facts).customers}
    assert all(segments[f"BEST{i}"] == "Champions" for i in range(10))
    # Scores are relative (quintiles), so the least-inactive of a large lost group
    # can rank mid-table on recency. The oldest ones must be Lost, and none of the
    # group can be Champions or Loyal.
    assert all(segments[f"LOST{i}"] == "Lost Customers" for i in range(6, 10))
    assert not {segments[f"LOST{i}"] for i in range(10)} & {"Champions", "Loyal Customers"}


# --- KPIs ---------------------------------------------------------------------

def test_kpis_and_deltas_with_enough_history():
    facts = [
        order("A", 200, 100), order("A", 100, 100), order("A", 10, 100),  # retained
        order("B", 120, 50),                                              # not retained
        order("C", 5, 200),                                               # new
    ]
    values, deltas = a.kpis(a.build_snapshot(facts))
    assert values["totalCustomers"] == 3
    assert values["revenue"] == 300.0                 # A(10d) + C(5d)
    assert values["averageClv"] == pytest.approx(550 / 3)
    assert values["retentionRate"] == 50.0            # of A, B (previous window) only A returned
    assert deltas["revenue"] == pytest.approx(100.0)  # 300 vs 150 in the previous window
    assert deltas["totalCustomers"] == pytest.approx(50.0)  # 3 now vs 2 then
    assert values["churnRisk"] is None and values["growthScore"] is None


def test_deltas_are_none_without_enough_history():
    values, deltas = a.kpis(a.build_snapshot([order("A", 10), order("B", 0)]))
    assert values["revenue"] == 200.0
    assert all(v is None for v in deltas.values())
    assert values["retentionRate"] is None


def test_monthly_revenue_marks_partial_last_month():
    series = a.monthly_revenue(a.build_snapshot([order("A", 40, 10), order("A", 0, 5)]))
    assert [p["month"] for p in series] == ["Sep 2026", "Oct 2026"]
    assert series[-1] == {"month": "Oct 2026", "actual": 5.0, "partial": True}
    assert series[0]["partial"] is False


def test_recommendations_have_no_invented_revenue_estimates():
    facts = [order(f"C{i}", i * 15, 50 + i) for i in range(30)]
    recs = a.recommendations(a.build_snapshot(facts))
    assert recs and all(r["estimatedRevenue"] is None for r in recs)
    assert all(r["historicalRevenue"] >= 0 for r in recs)


# --- Growth Score -------------------------------------------------------------------------------

def _snapshot_for_growth():
    return a.build_snapshot([order(f"C{i}", i * 5, 50 + i) for i in range(30)])


def _expected_score(parts):
    """parts: {key: (subscore, weight)} -> the weighted mean the docs promise."""
    return a.round_half_up(sum(v * w for v, w in parts.values()) / sum(w for _, w in parts.values()))


def test_growth_score_combines_three_measured_inputs():
    snapshot = _snapshot_for_growth()
    result = a.growth_score(snapshot, {"retentionRate": 60.0}, {"revenue": 20.0, "totalCustomers": 10.0})
    parts = {"rev": (70.0, 0.35), "ret": (60.0, 0.30), "cust": (75.0, 0.15)}
    assert result["score"] == _expected_score(parts)
    by_key = {c["key"]: c for c in result["components"]}
    assert by_key["revenueGrowth"]["value"] == 70 and by_key["revenueGrowth"]["measure"] == "+20.0%"
    assert by_key["customerGrowth"]["value"] == 75 and by_key["retention"]["measure"] == "60.0%"
    assert [c["weight"] for c in result["components"]] == [44, 38, 19] and result["missing"] == []


def test_growth_sub_scores_are_clamped_to_0_100():
    snapshot = _snapshot_for_growth()
    high = a.growth_score(snapshot, {"retentionRate": 100.0}, {"revenue": 500.0, "totalCustomers": 90.0})
    low = a.growth_score(snapshot, {"retentionRate": 0.0}, {"revenue": -500.0, "totalCustomers": -90.0})
    assert {c["key"]: c["value"] for c in high["components"]}["revenueGrowth"] == 100
    assert {c["key"]: c["value"] for c in low["components"]}["customerGrowth"] == 0
    assert 0 <= low["score"] < high["score"] <= 100


def test_growth_score_rescales_weights_when_an_input_is_missing():
    snapshot = _snapshot_for_growth()
    result = a.growth_score(snapshot, {"retentionRate": 60.0}, {"revenue": 20.0, "totalCustomers": None})
    assert result["missing"] == ["Customer growth (vs 90 days ago)"]
    assert [c["weight"] for c in result["components"]] == [54, 46]  # 0.35 / 0.30 over 0.65
    assert result["score"] == _expected_score({"rev": (70.0, 0.35), "ret": (60.0, 0.30)})


def test_growth_score_needs_at_least_two_inputs():
    snapshot = _snapshot_for_growth()
    assert a.growth_score(snapshot, {"retentionRate": None}, {"revenue": 20.0, "totalCustomers": None}) is None   # only one input
    assert a.growth_score(a.build_snapshot([]), {"retentionRate": 60.0}, {"revenue": 1.0, "totalCustomers": 1.0}) is None


# --- revenue drivers: order stats per country ------------------------------------

def test_revenue_drivers_report_orders_customers_average_and_repeat_rate():
    def sale(customer, days_ago, value, country):
        return a.OrderFact(customer, customer, f"{customer.lower()}@example.com", AS_OF - timedelta(days=days_ago), Decimal(str(value)), None, "Skincare", country, None)

    facts = [sale("A", 10, 100, "United Kingdom"), sale("A", 20, 50, "United Kingdom"), sale("B", 30, 150, "United Kingdom"), sale("B", 40, 80, "France")]
    drivers = a.revenue_drivers(a.build_snapshot(facts))
    assert "byChannel" not in drivers                      # revenue by channel was removed: the dataset has no channel
    rows = {r["name"]: r for r in drivers["byCountry"]}
    uk = rows["United Kingdom"]
    assert (uk["orders"], uk["customers"]) == (3, 2)
    assert uk["avgOrderValue"] == 100.0
    assert uk["repeatRate"] == 50.0  # 1 of 2 customers ordered twice in the UK
    assert rows["France"]["repeatRate"] == 0.0 and rows["France"]["orders"] == 1


# --- KPI period length and cohort retention ----------------------------------------

def test_kpi_period_length_changes_the_revenue_window():
    # 100 within the last 30 days, 200 between 31 and 90 days ago.
    facts = [order("A", 5, 100), order("B", 60, 200), order("C", 400, 1)]
    snapshot = a.build_snapshot(facts)
    assert a.kpis(snapshot)[0]["revenue"] == 300.0
    assert a.kpis(snapshot, 30)[0]["revenue"] == 100.0
    labels = [c["label"] for c in a.growth_score(snapshot, {"retentionRate": 50.0}, {"revenue": 10.0, "totalCustomers": 5.0}, 30)["components"]]
    assert "Retention rate (30 days)" in labels


def test_cohort_retention_counts_customers_who_ordered_again_each_month():
    # AS_OF is 13 Oct 2026, so October is still in progress. 90 days ago = mid July.
    facts = [
        order("A", 90), order("A", 60),    # A: first order July, again in August
        order("B", 90),                    # B: July only
        order("C", 30), order("C", 5),     # C: first order September, again in October (partial)
    ]
    result = a.cohort_retention(a.build_snapshot(facts))
    rows = {r["label"]: r for r in result["cohorts"]}
    july, september = rows["Jul 2026"], rows["Sep 2026"]
    assert july["size"] == 2 and july["retention"][0] == 100.0
    assert july["retention"][1] == 50.0 and july["retention"][2] == 0.0  # Aug: A back; Sep: nobody
    assert july["retention"][3] is None                                    # Oct is unfinished
    assert september["size"] == 1 and september["retention"][1] is None   # partial October
    assert result["partialMonth"] == "Oct 2026"
    assert result["averages"][0] == 100.0


def test_kpis_for_a_past_period_use_only_data_up_to_its_end():
    # 100 ten days ago, 200 sixty days ago, 400 two years ago.
    snapshot = a.build_snapshot([order("A", 10, 100), order("B", 60, 200), order("C", 700, 400)])
    end = AS_OF - timedelta(days=45)  # a period that ends before the 100 order
    values, _ = a.kpis(snapshot, 30, end)
    assert values["revenue"] == 200.0          # only the order 60 days ago falls in the 30 days to `end`
    assert values["totalCustomers"] == 2       # A had not ordered yet by then
    assert a.kpis(snapshot, 30, AS_OF + timedelta(days=500))[0]["revenue"] == 100.0  # later than the data is cut back
    values, _ = a.kpis(snapshot, 30, AS_OF - timedelta(days=2000))
    assert values["revenue"] is None           # the period ends before the first order


def test_executive_summary_names_the_dates_of_a_past_period():
    snapshot = a.build_snapshot([order("A", 10, 100), order("B", 60, 200), order("C", 700, 400)])
    end = AS_OF - timedelta(days=45)
    values, deltas = a.kpis(snapshot, 30, end)
    deltas["revenue"] = 12.0
    assert " to " in a.executive_summary(snapshot, values, deltas, 30, end)["headline"]
    assert "last 30 days" in a.executive_summary(snapshot, values, deltas, 30)["headline"]
