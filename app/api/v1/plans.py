from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_plan_service
from app.schemas.plan import PlanListResponse
from app.services.plan_service import PlanService

router = APIRouter(prefix="/plans", tags=["Plans"])


@router.get("", response_model=PlanListResponse)
async def list_plans(
    plan_service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanListResponse:
    return await plan_service.list_active_plans()
