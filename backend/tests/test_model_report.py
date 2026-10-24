"""Model Report Card: scores next to baselines, Shown/Hidden decisions, and the history of changes. Test data only."""

from app.models import ModelReport
from app.services import model_report as mr
from app.services import predictions as pr


def _row(**kw) -> mr.Row:
    base = dict(model="churn", label="Churn prediction", decision="shown", metric="ROC-AUC", model_score=0.80, baseline_score=0.70)
    base.update(kw)
    return mr.Row(**base)


def test_result_to_row_keeps_both_scores_and_the_reason():
    hidden = pr.ModelResult.unavailable("no better", metric="MAE ($)", model_score=10.0, baseline_score=9.0, higher_is_better=False, test_size=50)
    row = mr._from_result("clv", "Customer lifetime value", hidden)
    assert (row.decision, row.reason, row.model_score, row.baseline_score, row.higher_is_better, row.test_size) == ("hidden", "no better", 10.0, 9.0, False, 50)
    shown = mr._from_result("churn", "Churn", pr.ModelResult("available", None, [], metric="ROC-AUC", model_score=0.8, baseline_score=0.7))
    assert shown.decision == "shown" and shown.reason is None


def test_history_line_saved_only_when_something_changed(db_session):
    assert mr.record_changes(db_session, [_row()]) == 1
    assert mr.record_changes(db_session, [_row()]) == 0                                   # same again: no new line
    assert mr.record_changes(db_session, [_row(model_score=0.81)]) == 1                   # a score moved
    assert mr.record_changes(db_session, [_row(model_score=0.81, decision="hidden", reason="no longer beats the baseline")]) == 1
    lines = mr.history(db_session)
    assert [h.decision for h in lines] == ["hidden", "shown", "shown"]
    assert lines[0].reason == "no longer beats the baseline"


def test_each_model_has_its_own_history(db_session):
    mr.record_changes(db_session, [_row(), _row(model="clv", label="Customer lifetime value")])
    assert db_session.query(ModelReport).count() == 2
    assert mr.record_changes(db_session, [_row(), _row(model="clv", label="Customer lifetime value", decision="hidden")]) == 1


def test_report_endpoint_lists_every_model_even_without_data(db_client):
    r = db_client.get("/api/v1/models/report")
    assert r.status_code == 200
    body = r.json()
    names = {row["model"] for row in body["rows"]}
    assert {"churn", "clv", "revenue_forecast", "order_risk"} <= names
    for row in body["rows"]:
        assert row["decision"] in ("shown", "hidden")
        if row["decision"] == "hidden":
            assert row["reason"]                       # a hidden model always says why
    assert len(body["history"]) >= 4                   # the first call saves the first lines
    again = db_client.get("/api/v1/models/report").json()
    assert len(again["history"]) == len(body["history"])   # nothing changed: no new lines
