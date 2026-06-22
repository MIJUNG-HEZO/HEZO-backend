import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://hezo_app:password@localhost:15432/hezo_dev")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-at-least-32-bytes")

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, require_authenticated
from app.main import app

SITE_ID = "00000000-0000-0000-0000-000000000001"

_fake_user = CurrentUser(
    id=uuid4(),
    email_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
)


def _override_auth():
    return _fake_user


def test_preview_requires_auth():
    with TestClient(app) as client:
        resp = client.post(f"/api/v1/sites/{SITE_ID}/preview")
    assert resp.status_code == 401


def test_preview_mock_mode():
    """P3_BUILD_ENDPOINT 미설정 → 202 + preview_mode=mock."""
    app.dependency_overrides[require_authenticated] = _override_auth
    try:
        with TestClient(app) as client:
            resp = client.post(f"/api/v1/sites/{SITE_ID}/preview")
        assert resp.status_code == 202
        body = resp.json()
        assert body["preview_mode"] == "mock"
        assert body["site_id"] == SITE_ID
    finally:
        app.dependency_overrides.pop(require_authenticated, None)
