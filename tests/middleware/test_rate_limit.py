import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.middleware.rate_limit import _get_client_ip


@pytest.fixture
def app_with_rate_limit():
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    with patch("app.middleware.rate_limit.aioredis") as mock_redis_mod:
        mock_client = AsyncMock()
        mock_redis_mod.from_url.return_value = mock_client

        from app.middleware.rate_limit import RateLimitMiddleware
        app.add_middleware(
            RateLimitMiddleware,
            redis_url="redis://localhost:6379/0",
            limit=3,
            window_seconds=60,
        )
        yield app, mock_client


def test_allows_requests_under_limit(app_with_rate_limit):
    app, mock_client = app_with_rate_limit
    mock_client.zadd = AsyncMock()
    mock_client.zremrangebyscore = AsyncMock()
    mock_client.zcard.return_value = 1  # 1건 — limit 3 이하
    mock_client.expire = AsyncMock()

    client = TestClient(app)
    response = client.get("/ping")
    assert response.status_code == 200


def test_blocks_requests_over_limit(app_with_rate_limit):
    app, mock_client = app_with_rate_limit
    mock_client.zadd = AsyncMock()
    mock_client.zremrangebyscore = AsyncMock()
    mock_client.zcard.return_value = 4  # 4건 — limit 3 초과
    mock_client.expire = AsyncMock()

    client = TestClient(app)
    response = client.get("/ping")
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def _make_request(headers: list[tuple[bytes, bytes]], client_host: str | None = "127.0.0.1"):
    scope = {
        "type": "http",
        "headers": headers,
        "client": (client_host, 12345) if client_host else None,
    }
    return Request(scope)


def test_get_client_ip_uses_leftmost_x_forwarded_for_entry():
    # CloudFront -> ALB 순으로 프록시를 거치며 각자 IP를 append한다.
    # 왼쪽 끝(첫 번째)이 원본 클라이언트 IP, 오른쪽은 ALB의 내부 IP다.
    request = _make_request(
        headers=[(b"x-forwarded-for", b"1.2.3.4, 10.0.0.5")],
        client_host="10.0.0.5",  # ALB가 맺은 TCP 연결의 IP (원본 클라이언트가 아님)
    )
    assert _get_client_ip(request) == "1.2.3.4"


def test_get_client_ip_falls_back_to_request_client_when_header_absent():
    # 로컬 개발 등 프록시 없이 직접 접속하는 경우
    request = _make_request(headers=[], client_host="192.168.0.10")
    assert _get_client_ip(request) == "192.168.0.10"


def test_get_client_ip_returns_unknown_when_no_header_and_no_client():
    request = _make_request(headers=[], client_host=None)
    assert _get_client_ip(request) == "unknown"


def test_middleware_builds_redis_key_from_leftmost_x_forwarded_for_entry(app_with_rate_limit):
    # 미들웨어 __call__ 내부에서 _get_client_ip()의 반환값이 실제로
    # Redis 키 생성에 쓰이는지 end-to-end로 검증한다 (헬퍼 단위 테스트만으로는
    # __call__ 내부가 request.client.host로 되돌아가도 잡아내지 못함).
    app, mock_client = app_with_rate_limit
    mock_client.zadd = AsyncMock()
    mock_client.zremrangebyscore = AsyncMock()
    mock_client.zcard.return_value = 1  # limit 3 이하 — 통과
    mock_client.expire = AsyncMock()

    client = TestClient(app)
    response = client.get(
        "/ping",
        headers={"X-Forwarded-For": "1.2.3.4, 10.0.0.5"},
    )
    assert response.status_code == 200

    zadd_key = mock_client.zadd.call_args.args[0]
    assert "hezo:rl:1.2.3.4" == zadd_key
    assert "10.0.0.5" not in zadd_key
