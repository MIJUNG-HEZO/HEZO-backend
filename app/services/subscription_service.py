from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.exceptions import AppException
from app.repositories.plan_repository import PlanRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.schemas.plan import PlanResponse
from app.schemas.subscription import MySubscriptionResponse, SubscriptionResponse


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.plan_repository = PlanRepository(session)
        self.subscription_repository = SubscriptionRepository(session)

    async def get_my_subscription(self, *, user_id: UUID) -> MySubscriptionResponse:
        subscription = await self.subscription_repository.get_active_by_user_id(user_id)
        if subscription is None:
            raise AppException(
                code=error_codes.SUBSCRIPTION_NOT_FOUND,
                message="Active subscription was not found.",
                status_code=404,
            )

        plan = await self.plan_repository.get_by_id(subscription.plan_id)
        if plan is None:
            raise AppException(
                code=error_codes.SUBSCRIPTION_NOT_FOUND,
                message="Active subscription plan was not found.",
                status_code=404,
            )

        return MySubscriptionResponse(
            subscription=SubscriptionResponse(
                id=subscription.id,
                status=subscription.status,
                started_at=subscription.started_at,
                ended_at=subscription.ended_at,
                renewed_at=subscription.renewed_at,
                plan=PlanResponse.model_validate(plan),
            )
        )
