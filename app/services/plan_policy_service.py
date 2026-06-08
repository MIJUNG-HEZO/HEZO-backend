from uuid import UUID

from app.core import error_codes
from app.core.exceptions import AppException
from app.repositories.plan_repository import PlanRepository
from app.repositories.site_repository import SiteRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.schemas.plan import PlanUsageDetail, PlanUsagePlan, PlanUsageResponse


class PlanPolicyService:
    def __init__(
        self,
        *,
        plan_repository: PlanRepository,
        subscription_repository: SubscriptionRepository,
        site_repository: SiteRepository,
    ) -> None:
        self.plan_repository = plan_repository
        self.subscription_repository = subscription_repository
        self.site_repository = site_repository

    async def require_can_create_site(self, user_id: UUID) -> None:
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

        used_sites = await self.site_repository.count_active_sites_by_owner(user_id)
        if used_sites >= plan.max_sites:
            raise AppException(
                code=error_codes.SITE_LIMIT_EXCEEDED,
                message="Site creation limit has been exceeded.",
                status_code=403,
                details={"max_sites": plan.max_sites, "used_sites": used_sites},
            )

    async def get_user_usage(self, user_id: UUID) -> PlanUsageResponse:
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

        used_sites = await self.site_repository.count_active_sites_by_owner(user_id)
        remaining_sites = max(plan.max_sites - used_sites, 0)

        return PlanUsageResponse(
            plan=PlanUsagePlan(
                code=plan.code,
                name=plan.name,
            ),
            usage=PlanUsageDetail(
                max_sites=plan.max_sites,
                used_sites=used_sites,
                remaining_sites=remaining_sites,
                can_create_site=used_sites < plan.max_sites,
                can_publish=plan.can_publish,
            ),
        )
