from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.plan_repository import PlanRepository
from app.schemas.plan import PlanListResponse, PlanResponse


class PlanService:
    def __init__(self, session: AsyncSession) -> None:
        self.plan_repository = PlanRepository(session)

    async def list_active_plans(self) -> PlanListResponse:
        plans = await self.plan_repository.list_active()
        return PlanListResponse(items=[PlanResponse.model_validate(plan) for plan in plans])
