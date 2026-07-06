import logging
from collections.abc import Awaitable, Callable

import redis.asyncio

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: redis.asyncio.Redis | None = None


def get_redis_client() -> redis.asyncio.Redis:
    """전역 async Redis 클라이언트를 반환한다 (lazy singleton)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.asyncio.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def cache_get(client: redis.asyncio.Redis, key: str) -> str | None:
    value = await client.get(key)
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


async def cache_set(client: redis.asyncio.Redis, key: str, value: str, ttl: int) -> None:
    await client.setex(key, ttl, value)


async def cache_delete(client: redis.asyncio.Redis, key: str) -> None:
    await client.delete(key)


async def cache_get_with_fallback(
    client: redis.asyncio.Redis,
    key: str,
    fallback_fn: Callable[[], Awaitable[str]],
) -> str:
    """Redis 조회를 시도하고, 캐시 히트 시 그 값을 반환한다.

    Redis가 응답하지 않거나(네트워크 장애, 유지보수, 스로틀링 등) 어떤
    예외를 던지더라도 여기서 삼키고 경고 로그만 남긴 뒤 fallback_fn()
    (보통 DB 조회)으로 즉시 폴백한다 — Redis 장애가 요청 실패(500)로
    전파되지 않도록 하는 Graceful Degradation의 핵심 지점."""
    try:
        cached = await cache_get(client, key)
        if cached:
            return cached
    except Exception as e:
        logger.warning("Redis unavailable, falling back to DB: %s", e)
    return await fallback_fn()
