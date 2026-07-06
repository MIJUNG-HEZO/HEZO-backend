import time

import redis.asyncio as aioredis
from starlette.requests import Request
from starlette.responses import JSONResponse


def _get_client_ip(request: Request) -> str:
    """실제 클라이언트 IP를 추출한다.

    이 서비스는 CloudFront → Internal ALB → ECS 뒤에 배포되므로
    ``request.client.host``는 ALB가 연결을 맺은 IP일 뿐, 최종 사용자의
    IP가 아니다. 프록시(ALB, CloudFront)는 표준 관례상 ``X-Forwarded-For``
    헤더에 자신이 요청을 받은 IP를 마지막에 추가(append)하므로, 콤마로
    구분된 목록의 **가장 왼쪽(첫 번째)** 값이 원본 클라이언트 IP다.
    헤더가 없으면(로컬 개발 등 프록시 없이 직접 접속하는 경우) 기존
    ``request.client.host``로 폴백한다.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first_ip = forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip

    return request.client.host if request.client else "unknown"


class RateLimitMiddleware:
    """Redis 정렬 집합(sorted set) 기반 IP당 슬라이딩 윈도우 Rate Limiting."""

    def __init__(self, app, redis_url: str, limit: int = 300, window_seconds: int = 60):
        self.app = app
        self._redis = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        self._limit = limit
        self._window = window_seconds

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        client_ip = _get_client_ip(request)
        key = f"hezo:rl:{client_ip}"
        now = time.time()
        window_start = now - self._window

        await self._redis.zremrangebyscore(key, "-inf", window_start)
        await self._redis.zadd(key, {str(now): now})
        count = await self._redis.zcard(key)
        await self._redis.expire(key, self._window)

        if count > self._limit:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests"},
                headers={"Retry-After": str(self._window)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
