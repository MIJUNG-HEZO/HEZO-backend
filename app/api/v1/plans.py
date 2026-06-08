from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import (
    CurrentUser,
    get_plan_policy_service,
    get_plan_service,
    require_authenticated,
)
from app.schemas.plan import PlanListResponse, PlanUsageResponse
from app.services.plan_policy_service import PlanPolicyService
from app.services.plan_service import PlanService

router = APIRouter(prefix="/plans", tags=["Plans"])


@router.get("", response_model=PlanListResponse)
async def list_plans(
    plan_service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanListResponse:
    return await plan_service.list_active_plans()


@router.get("/me/usage", response_model=PlanUsageResponse)
async def get_my_plan_usage(
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    plan_policy_service: Annotated[PlanPolicyService, Depends(get_plan_policy_service)],
) -> PlanUsageResponse:
    return await plan_policy_service.get_user_usage(current_user.id)
