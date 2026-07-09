import logging

import pybreaker
import redis.exceptions
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get, cache_set, get_redis_client
from app.core.circuit_breakers import redis_plans_cache_breaker
from app.core.config import settings
from app.repositories.plan_repository import PlanRepository
from app.schemas.plan import PlanListResponse, PlanResponse

logger = logging.getLogger(__name__)

_PLANS_CACHE_KEY = "hezo:plans:active"
_PLANS_CACHE_TTL_SECONDS = 600


class PlanService:
    def __init__(self, session: AsyncSession) -> None:
        self.plan_repository = PlanRepository(session)

    async def list_active_plans(self) -> PlanListResponse:
        if settings.redis_enabled:
            cached = await self._get_cached_plans()
            if cached is not None:
                return cached

        plans = await self.plan_repository.list_active()
        response = PlanListResponse(items=[PlanResponse.model_validate(plan) for plan in plans])

        if settings.redis_enabled:
            await self._set_cached_plans(response)

        return response

    async def _get_cached_plans(self) -> PlanListResponse | None:
        try:
            client = get_redis_client()
            raw = await redis_plans_cache_breaker.call_async(cache_get, client, _PLANS_CACHE_KEY)
        except (redis.exceptions.RedisError, pybreaker.CircuitBreakerError) as exc:
            logger.warning("Redis 캐시 조회 실패, Aurora로 폴백: %s", exc)
            return None
        if raw is None:
            return None
        return PlanListResponse.model_validate_json(raw)

    async def _set_cached_plans(self, response: PlanListResponse) -> None:
        try:
            client = get_redis_client()
            await redis_plans_cache_breaker.call_async(
                cache_set,
                client,
                _PLANS_CACHE_KEY,
                response.model_dump_json(),
                _PLANS_CACHE_TTL_SECONDS,
            )
        except (redis.exceptions.RedisError, pybreaker.CircuitBreakerError) as exc:
            logger.warning("Redis 캐시 저장 실패(무시, 다음 요청은 다시 DB 조회): %s", exc)
