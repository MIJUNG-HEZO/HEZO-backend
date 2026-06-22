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


def test_chat_requires_auth():
    with TestClient(app) as client:
        resp = client.post(
            f"/api/v1/sites/{SITE_ID}/chat",
            json={"session_id": "test", "user_message": "안녕하세요"},
        )
    assert resp.status_code == 401


def test_chat_mock_mode():
    """P1_AGENT_ENDPOINT 미설정 → mock 응답."""
    app.dependency_overrides[require_authenticated] = _override_auth
    try:
        with TestClient(app) as client:
            resp = client.post(
                f"/api/v1/sites/{SITE_ID}/chat",
                json={"session_id": "test-sess", "user_message": "세무사 사무소입니다"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "assistant_message" in body
        assert body["mock"] is True
        assert body["session_id"] == "test-sess"
    finally:
        app.dependency_overrides.pop(require_authenticated, None)


def test_chat_mock_sequence():
    """연속 호출 시 순차적 mock 메시지 반환."""
    app.dependency_overrides[require_authenticated] = _override_auth
    try:
        with TestClient(app) as client:
            r1 = client.post(
                f"/api/v1/sites/{SITE_ID}/chat",
                json={"session_id": "seq-sess", "user_message": "첫 번째"},
            )
            r2 = client.post(
                f"/api/v1/sites/{SITE_ID}/chat",
                json={"session_id": "seq-sess", "user_message": "두 번째"},
            )
        assert r1.status_code == 200
        assert r2.status_code == 200
        # 두 메시지가 달라야 한다 (순차 mock)
        assert r1.json()["assistant_message"] != r2.json()["assistant_message"]
    finally:
        app.dependency_overrides.pop(require_authenticated, None)
