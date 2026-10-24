"""Launch Studio step 1: projects, trend uploads, own-product growth and the AI ideas.
All products, files and AI answers here are MADE UP for the tests (no real AI is called)."""

import io
import json
from datetime import date, timedelta

import pytest

from app.core.errors import ApiError
from app.models import Order, ProductSale
from app.services import launch_ai
from app.services.launch_ai import build_inputs, cache_key, validate_ideas
from app.services.product_growth import product_growth, rank, split_products

# --- AI answer validation -------------------------------------------------------------------------


GOOD = {"ideas": [{"name": "Test neck fan", "reason": "Searches for test fan are rising."}, {"name": "Test lamp", "reason": "Related query test lamp is rising."}]}


def test_a_good_answer_is_accepted():
    assert [i["name"] for i in validate_ideas(json.dumps(GOOD))] == ["Test neck fan", "Test lamp"]


def test_code_fences_and_a_sentence_around_the_json_are_tolerated():
    assert len(validate_ideas("```json\n" + json.dumps(GOOD) + "\n```")) == 2
    assert len(validate_ideas("Here you go: " + json.dumps(GOOD) + " Hope it helps!")) == 2


@pytest.mark.parametrize("text", ["", "not json", "[1, 2]", '{"ideas": "none"}', '{"ideas": []}', '{"other": 1}',
                                   '{"ideas": [{"name": "x", "reason": "too short name"}]}',
                                   '{"ideas": [{"name": "Fine name", "reason": "ok"}]}',
                                   '{"ideas": [{"name": 5, "reason": "A reason that is long enough"}]}'])
def test_unusable_answers_raise_a_plain_error(text):
    with pytest.raises(ApiError) as caught:
        validate_ideas(text)
    assert caught.value.status_code == 502 and caught.value.code == "ai_bad_answer"


def test_duplicates_and_extra_ideas_are_dropped():
    many = {"ideas": [{"name": f"Test item {i}", "reason": "A short reason here."} for i in range(8)] + [{"name": "test ITEM 0", "reason": "Same name again."}]}
    assert len(validate_ideas(json.dumps(many))) == 5


def test_the_inputs_sent_to_the_model_are_short_and_have_no_personal_data():
    inputs = build_inputs(
        [{"keyword": "test fan", "label": "rising", "related": [{"query": f"q{i}", "value": "1", "kind": "top"} for i in range(9)]}],
        [f"cat{i}" for i in range(20)], [f"p{i}" for i in range(20)],
    )
    assert len(inputs["trends"][0]["related"]) == 5 and len(inputs["shop_categories"]) == 10 and len(inputs["shop_growing_products"]) == 8
    assert cache_key("k", inputs) == cache_key("k", json.loads(json.dumps(inputs)))        # the same facts give the same fingerprint


class FakeModel:
    model = "fake-model"

    def __init__(self, answer):
        self.answer_text, self.calls = answer, 0

    def answer(self, instructions, turns):
        self.calls += 1
        assert "Do NOT invent" in instructions and "reviews" in instructions          # the no-invention rule is in the prompt
        return self.answer_text


# --- projects ---------------------------------------------------------------------------------------


def test_project_create_list_update_delete(db_client):
    created = db_client.post("/api/v1/launch/projects", json={"productName": "  Test neck fan ", "category": "Gadgets"})
    assert created.status_code == 201
    project = created.json()
    assert project["productName"] == "Test neck fan" and project["status"] == "idea" and project["launchedOn"] is None
    assert [p["id"] for p in db_client.get("/api/v1/launch/projects").json()] == [project["id"]]

    changed = db_client.patch(f"/api/v1/launch/projects/{project['id']}", json={"status": "launched", "notes": "first batch"}).json()
    assert changed["status"] == "launched" and changed["notes"] == "first batch" and changed["launchedOn"] == date.today().isoformat()
    assert changed["category"] == "Gadgets"                                      # not sent, so not changed
    assert db_client.patch(f"/api/v1/launch/projects/{project['id']}", json={"category": ""}).json()["category"] is None

    assert db_client.delete(f"/api/v1/launch/projects/{project['id']}").status_code == 204
    assert db_client.get("/api/v1/launch/projects").json() == []


def test_project_validation_and_not_found(db_client):
    assert db_client.post("/api/v1/launch/projects", json={"productName": "x"}).status_code == 422
    assert db_client.post("/api/v1/launch/projects", json={"productName": " x "}).status_code == 422
    assert db_client.patch("/api/v1/launch/projects/999999", json={"status": "ready"}).status_code == 404
    project = db_client.post("/api/v1/launch/projects", json={"productName": "Test lamp"}).json()
    assert db_client.patch(f"/api/v1/launch/projects/{project['id']}", json={"status": "flying"}).status_code == 422


# --- trend uploads ------------------------------------------------------------------------------------


def weekly_csv(values):
    last = date(2026, 6, 28)
    rows = [f"{(last - timedelta(days=7 * (len(values) - 1 - i))).isoformat()},{v}" for i, v in enumerate(values)]
    return "Category: All categories\n\nWeek,test fan: (Pakistan)\n" + "\n".join(rows) + "\n\nTOP\nquery,value\ntest fan usb,100\n"


def test_upload_saves_the_parsed_trend_with_its_label(db_client):
    files = {"file": ("trend.csv", io.BytesIO(weekly_csv([10] * 8 + [20] * 4).encode()), "text/csv")}
    body = db_client.post("/api/v1/launch/trends/upload", files=files)
    assert body.status_code == 201
    trend = body.json()[0]
    assert (trend["keyword"], trend["region"], trend["label"], trend["ratio"]) == ("test fan", "Pakistan", "rising", 2.0)
    assert len(trend["points"]) == 12 and trend["related"][0]["query"] == "test fan usb"
    assert len(db_client.get("/api/v1/launch/trends").json()) == 1
    assert db_client.delete(f"/api/v1/launch/trends/{trend['id']}").status_code == 204


def test_a_short_file_is_kept_but_has_no_label(db_client):
    files = {"file": ("trend.csv", io.BytesIO(weekly_csv([10, 20, 30]).encode()), "text/csv")}
    assert db_client.post("/api/v1/launch/trends/upload", files=files).json()[0]["label"] is None


def test_a_file_that_is_not_a_trends_export_is_refused(db_client):
    files = {"file": ("x.csv", io.BytesIO(b"name,price\nshoe,100\n"), "text/csv")}
    assert db_client.post("/api/v1/launch/trends/upload", files=files).status_code == 422
    files = {"file": ("x.csv", io.BytesIO(weekly_csv([1] * 12).encode()), "text/csv")}
    assert db_client.post("/api/v1/launch/trends/upload", data={"launch_project_id": "999999"}, files=files).status_code == 404


def test_uploading_for_a_project_links_it_and_deleting_the_project_removes_it(db_client):
    project = db_client.post("/api/v1/launch/projects", json={"productName": "Test fan"}).json()
    files = {"file": ("t.csv", io.BytesIO(weekly_csv([5] * 12).encode()), "text/csv")}
    db_client.post("/api/v1/launch/trends/upload", data={"launch_project_id": str(project["id"])}, files=files)
    assert len(db_client.get(f"/api/v1/launch/trends?launch_project_id={project['id']}").json()) == 1
    db_client.delete(f"/api/v1/launch/projects/{project['id']}")
    assert db_client.get("/api/v1/launch/trends").json() == []


# --- own-product growth ---------------------------------------------------------------------------------


def test_names_on_an_order_are_split_and_tidied():
    assert split_products(" Red  shoes, red shoes ,Blue bag,, ") == ["Red shoes", "Blue bag"]
    assert split_products(None) == []


def test_growth_needs_20_sales_in_the_two_periods_together():
    rows, small = rank({"A": 12, "B": 10, "C": 19}, {"A": 8, "B": 9, "C": 0})
    assert [r.product for r in rows] == ["A"] and small == 2                    # A: 20 together; B: 19 together; C: 19
    rows, _ = rank({"A": 11}, {"A": 9})
    assert rows[0].growth == pytest.approx(11 / 9 - 1) and rows[0].before == 9


def test_only_growing_products_are_listed_fastest_first_and_new_ones_have_no_percentage():
    rows, _ = rank({"fast": 30, "slow": 21, "falling": 10, "new": 25}, {"fast": 10, "slow": 20, "falling": 30, "new": 0})
    assert [r.product for r in rows] == ["fast", "slow", "new"]
    assert rows[-1].growth is None and rows[-1].product == "new"
    assert "falling" not in [r.product for r in rows]


def add_order(db, n, when, products):
    db.add(Order(external_id=f"T-{n}", customer_id=_customer(db), order_date=when, order_value=100, products=products, source="manual"))


_customer_id = []


def _customer(db):
    from app.models import Customer

    if not _customer_id or db.get(Customer, _customer_id[0]) is None:
        _customer_id.clear()
        customer = Customer(external_id="T-C", email="test@example.com", first_name="Test", country="PK")
        db.add(customer)
        db.flush()
        _customer_id.append(customer.id)
    return _customer_id[0]


def test_growth_from_product_names_on_orders(db_session):
    end = date(2026, 6, 30)
    n = 0
    for i in range(14):                                     # last 30 days: 14 orders with the shoes
        n += 1
        add_order(db_session, n, end - timedelta(days=i), "Test shoes, Test bag")
    for i in range(8):                                      # the 30 days before: 8 orders with the shoes
        n += 1
        add_order(db_session, n, end - timedelta(days=31 + i), "test SHOES")
    n += 1
    add_order(db_session, n, end - timedelta(days=89), "Test old item")          # makes the history long enough
    db_session.flush()
    result = product_growth(db_session, 30)
    assert (result.metric, result.source, result.period_end) == ("orders", "real", end)
    assert [(r.product, r.last, r.before) for r in result.rows] == [("Test shoes", 14, 8)]
    assert result.too_small == 1                                                # "Test bag" (the old item is outside both periods)


def test_growth_with_no_data_or_too_little_history(db_session):
    assert product_growth(db_session, 30).reason == "no_data"
    add_order(db_session, 1, date(2026, 6, 30), "Test shoes")
    db_session.flush()
    assert product_growth(db_session, 30).reason == "not_enough_history"


def test_growth_prefers_the_weekly_product_sales_table(db_session):
    monday = date(2026, 1, 5)
    for week in range(40):                                  # 40 weeks, selling more in the last 4
        db_session.add(ProductSale(product="Test fan", week_start=monday + timedelta(days=7 * week), units=2 if week < 36 else 6, source="import"))
    db_session.flush()
    result = product_growth(db_session, 30)
    assert result.metric == "units" and result.rows and result.rows[0].product == "Test fan"
    assert result.rows[0].last > result.rows[0].before


def test_growth_endpoint_checks_days(db_client):
    assert db_client.get("/api/v1/launch/growth?days=7").status_code == 422
    body = db_client.get("/api/v1/launch/growth?days=30").json()
    assert body["reason"] == "no_data" and body["minGroupCount"] == 20


# --- ideas endpoint -----------------------------------------------------------------------------------------


def upload_trend(db_client):
    files = {"file": ("t.csv", io.BytesIO(weekly_csv([10] * 8 + [20] * 4).encode()), "text/csv")}
    return db_client.post("/api/v1/launch/trends/upload", files=files).json()[0]


def test_ideas_are_labelled_cached_and_not_paid_for_twice(db_client, monkeypatch):
    fake = FakeModel(json.dumps(GOOD))
    monkeypatch.setattr(launch_ai, "get_model", lambda settings: fake)
    upload_trend(db_client)
    first = db_client.post("/api/v1/launch/ideas", json={}).json()
    assert first["label"] == "AI suggestion" and first["cached"] is False and first["model"] == "fake-model"
    assert [i["name"] for i in first["ideas"]] == ["Test neck fan", "Test lamp"]
    second = db_client.post("/api/v1/launch/ideas", json={}).json()
    assert second["cached"] is True and fake.calls == 1                         # the saved answer was used
    assert db_client.post("/api/v1/launch/ideas", json={"force": True}).json()["cached"] is False and fake.calls == 2


def test_ideas_need_something_to_go_on(db_client, monkeypatch):
    monkeypatch.setattr(launch_ai, "get_model", lambda settings: FakeModel(json.dumps(GOOD)))
    response = db_client.post("/api/v1/launch/ideas", json={})
    assert response.status_code == 422 and response.json()["error"]["code"] == "nothing_to_go_on"


def test_a_missing_key_and_a_bad_answer_give_clear_errors(db_client, monkeypatch):
    upload_trend(db_client)
    monkeypatch.setattr(launch_ai, "get_model", lambda settings: FakeModel("sorry, I cannot"))
    bad = db_client.post("/api/v1/launch/ideas", json={})
    assert bad.status_code == 502 and bad.json()["error"]["code"] == "ai_bad_answer"
    # A bad answer is not saved, so the next try asks again.
    fake = FakeModel(json.dumps(GOOD))
    monkeypatch.setattr(launch_ai, "get_model", lambda settings: fake)
    assert db_client.post("/api/v1/launch/ideas", json={}).status_code == 200 and fake.calls == 1


def test_asking_for_ideas_is_limited_per_account(db_client, monkeypatch):
    import uuid
    from types import SimpleNamespace

    import app.api.v1.launch as launch
    from app.api.deps import require_user
    from app.main import app
    from app.services.rate_limit import reset_rate_limits

    reset_rate_limits()
    monkeypatch.setattr(launch, "IDEAS_PER_WINDOW", 2)
    monkeypatch.setattr(launch_ai, "get_model", lambda settings: FakeModel(json.dumps(GOOD)))
    same = SimpleNamespace(id=uuid.uuid4(), email="t@example.com", name="T")
    app.dependency_overrides[require_user] = lambda: same
    upload_trend(db_client)
    codes = [db_client.post("/api/v1/launch/ideas", json={"force": True}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    reset_rate_limits()
