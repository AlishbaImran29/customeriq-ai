"""Launch Studio steps 2-6: vendors and quotes, competitor ads, AI content checks, creatives, profit and results.
All names, ads, numbers and AI answers here are MADE UP for the tests (no real AI or storage is called)."""

import io
import json
from datetime import date, timedelta
from itertools import count
from types import SimpleNamespace

import pytest

from app.core.errors import ApiError
from app.models import Customer, LaunchProject, Order
from app.services import launch_ai, launch_ai_content as content
from app.services import supabase_storage as storage
from app.services.vendors import best_quotes, clean_phone

# --- helpers ----------------------------------------------------------------------------------------------


class FakeModel:
    model = "fake-model"

    def __init__(self, answer):
        self.answer_text, self.calls = answer, 0

    def answer(self, instructions, turns):
        self.calls += 1
        assert "Do NOT invent" in instructions
        return self.answer_text if isinstance(self.answer_text, str) else json.dumps(self.answer_text)


def use_model(monkeypatch, answer):
    fake = FakeModel(answer)
    monkeypatch.setattr(launch_ai, "get_model", lambda settings: fake)
    return fake


def project(db_client, name="Test neck fan"):
    return db_client.post("/api/v1/launch/projects", json={"productName": name}).json()


def vendor(db_client, name="Test Traders", phone="0300 1234567"):
    return db_client.post("/api/v1/launch/vendors", json={"name": name, "whatsappPhone": phone, "city": "Lahore"})


_ids = count(1)


def add_orders(db, products, n, *, start, outcome=None, source="courier data", value=3000, customer=None):
    customer = customer or Customer(external_id=f"T-C{next(_ids)}", email=None, first_name="Test", country="PK")
    if customer.id is None:
        db.add(customer)
        db.flush()
    for i in range(n):
        db.add(Order(
            external_id=f"T-O{next(_ids)}", customer_id=customer.id, order_date=start + timedelta(days=i % 20), order_value=value,
            products=products, outcome=outcome, label_source=source if outcome else None, source="manual",
        ))
    db.flush()
    return customer


# --- step 2: vendors and quotes -------------------------------------------------------------------------


@pytest.mark.parametrize("written", ["0300 1234567", "+92 300 1234567", "923001234567", "0300-1234567"])
def test_vendor_phone_numbers_are_normalised(written):
    assert clean_phone(written) == "+923001234567"


@pytest.mark.parametrize("written", ["12345", "abc", "+1 415 555 0100"])
def test_a_bad_phone_is_refused_not_guessed(written):
    with pytest.raises(ApiError) as caught:
        clean_phone(written)
    assert caught.value.status_code == 422 and caught.value.code == "invalid_phone"
    assert clean_phone("  ") is None and clean_phone(None) is None


def test_vendor_crud_and_quality_starts_with_not_enough_data(db_client):
    created = vendor(db_client)
    assert created.status_code == 201
    body = created.json()
    assert body["whatsappPhone"] == "+923001234567" and body["quality"] == {"projects": 0, "closedOrders": 0, "returnRate": None, "needed": 20}
    edited = db_client.patch(f"/api/v1/launch/vendors/{body['id']}", json={"whatsappPhone": "", "notes": "good"}).json()
    assert edited["whatsappPhone"] is None and edited["notes"] == "good" and edited["city"] == "Lahore"
    assert db_client.patch(f"/api/v1/launch/vendors/{body['id']}", json={"whatsappPhone": "nope"}).status_code == 422
    assert db_client.post("/api/v1/launch/vendors", json={"name": "x"}).status_code == 422
    assert [v["id"] for v in db_client.get("/api/v1/launch/vendors").json()] == [body["id"]]
    assert db_client.delete(f"/api/v1/launch/vendors/{body['id']}").status_code == 204


def test_cheapest_and_fastest_are_marked_only_when_there_is_something_to_compare():
    q = lambda i, price, days: SimpleNamespace(id=i, unit_price=price, delivery_days=days)
    assert best_quotes([q(1, 100, 5)]) == (set(), set())
    assert best_quotes([q(1, 100, 5), q(2, 90, 9), q(3, 120, 2)]) == ({2}, {3})
    assert best_quotes([q(1, 100, 5), q(2, 100, 5)]) == ({1, 2}, {1, 2})                      # ties are all marked
    assert best_quotes([q(1, 100, None), q(2, 90, 4)]) == ({2}, set())                          # one delivery time: nothing to compare


def test_quotes_are_listed_with_marks_and_the_chosen_vendor(db_client):
    p, a, b = project(db_client), vendor(db_client, "Test A").json(), vendor(db_client, "Test B", "0301 2345678").json()
    base = f"/api/v1/launch/projects/{p['id']}/quotes"
    db_client.post(base, json={"vendorId": a["id"], "unitPrice": 900, "moq": 50, "deliveryDays": 10, "sampleReceived": True})
    quotes = db_client.post(base, json={"vendorId": b["id"], "unitPrice": 1000, "moq": 20, "deliveryDays": 4}).json()
    by_vendor = {q["vendorName"]: q for q in quotes}
    assert by_vendor["Test A"]["cheapest"] and not by_vendor["Test A"]["fastest"] and by_vendor["Test A"]["sampleReceived"]
    assert by_vendor["Test B"]["fastest"] and not by_vendor["Test B"]["cheapest"]
    chosen = db_client.put(f"/api/v1/launch/projects/{p['id']}/vendor", json={"vendorId": b["id"]}).json()
    assert [q["chosen"] for q in chosen if q["vendorName"] == "Test B"] == [True]
    changed = db_client.patch(f"/api/v1/launch/quotes/{by_vendor['Test B']['id']}", json={"unitPrice": 800}).json()
    assert [q for q in changed if q["vendorName"] == "Test B"][0]["cheapest"]
    assert len(db_client.delete(f"/api/v1/launch/quotes/{by_vendor['Test A']['id']}").json()) == 1


def test_quote_validation(db_client):
    p, v = project(db_client), vendor(db_client).json()
    base = f"/api/v1/launch/projects/{p['id']}/quotes"
    assert db_client.post(base, json={"vendorId": v["id"], "unitPrice": -1}).status_code == 422
    assert db_client.post(base, json={"vendorId": v["id"], "unitPrice": 5, "moq": 0}).status_code == 422
    assert db_client.post(base, json={"vendorId": 999999, "unitPrice": 5}).status_code == 404
    future = (date.today() + timedelta(days=2)).isoformat()
    assert db_client.post(base, json={"vendorId": v["id"], "unitPrice": 5, "quotedOn": future}).status_code == 422


def test_the_quote_request_message_is_an_ai_suggestion_cached_and_link_free(db_client, monkeypatch):
    p, v = project(db_client), vendor(db_client).json()
    fake = use_model(monkeypatch, {"message": "Assalam o Alaikum, I would like a quote for 100 pieces of Test neck fan, please."})
    body = {"projectId": p["id"], "quantity": 100, "language": "en"}
    first = db_client.post(f"/api/v1/launch/vendors/{v['id']}/quote-request", json=body).json()
    assert first["label"] == "AI suggestion" and first["whatsappPhone"] == "+923001234567" and first["cached"] is False
    assert db_client.post(f"/api/v1/launch/vendors/{v['id']}/quote-request", json=body).json()["cached"] is True and fake.calls == 1
    use_model(monkeypatch, {"message": "Please order from https://evil.example now, thanks and regards."})
    again = db_client.post(f"/api/v1/launch/vendors/{v['id']}/quote-request", json={**body, "quantity": 200})
    assert again.status_code == 502 and again.json()["error"]["code"] == "ai_bad_answer"


# --- competitor board -----------------------------------------------------------------------------------


def test_the_ad_library_link_is_only_a_link_with_country_pakistan(db_client):
    url = db_client.get("/api/v1/launch/ad-library-link?keyword=neck fan").json()["url"]
    assert url.startswith("https://www.facebook.com/ads/library/?") and "country=PK" in url and "ad_type=all" in url and "q=neck+fan" in url
    assert db_client.get("/api/v1/launch/ad-library-link?keyword=x").status_code == 422


def test_images_are_recognised_by_their_first_bytes():
    assert storage.detect_image(b"\x89PNG\r\n\x1a\n" + b"0" * 10) == ("png", "image/png")
    assert storage.detect_image(b"\xff\xd8\xff\xe0" + b"0" * 10)[0] == "jpg"
    assert storage.detect_image(b"RIFF1234WEBPVP8 ")[0] == "webp"
    assert storage.detect_image(b"<svg onload=alert(1)>") is None and storage.detect_image(b"GIF89a") is None


def save_ad(db_client, pid, **fields):
    data = {"page_name": "Test Page", "ad_text": "Test neck fan only Rs 1,999. Cash on delivery!", "price_seen": "1999", **fields}
    return db_client.post(f"/api/v1/launch/projects/{pid}/ads", data=data)


def test_saving_and_deleting_an_ad_without_a_screenshot(db_client):
    p = project(db_client)
    saved = save_ad(db_client, p["id"], offer_seen="Free delivery", link="https://example.com/ad")
    assert saved.status_code == 201
    ad = saved.json()
    assert ad["pageName"] == "Test Page" and ad["priceSeen"] == 1999 and ad["hasScreenshot"] is False and ad["screenshotUrl"] is None
    assert len(db_client.get(f"/api/v1/launch/projects/{p['id']}/ads").json()) == 1
    assert db_client.delete(f"/api/v1/launch/ads/{ad['id']}").status_code == 204


def test_ad_validation(db_client):
    p = project(db_client)
    assert save_ad(db_client, p["id"], link="javascript:alert(1)").status_code == 422
    assert save_ad(db_client, p["id"], date_seen=(date.today() + timedelta(days=3)).isoformat()).status_code == 422
    assert db_client.post(f"/api/v1/launch/projects/{p['id']}/ads", data={"page_name": "x"}).status_code == 422
    assert save_ad(db_client, 999999).status_code == 404


def test_a_screenshot_needs_storage_and_must_be_a_real_image(db_client, monkeypatch):
    p = project(db_client)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 50
    without_storage = db_client.post(
        f"/api/v1/launch/projects/{p['id']}/ads", data={"page_name": "Test Page"}, files={"screenshot": ("a.png", io.BytesIO(png), "image/png")})
    assert without_storage.status_code == 503 and without_storage.json()["error"]["code"] == "storage_not_configured"

    uploaded = []
    monkeypatch.setattr(storage, "_call", lambda settings, method, path, body, ctype: uploaded.append((method, path, ctype)) or {"signedURL": "/object/sign/x?token=t"})
    monkeypatch.setattr(storage, "storage_configured", lambda settings: True)
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "supabase_url", "https://example.supabase.co", raising=False)
    ok = db_client.post(f"/api/v1/launch/projects/{p['id']}/ads", data={"page_name": "Test Page"}, files={"screenshot": ("a.png", io.BytesIO(png), "image/png")})
    assert ok.status_code == 201 and ok.json()["hasScreenshot"] is True
    assert uploaded[0][0] == "POST" and uploaded[0][1].startswith("/object/competitor-ads/project-") and uploaded[0][2] == "image/png"
    fake_svg = db_client.post(f"/api/v1/launch/projects/{p['id']}/ads", data={"page_name": "Test Page"}, files={"screenshot": ("a.png", io.BytesIO(b"<svg/>"), "image/png")})
    assert fake_svg.status_code == 422 and fake_svg.json()["error"]["code"] == "not_an_image"
    big = db_client.post(f"/api/v1/launch/projects/{p['id']}/ads", data={"page_name": "Test Page"}, files={"screenshot": ("a.png", io.BytesIO(png + b"0" * (3 * 1024 * 1024)), "image/png")})
    assert big.status_code == 413


ANALYSIS = {
    "ads": [{"id": 1, "hook_type": "discount", "offer": "Free delivery", "price": 1999, "cta": "Order now", "cod_mentioned": True, "language": "english"}],
    "summary": {"patterns": ["All ads lead with the price."], "gaps": ["No ad explains how to use the product."]},
}


def test_competitor_analysis_is_validated_cached_and_checks_numbers(db_client, monkeypatch):
    p = project(db_client)
    ad_id = save_ad(db_client, p["id"]).json()["id"]
    answer = json.loads(json.dumps(ANALYSIS))
    answer["ads"][0]["id"] = ad_id
    fake = use_model(monkeypatch, answer)
    first = db_client.post(f"/api/v1/launch/projects/{p['id']}/ads/analyse", json={}).json()
    assert first["label"] == "AI suggestion" and first["cached"] is False
    assert first["ads"][0]["hookType"] == "discount" and first["ads"][0]["price"] == 1999 and first["ads"][0]["codMentioned"] is True
    assert first["patterns"] and first["gaps"]
    assert db_client.post(f"/api/v1/launch/projects/{p['id']}/ads/analyse", json={}).json()["cached"] is True and fake.calls == 1

    # An invented price (not in the ad text or the saved price) is dropped, and an unknown hook type becomes "other".
    answer["ads"][0].update(price=777, hook_type="made_up_type")
    use_model(monkeypatch, answer)
    again = db_client.post(f"/api/v1/launch/projects/{p['id']}/ads/analyse", json={"force": True}).json()
    assert again["ads"][0]["price"] is None and again["ads"][0]["hookType"] == "other"


def test_analysis_needs_a_saved_ad_and_a_usable_answer(db_client, monkeypatch):
    p = project(db_client)
    assert db_client.post(f"/api/v1/launch/projects/{p['id']}/ads/analyse", json={}).json()["error"]["code"] == "no_ads"
    save_ad(db_client, p["id"])
    use_model(monkeypatch, {"ads": [{"id": 9999, "hook_type": "other"}], "summary": {"patterns": ["x" * 10], "gaps": []}})
    assert db_client.post(f"/api/v1/launch/projects/{p['id']}/ads/analyse", json={}).status_code == 502
    use_model(monkeypatch, "not json at all")
    assert db_client.post(f"/api/v1/launch/projects/{p['id']}/ads/analyse", json={}).status_code == 502


# --- unprovable claims -----------------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "Over 5000 sold already!", "10k customers trust us", "Only 3 left in stock", "Rated 5 stars", "★★★★★ amazing", "Customers say it is great",
    "Real testimonials inside", "Our best seller", "As seen on TV", "#1 fan in Pakistan", "1,200+ happy buyers", "5-star reviews",
])
def test_claims_that_cannot_be_proven_are_detected(text):
    assert content.unprovable_claim(text)


@pytest.mark.parametrize("text", [
    "Cash on delivery all over Pakistan", "Buy 2 and get free delivery", "Stay cool this summer", "Order today, pay when it arrives",
    "Rs 1,999 only", "USB rechargeable, 3 speeds",
])
def test_honest_copy_is_not_flagged(text):
    assert not content.unprovable_claim(text)


def good_ad(**changes):
    return {"hook": "Hot days? Stay cool.", "primary_text": "A small rechargeable fan you wear on your neck. Pay when it arrives.", "headline": "Neck fan", "cta": "Order Now", "angle": "cod_trust", **changes}


def full_creatives(**changes):
    angles = ["price", "quality", "urgency", "social_proof", "cod_trust"]
    return {"meta_ads": [good_ad(angle=a, hook=f"Hook {a} for the test fan") for a in angles],
            "instagram": {"caption": "Cool summer days with the test fan.", "hashtags": ["summer", "#testfan", "test fan!"]},
            "whatsapp_status": "Test fan, cash on delivery. Message me to order.", **changes}


def test_creatives_check_keeps_honest_items_and_counts_removed_ones():
    answer = full_creatives()
    answer["meta_ads"][1] = good_ad(angle="quality", primary_text="Over 5000 sold, customers say it is the best.")
    answer["whatsapp_status"] = "Only 4 left, hurry!"
    result = content.check_creatives(json.dumps(answer))
    assert [a["angle"] for a in result["meta_ads"]] == ["price", "urgency", "social_proof", "cod_trust"]
    assert result["whatsapp_status"] is None and result["removed"] == 2
    assert result["instagram"]["hashtags"] == ["#summer", "#testfan"]                  # tidied, "#" added, duplicates dropped


def test_creatives_with_a_bad_shape_or_nothing_usable_are_refused():
    for bad in ("nope", json.dumps({"meta_ads": "x"}), json.dumps({"meta_ads": [], "instagram": None, "whatsapp_status": None})):
        with pytest.raises(ApiError) as caught:
            content.check_creatives(bad)
        assert caught.value.status_code == 502
    assert content.check_meta_ad(good_ad(angle="made_up")) is None and content.check_meta_ad(good_ad(headline="")) is None


BRIEF = {"productName": "Test neck fan", "features": ["USB rechargeable", "3 speeds"], "price": 1999, "offer": "Free delivery",
         "targetCustomer": "students", "language": "roman_ur", "tone": "friendly"}


def test_generate_creatives_is_labelled_cached_and_uses_the_competitor_findings(db_client, monkeypatch):
    p = project(db_client)
    fake = use_model(monkeypatch, full_creatives())
    url = f"/api/v1/launch/projects/{p['id']}/creatives/generate"
    first = db_client.post(url, json=BRIEF).json()
    assert first["label"] == "AI suggestion" and len(first["metaAds"]) == 5 and first["usedCompetitorAnalysis"] is False
    assert first["instagram"]["hashtags"][0] == "#summer" and first["whatsappStatus"]["text"]
    assert db_client.post(url, json=BRIEF).json()["cached"] is True and fake.calls == 1

    ad_id = save_ad(db_client, p["id"]).json()["id"]
    analysis = json.loads(json.dumps(ANALYSIS))
    analysis["ads"][0]["id"] = ad_id
    use_model(monkeypatch, analysis)
    db_client.post(f"/api/v1/launch/projects/{p['id']}/ads/analyse", json={})
    seen = {}
    fake2 = use_model(monkeypatch, full_creatives())
    original = fake2.answer
    fake2.answer = lambda instructions, turns: seen.setdefault("prompt", turns[0].content) and original(instructions, turns)
    second = db_client.post(url, json=BRIEF).json()
    assert second["usedCompetitorAnalysis"] is True and second["cached"] is False
    assert "No ad explains how to use the product." in seen["prompt"]


def test_regenerate_one_item_and_the_save_edit_delete_cycle(db_client, monkeypatch):
    p = project(db_client)
    use_model(monkeypatch, {"meta_ad": good_ad(angle="price", hook="A fresh hook for the test fan")})
    new = db_client.post(f"/api/v1/launch/projects/{p['id']}/creatives/regenerate", json={"kind": "meta_ad", "brief": BRIEF, "current": good_ad()}).json()
    assert new["label"] == "AI suggestion" and new["content"]["hook"] == "A fresh hook for the test fan"
    saved = db_client.post(f"/api/v1/launch/projects/{p['id']}/creatives", json={"kind": "meta_ad", "content": new["content"]})
    assert saved.status_code == 201 and saved.json()["aiGenerated"] is True
    cid = saved.json()["id"]
    edited = db_client.patch(f"/api/v1/launch/creatives/{cid}", json={"content": {**new["content"], "headline": "My own headline"}}).json()
    assert edited["content"]["headline"] == "My own headline" and edited["aiGenerated"] is False
    assert len(db_client.get(f"/api/v1/launch/projects/{p['id']}/creatives").json()) == 1
    assert db_client.delete(f"/api/v1/launch/creatives/{cid}").status_code == 204

    use_model(monkeypatch, {"meta_ad": good_ad(primary_text="Over 9000 sold!")})
    assert db_client.post(f"/api/v1/launch/projects/{p['id']}/creatives/regenerate", json={"kind": "meta_ad", "brief": BRIEF}).status_code == 502


def test_saved_content_must_have_the_right_shape(db_client):
    p = project(db_client)
    url = f"/api/v1/launch/projects/{p['id']}/creatives"
    assert db_client.post(url, json={"kind": "meta_ad", "content": {"hook": "only a hook"}}).status_code == 422
    assert db_client.post(url, json={"kind": "whatsapp_status", "content": {"text": ""}}).status_code == 422
    assert db_client.post(url, json={"kind": "instagram", "content": {"caption": "ok", "hashtags": "nope"}}).status_code == 422
    assert db_client.post(url, json={"kind": "whatsapp_status", "content": {"text": "Order now"}}).status_code == 201
    assert db_client.post(url, json={"kind": "poster", "content": {}}).status_code == 422


def test_ai_calls_are_limited_per_account(db_client, monkeypatch):
    import uuid

    import app.api.v1.launch_steps as steps
    from app.api.deps import require_user
    from app.main import app
    from app.services.rate_limit import reset_rate_limits

    reset_rate_limits()
    monkeypatch.setattr(steps, "AI_CALLS_PER_WINDOW", 2)
    same = SimpleNamespace(id=uuid.uuid4(), email="t@example.com", name="T", role="owner")
    app.dependency_overrides[require_user] = lambda: same
    p = project(db_client)
    use_model(monkeypatch, full_creatives())
    url = f"/api/v1/launch/projects/{p['id']}/creatives/generate"
    codes = [db_client.post(url, json={**BRIEF, "force": True}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    reset_rate_limits()


# --- step 5: profit ----------------------------------------------------------------------------------------


PROFIT = {"cost": 1000, "price": 2500, "packing": 50, "courierFee": 250, "returnShipping": 150, "returnRate": 0.2, "adBudget": 10000}


def test_profit_endpoint_matches_the_hand_example(db_client):
    body = db_client.post("/api/v1/launch/profit/calculate", json=PROFIT).json()
    assert body["label"] == "Estimate from your numbers"
    assert (body["profitDelivered"], body["lossReturned"], body["profitPerOrderPlaced"], body["ordersToRecoverBudget"]) == (1200, 450, 870, 12)
    assert body["warnings"] == []
    assert db_client.post("/api/v1/launch/profit/calculate", json={**PROFIT, "returnRate": 2}).status_code == 422
    assert db_client.post("/api/v1/launch/profit/calculate", json={**PROFIT, "price": 0}).status_code == 422


def test_profit_defaults_use_the_chosen_vendor_and_need_20_courier_orders_for_a_return_rate(db_client, db_session):
    p, v = project(db_client), vendor(db_client).json()
    base = f"/api/v1/launch/projects/{p['id']}"
    empty = db_client.get(f"{base}/profit-defaults").json()
    assert empty["cost"] is None and empty["returnRate"] is None and empty["returnRateNeeded"] == 20 and empty["saved"] is None

    db_client.post(f"{base}/quotes", json={"vendorId": v["id"], "unitPrice": 950})
    db_client.put(f"{base}/vendor", json={"vendorId": v["id"]})
    add_orders(db_session, "Test other", 15, start=date(2026, 1, 1), outcome="delivered")
    add_orders(db_session, "Test other", 4, start=date(2026, 1, 1), outcome="returned")
    assert db_client.get(f"{base}/profit-defaults").json()["returnRate"] is None                  # 19 closed orders
    add_orders(db_session, "Test other", 1, start=date(2026, 1, 1), outcome="returned", source="proxy: cancellations")
    assert db_client.get(f"{base}/profit-defaults").json()["returnRate"] is None                  # a proxy label is not courier data
    add_orders(db_session, "Test other", 1, start=date(2026, 1, 1), outcome="delivered")
    got = db_client.get(f"{base}/profit-defaults").json()
    assert got["cost"] == 950 and got["costSource"] == "Test Traders"
    assert got["returnRate"] == pytest.approx(4 / 20) and got["returnRateOrders"] == 20

    saved = db_client.put(f"{base}/profit", json=PROFIT)
    assert saved.status_code == 200 and db_client.get(f"{base}/profit-defaults").json()["saved"]["price"] == 2500


# --- step 6: launch and results -----------------------------------------------------------------------------


def test_launch_date_rules(db_client):
    p = project(db_client)
    url = f"/api/v1/launch/projects/{p['id']}/launch"
    assert db_client.post(url, json={"launchedOn": (date.today() + timedelta(days=1)).isoformat()}).status_code == 422
    done = db_client.post(url, json={"launchedOn": "2026-03-01"}).json()
    assert done == {"status": "launched", "launchedOn": "2026-03-01"}
    assert db_client.get("/api/v1/launch/projects").json()[0]["launchedOn"] == "2026-03-01"


def test_linking_products_and_searching_names(db_client, db_session):
    p = project(db_client)
    add_orders(db_session, "Test neck fan, Test lamp", 2, start=date(2026, 2, 1))
    names = [n["name"] for n in db_client.get("/api/v1/launch/product-names?q=neck").json()]
    assert names == ["Test neck fan"]
    assert db_client.get("/api/v1/launch/product-names?q=%25%25").json() == []                          # a % is searched as a letter, not a wildcard
    base = f"/api/v1/launch/projects/{p['id']}/products"
    linked = db_client.post(base, json={"name": "  test NECK   fan "}).json()
    assert [x["name"] for x in linked] == ["test NECK fan"]
    assert len(db_client.post(base, json={"name": "Test Neck Fan"}).json()) == 1                      # the same product is not linked twice
    assert db_client.delete(f"{base}/{linked[0]['id']}").json() == []
    assert db_client.delete(f"{base}/999999").status_code == 404


def test_results_before_launch_or_without_products(db_client):
    p = project(db_client)
    assert db_client.get(f"/api/v1/launch/projects/{p['id']}/results").json()["reason"] == "not_launched"
    db_client.post(f"/api/v1/launch/projects/{p['id']}/launch", json={"launchedOn": "2026-03-01"})
    assert db_client.get(f"/api/v1/launch/projects/{p['id']}/results").json()["reason"] == "no_products"


def test_results_count_real_orders_and_hide_rates_below_the_minimum(db_client, db_session):
    p = project(db_client)
    base = f"/api/v1/launch/projects/{p['id']}"
    db_client.post(f"{base}/launch", json={"launchedOn": "2026-03-01"})
    db_client.post(f"{base}/products", json={"name": "Test neck fan"})
    buyer = add_orders(db_session, "Test neck fan, Test lamp", 2, start=date(2026, 3, 1), outcome="delivered", value=3000)
    add_orders(db_session, "Test neck fan", 1, start=date(2026, 3, 5), outcome="returned", value=3000)
    add_orders(db_session, "Test neck fan", 3, start=date(2026, 2, 1), outcome="delivered")             # before the launch: not counted
    add_orders(db_session, "Test lamp", 4, start=date(2026, 3, 5), outcome="delivered")                # another product: not counted
    r = db_client.get(f"{base}/results").json()
    assert (r["orders"], r["revenue"], r["customers"], r["closedOrders"]) == (3, 9000, 2, 3)
    assert r["returnRate"] is None and r["returnNeeded"] == 17 and r["realProfitPerOrder"] is None and r["minGroupCount"] == 20
    assert buyer.id is not None


def test_results_with_enough_orders_show_the_return_rate_and_real_vs_expected_profit(db_client, db_session):
    p = project(db_client)
    base = f"/api/v1/launch/projects/{p['id']}"
    db_client.post(f"{base}/launch", json={"launchedOn": "2026-03-01"})
    db_client.post(f"{base}/products", json={"name": "Test neck fan"})
    db_client.put(f"{base}/profit", json=PROFIT)
    repeat = add_orders(db_session, "Test neck fan", 16, start=date(2026, 3, 1), outcome="delivered", value=2500)
    add_orders(db_session, "Test neck fan", 4, start=date(2026, 3, 1), outcome="returned", value=2500)
    r = db_client.get(f"{base}/results").json()
    assert r["closedOrders"] == 20 and r["returnRate"] == pytest.approx(0.2) and r["repeatBuyers"] == 2 and r["hasProfitInputs"] is True
    # 16 delivered earn 2500-1000-50-250 = 1200 each; 4 returned lose 50+250+150 = 450 each: (16*1200 - 4*450) / 20 = 870
    assert r["realProfitPerOrder"] == 870 and r["expectedProfitPerOrder"] == 870
    assert repeat.id is not None


def test_a_vendors_return_rate_comes_from_orders_of_the_projects_that_chose_it(db_client, db_session):
    p, v = project(db_client), vendor(db_client).json()
    base = f"/api/v1/launch/projects/{p['id']}"
    db_client.put(f"{base}/vendor", json={"vendorId": v["id"]})
    db_client.post(f"{base}/launch", json={"launchedOn": "2026-03-01"})
    db_client.post(f"{base}/products", json={"name": "Test neck fan"})
    add_orders(db_session, "Test neck fan", 14, start=date(2026, 3, 1), outcome="delivered")
    add_orders(db_session, "Test neck fan", 5, start=date(2026, 3, 1), outcome="returned")
    quality = [x for x in db_client.get("/api/v1/launch/vendors").json() if x["id"] == v["id"]][0]["quality"]
    assert quality["returnRate"] is None and quality["closedOrders"] == 19 and quality["needed"] == 1
    add_orders(db_session, "Test neck fan", 1, start=date(2026, 3, 1), outcome="returned")
    quality = [x for x in db_client.get("/api/v1/launch/vendors").json() if x["id"] == v["id"]][0]["quality"]
    assert quality["returnRate"] == pytest.approx(6 / 20) and quality["projects"] == 1


def test_deleting_a_project_removes_everything_that_belongs_to_it(db_client, db_session):
    p, v = project(db_client), vendor(db_client).json()
    base = f"/api/v1/launch/projects/{p['id']}"
    db_client.post(f"{base}/quotes", json={"vendorId": v["id"], "unitPrice": 5})
    save_ad(db_client, p["id"])
    db_client.post(f"{base}/creatives", json={"kind": "whatsapp_status", "content": {"text": "Order now"}})
    db_client.post(f"{base}/products", json={"name": "Test neck fan"})
    assert db_client.delete(base).status_code == 204
    assert db_client.get(f"{base}/quotes").status_code == 404
    assert db_session.query(LaunchProject).count() == 0
    assert [x["name"] for x in db_client.get("/api/v1/launch/vendors").json()] == ["Test Traders"]        # the vendor book is kept
