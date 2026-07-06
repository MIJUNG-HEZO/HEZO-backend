from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_cache_get_returns_none_when_miss():
    with patch("app.core.cache.redis.asyncio") as mock_redis_mod:
        mock_client = AsyncMock()
        mock_client.get.return_value = None
        mock_redis_mod.from_url.return_value = mock_client

        from app.core.cache import cache_get
        result = await cache_get(mock_client, "hezo:missing_key")
        assert result is None


@pytest.mark.asyncio
async def test_cache_get_returns_value_on_hit():
    with patch("app.core.cache.redis.asyncio") as mock_redis_mod:
        mock_client = AsyncMock()
        mock_client.get.return_value = b'{"id": 1}'
        mock_redis_mod.from_url.return_value = mock_client

        from app.core.cache import cache_get
        result = await cache_get(mock_client, "hezo:plans")
        assert result == '{"id": 1}'


@pytest.mark.asyncio
async def test_cache_set_calls_setex():
    with patch("app.core.cache.redis.asyncio") as mock_redis_mod:
        mock_client = AsyncMock()
        mock_redis_mod.from_url.return_value = mock_client

        from app.core.cache import cache_set
        await cache_set(mock_client, "hezo:plans", '{"id": 1}', ttl=600)
        mock_client.setex.assert_called_once_with("hezo:plans", 600, '{"id": 1}')


@pytest.mark.asyncio
async def test_cache_delete_calls_delete():
    with patch("app.core.cache.redis.asyncio") as mock_redis_mod:
        mock_client = AsyncMock()
        mock_redis_mod.from_url.return_value = mock_client

        from app.core.cache import cache_delete
        await cache_delete(mock_client, "hezo:plans")
        mock_client.delete.assert_called_once_with("hezo:plans")
