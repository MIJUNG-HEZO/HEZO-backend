from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


def test_health_check_db_ok() -> None:
    client = TestClient(app)

    with patch("app.api.v1.health.check_database_connection", return_value=True):
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "hezo-api", "db": True}


def test_health_check_db_down() -> None:
    client = TestClient(app)

    with patch("app.api.v1.health.check_database_connection", return_value=False):
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "service": "hezo-api", "db": False}


def test_health_check_db_raises_exception() -> None:
    client = TestClient(app)

    with patch(
        "app.api.v1.health.check_database_connection",
        side_effect=Exception("connection refused"),
    ):
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "service": "hezo-api", "db": False}


def test_openapi_schema_contains_health_path() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/v1/health" in response.json()["paths"]
