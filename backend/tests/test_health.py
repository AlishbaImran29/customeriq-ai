import pytest
from fastapi.testclient import TestClient

from app.api.v1.health import get_database_status
from app.main import app


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_ok_when_database_reachable(client):
    app.dependency_overrides[get_database_status] = lambda: "ok"
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.parametrize("database", ["not_configured", "unavailable"])
def test_health_degraded_returns_503(client, database):
    app.dependency_overrides[get_database_status] = lambda: database
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": database}


def test_unknown_route_uses_error_shape(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "details": None}
    }


def test_wrong_method_uses_error_shape(client):
    response = client.post("/api/v1/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_cors_allows_configured_frontend_origin(client):
    app.dependency_overrides[get_database_status] = lambda: "ok"
    response = client.get(
        "/api/v1/health", headers={"Origin": "http://localhost:3001"}
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3001"


def test_cors_rejects_unknown_origin(client):
    app.dependency_overrides[get_database_status] = lambda: "ok"
    response = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers
