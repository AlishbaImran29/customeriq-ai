"""Hardening: security headers, and the rate limiter."""

import pytest

from app.core.errors import ApiError
from app.services.rate_limit import check_rate_limit, reset_rate_limits


@pytest.fixture(autouse=True)
def clean_limits():
    reset_rate_limits()
    yield
    reset_rate_limits()


def test_every_response_carries_the_safe_headers(db_client):
    response = db_client.get("/api/v1/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_the_limit_stops_the_sixteenth_use_but_not_another_account():
    for _ in range(15):
        check_rate_limit("ai:user-1", limit=15, window_seconds=600, what="the AI")
    with pytest.raises(ApiError) as caught:
        check_rate_limit("ai:user-1", limit=15, window_seconds=600, what="the AI")
    assert caught.value.status_code == 429 and caught.value.code == "rate_limited"
    check_rate_limit("ai:user-2", limit=15, window_seconds=600, what="the AI")   # a different account is unaffected


def test_uses_expire_after_the_window(monkeypatch):
    import app.services.rate_limit as module

    now = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    check_rate_limit("k", limit=1, window_seconds=60, what="x")
    with pytest.raises(ApiError):
        check_rate_limit("k", limit=1, window_seconds=60, what="x")
    now[0] += 61
    check_rate_limit("k", limit=1, window_seconds=60, what="x")
