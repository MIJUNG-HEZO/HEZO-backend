from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.constants import FREE_PLAN_CODE
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

    async def upgrade_plan(
        self,
        *,
        user_id: UUID,
        target_plan_code: str,
    ) -> MySubscriptionResponse:
        target_code = target_plan_code.upper()
        subscription = await self.subscription_repository.get_active_by_user_id_for_update(user_id)
        if subscription is None:
            raise AppException(
                code=error_codes.SUBSCRIPTION_NOT_FOUND,
                message="Active subscription was not found.",
                status_code=404,
            )

        current_plan = await self.plan_repository.get_by_id(subscription.plan_id)
        if current_plan is None:
            raise AppException(
                code=error_codes.PLAN_NOT_FOUND,
                message="Active subscription plan was not found.",
                status_code=404,
            )

        target_plan = await self.plan_repository.get_by_code(target_code)
        if target_plan is None:
            raise AppException(
                code=error_codes.PLAN_NOT_FOUND,
                message="Plan not found.",
                status_code=404,
                details={"plan_code": target_code},
            )
        if not target_plan.is_active:
            raise AppException(
                code=error_codes.PLAN_NOT_ACTIVE,
                message="Plan is not active.",
                status_code=400,
                details={"plan_code": target_code},
            )
        if (
            target_plan.code == FREE_PLAN_CODE
            or target_plan.id == current_plan.id
            or target_plan.price_monthly <= current_plan.price_monthly
        ):
            raise AppException(
                code=error_codes.PLAN_UPGRADE_NOT_ALLOWED,
                message="Target plan is not an upgrade from the current plan.",
                status_code=400,
                details={
                    "current_plan_code": current_plan.code,
                    "target_plan_code": target_plan.code,
                },
            )

        try:
            updated_subscription = await self.subscription_repository.change_plan(
                subscription,
                plan_id=target_plan.id,
                started_at=datetime.now(UTC),
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        return MySubscriptionResponse(
            subscription=SubscriptionResponse(
                id=updated_subscription.id,
                status=updated_subscription.status,
                started_at=updated_subscription.started_at,
                ended_at=updated_subscription.ended_at,
                renewed_at=updated_subscription.renewed_at,
                plan=PlanResponse.model_validate(target_plan),
            )
        )
