from dataclasses import dataclass
from uuid import UUID

from app.core import error_codes
from app.core.exceptions import AppException
from app.repositories.plan_repository import PlanRepository
from app.repositories.site_repository import SiteRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.schemas.plan import PlanUsageDetail, PlanUsagePlan, PlanUsageResponse


@dataclass(frozen=True)
class PublishPolicyResult:
    plan_code: str
    plan_can_publish: bool


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
        """사이트 생성(draft) 허용 여부 확인 — 이메일 인증·구독 존재만 체크.
        발행 한도(max_sites)는 publish 시점에 require_can_publish_site 에서 체크한다.
        """
        subscription = await self.subscription_repository.get_active_by_user_id_for_update(user_id)
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

    async def require_can_publish_site(self, user_id: UUID) -> None:
        """발행 허용 여부 확인 — 플랜 발행 권한 + 발행된 사이트 수 한도 체크."""
        subscription = await self.subscription_repository.get_active_by_user_id_for_update(user_id)
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

        if not plan.can_publish:
            raise AppException(
                code=error_codes.PLAN_CANNOT_PUBLISH,
                message="Your current plan does not support publishing.",
                status_code=403,
            )

        published_count = await self.site_repository.count_published_sites_by_owner(user_id)
        if published_count >= plan.max_sites:
            raise AppException(
                code=error_codes.SITE_LIMIT_EXCEEDED,
                message="Published site limit has been exceeded.",
                status_code=403,
                details={"max_sites": plan.max_sites, "published_sites": published_count},
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

        published_sites = await self.site_repository.count_published_sites_by_owner(user_id)
        remaining_sites = max(plan.max_sites - published_sites, 0)

        return PlanUsageResponse(
            plan=PlanUsagePlan(
                code=plan.code,
                name=plan.name,
            ),
            usage=PlanUsageDetail(
                max_sites=plan.max_sites,
                used_sites=published_sites,
                remaining_sites=remaining_sites,
                can_create_site=True,  # draft는 항상 생성 가능
                can_publish=plan.can_publish and published_sites < plan.max_sites,
            ),
        )

    async def get_publish_policy(self, user_id: UUID) -> PublishPolicyResult:
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

        return PublishPolicyResult(
            plan_code=plan.code,
            plan_can_publish=plan.can_publish,
        )
