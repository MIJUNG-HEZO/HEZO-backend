from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import (
    CurrentUser,
    get_plan_policy_service,
    get_plan_service,
    require_authenticated,
)
from app.core.cache import cache_get_with_fallback, cache_set, get_redis_client
from app.core.config import settings
from app.schemas.plan import PlanListResponse, PlanUsageResponse
from app.services.plan_policy_service import PlanPolicyService
from app.services.plan_service import PlanService

router = APIRouter(prefix="/plans", tags=["Plans"])

PLANS_CACHE_KEY = "hezo:plans:active"
PLANS_CACHE_TTL = 600  # 10분


@router.get("", response_model=PlanListResponse)
async def list_plans(
    plan_service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanListResponse:
    # 이 엔드포인트는 인증 의존성이 없다 — 플랜 카탈로그는 전 사용자 공통 데이터이므로
    # 고정 키(PLANS_CACHE_KEY)로 캐시해도 사용자 간 데이터 격리 문제가 없다.
    if not settings.redis_enabled:
        return await plan_service.list_active_plans()

    redis_client = get_redis_client()

    async def fetch_from_db() -> str:
        result = await plan_service.list_active_plans()
        try:
            await cache_set(redis_client, PLANS_CACHE_KEY, result.model_dump_json(), PLANS_CACHE_TTL)
        except Exception:
            pass  # 캐시 저장 실패는 무시 — DB 조회 결과 반환은 계속 진행
        return result.model_dump_json()

    raw = await cache_get_with_fallback(redis_client, PLANS_CACHE_KEY, fetch_from_db)
    return PlanListResponse.model_validate_json(raw)


@router.get("/me/usage", response_model=PlanUsageResponse)
async def get_my_plan_usage(
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    plan_policy_service: Annotated[PlanPolicyService, Depends(get_plan_policy_service)],
) -> PlanUsageResponse:
    return await plan_policy_service.get_user_usage(current_user.id)
