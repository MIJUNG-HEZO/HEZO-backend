from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SubscriptionStatus
from app.models.subscription import Subscription


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
        started_at: datetime | None = None,
    ) -> Subscription:
        subscription = Subscription(
            user_id=user_id,
            plan_id=plan_id,
            status=status,
            started_at=started_at or datetime.now(UTC),
        )
        self.session.add(subscription)
        return subscription

    async def create_free_subscription(self, *, user_id: UUID, plan_id: UUID) -> Subscription:
        return await self.create(
            user_id=user_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
        )

    async def get_active_by_user_id(self, user_id: UUID) -> Subscription | None:
        stmt = select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_user_id_for_update(self, user_id: UUID) -> Subscription | None:
        stmt = (
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def change_plan(
        self,
        subscription: Subscription,
        *,
        plan_id: UUID,
        started_at: datetime,
    ) -> Subscription:
        subscription.plan_id = plan_id
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.started_at = started_at
        subscription.ended_at = None
        subscription.renewed_at = None
        await self.session.flush()
        return subscription
