from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.exceptions import AppException
from app.repositories.plan_repository import PlanRepository
from app.repositories.site_repository import SiteRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.schemas.site import (
    VALID_SITE_MODULE_PAIRS,
    SiteCreateRequest,
    SiteListResponse,
    SitePublishAvailabilityResponse,
    SiteResponse,
    SiteUpdateRequest,
)
from app.services.plan_policy_service import PlanPolicyService


class SiteService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.site_repository = SiteRepository(session)
        self.plan_policy_service = PlanPolicyService(
            plan_repository=PlanRepository(session),
            subscription_repository=SubscriptionRepository(session),
            site_repository=self.site_repository,
        )

    async def create_site(
        self,
        *,
        user_id: UUID,
        email_verified: bool,
        payload: SiteCreateRequest,
    ) -> SiteResponse:
        if not email_verified:
            raise AppException(
                code=error_codes.EMAIL_NOT_VERIFIED,
                message="Email verification is required.",
                status_code=403,
            )

        expected_site_type = VALID_SITE_MODULE_PAIRS.get(payload.module_key)
        if expected_site_type != payload.site_type:
            raise AppException(
                code=error_codes.INVALID_SITE_MODULE_COMBINATION,
                message="Invalid site type and module key combination.",
                status_code=400,
                details={
                    "module_key": payload.module_key,
                    "site_type": payload.site_type,
                    "expected_site_type": expected_site_type,
                },
            )

        await self.plan_policy_service.require_can_create_site(user_id)

        try:
            site = await self.site_repository.create(
                owner_id=user_id,
                name=payload.name,
                site_type=payload.site_type,
                module_key=payload.module_key,
            )
            await self.session.commit()
            await self.session.refresh(site)
        except SQLAlchemyError:
            await self.session.rollback()
            raise

        return SiteResponse.model_validate(site)

    async def list_sites(self, *, user_id: UUID) -> SiteListResponse:
        sites = await self.site_repository.list_active_sites_by_owner(user_id)
        items = [SiteResponse.model_validate(site) for site in sites]
        return SiteListResponse(items=items, total=len(items))

    async def get_site(self, *, user_id: UUID, site_id: UUID) -> SiteResponse:
        site = await self.site_repository.get_active_site_by_id_and_owner(
            site_id=site_id,
            owner_id=user_id,
        )
        if site is None:
            raise AppException(
                code=error_codes.SITE_NOT_FOUND,
                message="Site was not found.",
                status_code=404,
            )

        return SiteResponse.model_validate(site)

    async def update_site(
        self,
        *,
        user_id: UUID,
        site_id: UUID,
        payload: SiteUpdateRequest,
    ) -> SiteResponse:
        expected_site_type = VALID_SITE_MODULE_PAIRS.get(payload.module_key)
        if expected_site_type != payload.site_type:
            raise AppException(
                code=error_codes.INVALID_SITE_MODULE_COMBINATION,
                message="Invalid site type and module key combination.",
                status_code=400,
                details={
                    "module_key": payload.module_key,
                    "site_type": payload.site_type,
                    "expected_site_type": expected_site_type,
                },
            )

        site = await self.site_repository.get_active_site_by_id_and_owner(
            site_id=site_id,
            owner_id=user_id,
        )
        if site is None:
            raise AppException(
                code=error_codes.SITE_NOT_FOUND,
                message="Site was not found.",
                status_code=404,
            )

        try:
            updated_site = await self.site_repository.update_basic_info(
                site=site,
                name=payload.name,
                site_type=payload.site_type,
                module_key=payload.module_key,
            )
            await self.session.commit()
            await self.session.refresh(updated_site)
        except SQLAlchemyError:
            await self.session.rollback()
            raise

        return SiteResponse.model_validate(updated_site)

    async def delete_site(self, *, user_id: UUID, site_id: UUID) -> None:
        site = await self.site_repository.get_active_site_by_id_and_owner(
            site_id=site_id,
            owner_id=user_id,
        )
        if site is None:
            raise AppException(
                code=error_codes.SITE_NOT_FOUND,
                message="Site was not found.",
                status_code=404,
            )

        try:
            await self.site_repository.soft_delete(site=site)
            await self.session.commit()
        except SQLAlchemyError:
            await self.session.rollback()
            raise

    async def publish_site(
        self,
        *,
        user_id: UUID,
        site_id: UUID,
    ) -> SiteResponse:
        site = await self.site_repository.get_active_site_by_id_and_owner(
            site_id=site_id,
            owner_id=user_id,
        )
        if site is None:
            raise AppException(
                code=error_codes.SITE_NOT_FOUND,
                message="Site was not found.",
                status_code=404,
            )

        await self.plan_policy_service.require_can_publish_site(user_id)

        try:
            site = await self.site_repository.publish(site=site)
            await self.session.commit()
            await self.session.refresh(site)
        except SQLAlchemyError:
            await self.session.rollback()
            raise

        return SiteResponse.model_validate(site)

    async def sync_published_from_pipeline(
        self,
        *,
        user_id: UUID,
        site_id: UUID,
    ) -> None:
        """Step Functions 파이프라인 완료 후 PostgreSQL is_published 동기화.

        plan 한도 체크 없음 — 파이프라인이 이미 실행됐으므로 DB 상태만 맞춘다.
        is_published=True이면 no-op (멱등적).
        """
        site = await self.site_repository.get_active_site_by_id_and_owner(
            site_id=site_id,
            owner_id=user_id,
        )
        if site is None or site.is_published:
            return
        try:
            await self.site_repository.publish(site=site)
            await self.session.commit()
        except SQLAlchemyError:
            await self.session.rollback()
            raise

    async def check_publish_availability(
        self,
        *,
        user_id: UUID,
        site_id: UUID,
    ) -> SitePublishAvailabilityResponse:
        site = await self.site_repository.get_active_site_by_id_and_owner(
            site_id=site_id,
            owner_id=user_id,
        )
        if site is None:
            raise AppException(
                code=error_codes.SITE_NOT_FOUND,
                message="Site was not found.",
                status_code=404,
            )

        publish_policy = await self.plan_policy_service.get_publish_policy(user_id)
        can_publish = publish_policy.plan_can_publish

        return SitePublishAvailabilityResponse(
            can_publish=can_publish,
            reason=None if can_publish else "PLAN_CANNOT_PUBLISH",
            site_status=site.status,
            is_published=site.is_published,
            plan_code=publish_policy.plan_code,
            plan_can_publish=publish_policy.plan_can_publish,
        )
