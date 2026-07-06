import redis.asyncio

from app.core.config import settings

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
