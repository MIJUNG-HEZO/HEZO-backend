import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.v1.sites as sites_module
from app.api.deps import (
    CurrentUser,
    get_site_service,
    require_authenticated,
    require_email_verified,
)
from app.core import error_codes
from app.core.enums import ModuleKey, SiteStatus, SiteType
from app.core.exceptions import AppException
from app.main import app
from app.schemas.site import (
    SiteCreateRequest,
    SiteListResponse,
    SitePublishAvailabilityResponse,
    SiteResponse,
    SiteUpdateRequest,
)
from app.services.plan_policy_service import PlanPolicyService
from app.services.site_service import SiteService


class FakeSiteService:
    def __init__(self) -> None:
        self.created_by_user_id: UUID | None = None
        self.listed_by_user_id: UUID | None = None
        self.requested_site_id: UUID | None = None

    async def create_site(
        self,
        *,
        user_id: UUID,
        email_verified: bool,
        payload: SiteCreateRequest,
    ) -> SiteResponse:
        self.created_by_user_id = user_id
        assert email_verified is True
        assert payload.name == "강남 한의원"
        return SiteResponse(
            id=uuid4(),
            name=payload.name,
            site_type=payload.site_type,
            module_key=payload.module_key,
            status="draft",
            is_published=False,
            published_at=None,
            created_at=datetime(2026, 6, 7, tzinfo=UTC),
            updated_at=datetime(2026, 6, 7, tzinfo=UTC),
        )

    async def list_sites(self, *, user_id: UUID) -> SiteListResponse:
        self.listed_by_user_id = user_id
        return SiteListResponse(
            items=[
                SiteResponse(
                    id=uuid4(),
                    name="강남 한의원",
                    site_type=SiteType.LANDING,
                    module_key=ModuleKey.MEDICAL,
                    status=SiteStatus.DRAFT,
                    is_published=False,
                    published_at=None,
                    created_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
                    updated_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
                ),
                SiteResponse(
                    id=uuid4(),
                    name="성수 맛집",
                    site_type=SiteType.STORE,
                    module_key=ModuleKey.RESTAURANT,
                    status=SiteStatus.DRAFT,
                    is_published=False,
                    published_at=None,
                    created_at=datetime(2026, 6, 7, 1, tzinfo=UTC),
                    updated_at=datetime(2026, 6, 7, 1, tzinfo=UTC),
                ),
            ],
            total=2,
        )

    async def get_site(self, *, user_id: UUID, site_id: UUID) -> SiteResponse:
        self.listed_by_user_id = user_id
        self.requested_site_id = site_id
        return SiteResponse(
            id=site_id,
            name="강남 한의원",
            site_type=SiteType.LANDING,
            module_key=ModuleKey.MEDICAL,
            status=SiteStatus.DRAFT,
            is_published=False,
            published_at=None,
            created_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
            updated_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
        )

    async def update_site(
        self,
        *,
        user_id: UUID,
        site_id: UUID,
        payload: SiteUpdateRequest,
    ) -> SiteResponse:
        self.listed_by_user_id = user_id
        self.requested_site_id = site_id
        return SiteResponse(
            id=site_id,
            name=payload.name,
            site_type=payload.site_type,
            module_key=payload.module_key,
            status=SiteStatus.DRAFT,
            is_published=False,
            published_at=None,
            created_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
            updated_at=datetime(2026, 6, 7, 3, tzinfo=UTC),
        )

    async def delete_site(self, *, user_id: UUID, site_id: UUID) -> None:
        self.listed_by_user_id = user_id
        self.requested_site_id = site_id

    async def check_publish_availability(
        self,
        *,
        user_id: UUID,
        site_id: UUID,
    ) -> SitePublishAvailabilityResponse:
        self.listed_by_user_id = user_id
        self.requested_site_id = site_id
        return SitePublishAvailabilityResponse(
            can_publish=True,
            reason=None,
            site_status=SiteStatus.DRAFT,
            is_published=False,
            plan_code="PRO",
            plan_can_publish=True,
        )


class FakeSubscription:
    def __init__(self, plan_id: UUID) -> None:
        self.plan_id = plan_id


class FakePlan:
    def __init__(
        self,
        max_sites: int,
        code: str = "PRO",
        can_publish: bool = True,
    ) -> None:
        self.max_sites = max_sites
        self.code = code
        self.can_publish = can_publish


class FakeSubscriptionRepository:
    def __init__(self, plan_id: UUID) -> None:
        self.plan_id = plan_id

    async def get_active_by_user_id(self, _: UUID) -> FakeSubscription:
        return FakeSubscription(plan_id=self.plan_id)

    async def get_active_by_user_id_for_update(self, _: UUID) -> FakeSubscription:
        return FakeSubscription(plan_id=self.plan_id)


class FakePlanRepository:
    def __init__(self, plan: FakePlan) -> None:
        self.plan = plan

    async def get_by_id(self, _: UUID) -> FakePlan:
        return self.plan


class FakeSiteRepository:
    def __init__(self, used_sites: int) -> None:
        self.used_sites = used_sites

    async def count_active_sites_by_owner(self, _: UUID) -> int:
        return self.used_sites

    async def count_published_sites_by_owner(self, _: UUID) -> int:
        return self.used_sites


class FakeListSiteRepository:
    def __init__(self, sites: list[SimpleNamespace]) -> None:
        self.sites = sites
        self.owner_id: UUID | None = None

    async def list_active_sites_by_owner(self, owner_id: UUID) -> list[SimpleNamespace]:
        self.owner_id = owner_id
        return self.sites


class FakeDetailSiteRepository:
    def __init__(self, site: SimpleNamespace | None) -> None:
        self.site = site
        self.site_id: UUID | None = None
        self.owner_id: UUID | None = None

    async def get_active_site_by_id_and_owner(
        self,
        *,
        site_id: UUID,
        owner_id: UUID,
    ) -> SimpleNamespace | None:
        self.site_id = site_id
        self.owner_id = owner_id
        return self.site

    async def update_basic_info(
        self,
        *,
        site: SimpleNamespace,
        name: str,
        site_type: SiteType,
        module_key: ModuleKey,
    ) -> SimpleNamespace:
        site.name = name
        site.site_type = site_type
        site.module_key = module_key
        return site

    async def soft_delete(self, *, site: SimpleNamespace) -> SimpleNamespace:
        site.status = SiteStatus.DELETED
        site.deleted_at = datetime.now(UTC)
        return site


class FakeAsyncSession:
    async def commit(self) -> None:
        return None

    async def refresh(self, _: SimpleNamespace) -> None:
        return None

    async def rollback(self) -> None:
        return None


class FakePublishPolicyService:
    def __init__(self, *, plan_code: str, plan_can_publish: bool) -> None:
        self.plan_code = plan_code
        self.plan_can_publish = plan_can_publish
        self.user_id: UUID | None = None

    async def get_publish_policy(self, user_id: UUID) -> SimpleNamespace:
        self.user_id = user_id
        return SimpleNamespace(
            plan_code=self.plan_code,
            plan_can_publish=self.plan_can_publish,
        )


class FakeFailingPublishPolicyService:
    async def get_publish_policy(self, _: UUID) -> None:
        raise AppException(
            code=error_codes.SUBSCRIPTION_NOT_FOUND,
            message="Active subscription was not found.",
            status_code=404,
        )


def test_create_site_requires_authentication() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/sites",
        json={
            "name": "강남 한의원",
            "site_type": "landing",
            "module_key": "medical",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == error_codes.UNAUTHORIZED


def test_list_sites_requires_authentication() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/sites")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == error_codes.UNAUTHORIZED


def test_get_site_requires_authentication() -> None:
    client = TestClient(app)

    response = client.get(f"/api/v1/sites/{uuid4()}")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == error_codes.UNAUTHORIZED


def test_update_site_requires_authentication() -> None:
    client = TestClient(app)

    response = client.patch(
        f"/api/v1/sites/{uuid4()}",
        json={
            "name": "수정된 한의원",
            "site_type": "landing",
            "module_key": "medical",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == error_codes.UNAUTHORIZED


def test_delete_site_requires_authentication() -> None:
    client = TestClient(app)

    response = client.delete(f"/api/v1/sites/{uuid4()}")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == error_codes.UNAUTHORIZED


def test_check_publish_availability_requires_authentication() -> None:
    client = TestClient(app)

    response = client.get(f"/api/v1/sites/{uuid4()}/publish-availability")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == error_codes.UNAUTHORIZED


def test_list_sites_returns_current_user_sites() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    fake_site_service = FakeSiteService()

    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_site_service] = lambda: fake_site_service

    try:
        client = TestClient(app)
        response = client.get("/api/v1/sites")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["items"][0]["name"] == "강남 한의원"
    assert body["items"][1]["name"] == "성수 맛집"
    assert fake_site_service.listed_by_user_id == current_user.id


def test_get_site_returns_current_user_site() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    site_id = uuid4()
    fake_site_service = FakeSiteService()

    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_site_service] = lambda: fake_site_service

    try:
        client = TestClient(app)
        response = client.get(f"/api/v1/sites/{site_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(site_id)
    assert body["name"] == "강남 한의원"
    assert body["status"] == "draft"
    assert fake_site_service.listed_by_user_id == current_user.id
    assert fake_site_service.requested_site_id == site_id


def test_update_site_returns_updated_site() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    site_id = uuid4()
    fake_site_service = FakeSiteService()

    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_site_service] = lambda: fake_site_service

    try:
        client = TestClient(app)
        response = client.patch(
            f"/api/v1/sites/{site_id}",
            json={
                "name": "수정된 한의원",
                "site_type": "landing",
                "module_key": "medical",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(site_id)
    assert body["name"] == "수정된 한의원"
    assert body["site_type"] == "landing"
    assert body["module_key"] == "medical"
    assert fake_site_service.listed_by_user_id == current_user.id
    assert fake_site_service.requested_site_id == site_id


def test_delete_site_returns_no_content() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    site_id = uuid4()
    fake_site_service = FakeSiteService()

    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_site_service] = lambda: fake_site_service

    try:
        client = TestClient(app)
        response = client.delete(f"/api/v1/sites/{site_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert fake_site_service.listed_by_user_id == current_user.id
    assert fake_site_service.requested_site_id == site_id


def test_check_publish_availability_returns_current_user_site_policy() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    site_id = uuid4()
    fake_site_service = FakeSiteService()

    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_site_service] = lambda: fake_site_service

    try:
        client = TestClient(app)
        response = client.get(f"/api/v1/sites/{site_id}/publish-availability")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "can_publish": True,
        "reason": None,
        "site_status": "draft",
        "is_published": False,
        "plan_code": "PRO",
        "plan_can_publish": True,
    }
    assert fake_site_service.listed_by_user_id == current_user.id
    assert fake_site_service.requested_site_id == site_id


def test_create_site_returns_created_site() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    fake_site_service = FakeSiteService()

    app.dependency_overrides[require_email_verified] = lambda: current_user
    app.dependency_overrides[get_site_service] = lambda: fake_site_service

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/sites",
            json={
                "name": "강남 한의원",
                "site_type": "landing",
                "module_key": "medical",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "강남 한의원"
    assert body["site_type"] == "landing"
    assert body["module_key"] == "medical"
    assert body["status"] == "draft"
    assert body["is_published"] is False
    assert fake_site_service.created_by_user_id == current_user.id


def test_create_site_rejects_invalid_site_module_combination() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))

    app.dependency_overrides[require_email_verified] = lambda: current_user

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/sites",
            json={
                "name": "강남 한의원",
                "site_type": "blog",
                "module_key": "medical",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["error"]["code"] == error_codes.INVALID_SITE_MODULE_COMBINATION


def test_update_site_rejects_invalid_site_module_combination() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))

    app.dependency_overrides[require_authenticated] = lambda: current_user

    try:
        client = TestClient(app)
        response = client.patch(
            f"/api/v1/sites/{uuid4()}",
            json={
                "name": "수정된 한의원",
                "site_type": "blog",
                "module_key": "medical",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["error"]["code"] == error_codes.INVALID_SITE_MODULE_COMBINATION


def test_site_service_requires_email_verification() -> None:
    async def run_create_site() -> None:
        site_service = SiteService(session=None)
        payload = SiteCreateRequest(
            name="강남 한의원",
            site_type=SiteType.LANDING,
            module_key=ModuleKey.MEDICAL,
        )

        with pytest.raises(AppException) as exc_info:
            await site_service.create_site(
                user_id=uuid4(),
                email_verified=False,
                payload=payload,
            )

        assert exc_info.value.code == error_codes.EMAIL_NOT_VERIFIED
        assert exc_info.value.status_code == 403

    asyncio.run(run_create_site())


def test_site_service_returns_site_list_response() -> None:
    async def run_list_sites() -> None:
        user_id = uuid4()
        sites = [
            SimpleNamespace(
                id=uuid4(),
                name="강남 한의원",
                site_type=SiteType.LANDING,
                module_key=ModuleKey.MEDICAL,
                status=SiteStatus.DRAFT,
                is_published=False,
                published_at=None,
                created_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
                updated_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
            )
        ]
        site_service = SiteService(session=None)
        site_service.site_repository = FakeListSiteRepository(sites=sites)

        response = await site_service.list_sites(user_id=user_id)

        assert response.total == 1
        assert response.items[0].name == "강남 한의원"
        assert site_service.site_repository.owner_id == user_id

    asyncio.run(run_list_sites())


def test_site_service_returns_site_detail_response() -> None:
    async def run_get_site() -> None:
        user_id = uuid4()
        site_id = uuid4()
        site = SimpleNamespace(
            id=site_id,
            name="강남 한의원",
            site_type=SiteType.LANDING,
            module_key=ModuleKey.MEDICAL,
            status=SiteStatus.DRAFT,
            is_published=False,
            published_at=None,
            created_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
            updated_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
        )
        site_service = SiteService(session=None)
        site_service.site_repository = FakeDetailSiteRepository(site=site)

        response = await site_service.get_site(user_id=user_id, site_id=site_id)

        assert response.id == site_id
        assert response.name == "강남 한의원"
        assert site_service.site_repository.site_id == site_id
        assert site_service.site_repository.owner_id == user_id

    asyncio.run(run_get_site())


def test_site_service_raises_site_not_found() -> None:
    async def run_get_site() -> None:
        site_service = SiteService(session=None)
        site_service.site_repository = FakeDetailSiteRepository(site=None)

        with pytest.raises(AppException) as exc_info:
            await site_service.get_site(user_id=uuid4(), site_id=uuid4())

        assert exc_info.value.code == error_codes.SITE_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_get_site())


def test_site_service_updates_site_basic_info() -> None:
    async def run_update_site() -> None:
        user_id = uuid4()
        site_id = uuid4()
        site = SimpleNamespace(
            id=site_id,
            name="강남 한의원",
            site_type=SiteType.LANDING,
            module_key=ModuleKey.MEDICAL,
            status=SiteStatus.DRAFT,
            is_published=False,
            published_at=None,
            created_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
            updated_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
        )
        site_service = SiteService(session=None)
        site_service.session = FakeAsyncSession()
        site_service.site_repository = FakeDetailSiteRepository(site=site)
        payload = SiteUpdateRequest(
            name="수정된 한의원",
            site_type=SiteType.LANDING,
            module_key=ModuleKey.MEDICAL,
        )

        response = await site_service.update_site(
            user_id=user_id,
            site_id=site_id,
            payload=payload,
        )

        assert response.id == site_id
        assert response.name == "수정된 한의원"
        assert site_service.site_repository.site_id == site_id
        assert site_service.site_repository.owner_id == user_id

    asyncio.run(run_update_site())


def test_site_service_raises_site_not_found_when_updating_missing_site() -> None:
    async def run_update_site() -> None:
        site_service = SiteService(session=None)
        site_service.site_repository = FakeDetailSiteRepository(site=None)
        payload = SiteUpdateRequest(
            name="수정된 한의원",
            site_type=SiteType.LANDING,
            module_key=ModuleKey.MEDICAL,
        )

        with pytest.raises(AppException) as exc_info:
            await site_service.update_site(
                user_id=uuid4(),
                site_id=uuid4(),
                payload=payload,
            )

        assert exc_info.value.code == error_codes.SITE_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_update_site())


def test_site_service_soft_deletes_site() -> None:
    async def run_delete_site() -> None:
        user_id = uuid4()
        site_id = uuid4()
        site = SimpleNamespace(
            id=site_id,
            name="강남 한의원",
            site_type=SiteType.LANDING,
            module_key=ModuleKey.MEDICAL,
            status=SiteStatus.DRAFT,
            is_published=False,
            published_at=None,
            deleted_at=None,
            created_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
            updated_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
        )
        site_service = SiteService(session=None)
        site_service.session = FakeAsyncSession()
        site_service.site_repository = FakeDetailSiteRepository(site=site)

        await site_service.delete_site(user_id=user_id, site_id=site_id)

        assert site.status == SiteStatus.DELETED
        assert site.deleted_at is not None
        assert site_service.site_repository.site_id == site_id
        assert site_service.site_repository.owner_id == user_id

    asyncio.run(run_delete_site())


def test_site_service_raises_site_not_found_when_deleting_missing_site() -> None:
    async def run_delete_site() -> None:
        site_service = SiteService(session=None)
        site_service.site_repository = FakeDetailSiteRepository(site=None)

        with pytest.raises(AppException) as exc_info:
            await site_service.delete_site(user_id=uuid4(), site_id=uuid4())

        assert exc_info.value.code == error_codes.SITE_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_delete_site())


def test_site_service_returns_publish_available_when_plan_allows_publish() -> None:
    async def run_check_availability() -> None:
        user_id = uuid4()
        site_id = uuid4()
        site = SimpleNamespace(
            id=site_id,
            name="강남 한의원",
            site_type=SiteType.LANDING,
            module_key=ModuleKey.MEDICAL,
            status=SiteStatus.DRAFT,
            is_published=False,
            published_at=None,
            created_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
            updated_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
        )
        site_service = SiteService(session=None)
        site_service.site_repository = FakeDetailSiteRepository(site=site)
        site_service.plan_policy_service = FakePublishPolicyService(
            plan_code="PRO",
            plan_can_publish=True,
        )

        response = await site_service.check_publish_availability(
            user_id=user_id,
            site_id=site_id,
        )

        assert response.can_publish is True
        assert response.reason is None
        assert response.site_status == SiteStatus.DRAFT
        assert response.is_published is False
        assert response.plan_code == "PRO"
        assert response.plan_can_publish is True
        assert site_service.site_repository.site_id == site_id
        assert site_service.site_repository.owner_id == user_id
        assert site_service.plan_policy_service.user_id == user_id

    asyncio.run(run_check_availability())


def test_site_service_returns_publish_unavailable_when_plan_blocks_publish() -> None:
    async def run_check_availability() -> None:
        site_id = uuid4()
        site = SimpleNamespace(
            id=site_id,
            name="강남 한의원",
            site_type=SiteType.LANDING,
            module_key=ModuleKey.MEDICAL,
            status=SiteStatus.DRAFT,
            is_published=False,
            published_at=None,
            created_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
            updated_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
        )
        site_service = SiteService(session=None)
        site_service.site_repository = FakeDetailSiteRepository(site=site)
        site_service.plan_policy_service = FakePublishPolicyService(
            plan_code="FREE",
            plan_can_publish=False,
        )

        response = await site_service.check_publish_availability(
            user_id=uuid4(),
            site_id=site_id,
        )

        assert response.can_publish is False
        assert response.reason == "PLAN_CANNOT_PUBLISH"
        assert response.plan_code == "FREE"
        assert response.plan_can_publish is False

    asyncio.run(run_check_availability())


def test_site_service_raises_site_not_found_when_checking_publish_availability() -> None:
    async def run_check_availability() -> None:
        site_service = SiteService(session=None)
        site_service.site_repository = FakeDetailSiteRepository(site=None)

        with pytest.raises(AppException) as exc_info:
            await site_service.check_publish_availability(user_id=uuid4(), site_id=uuid4())

        assert exc_info.value.code == error_codes.SITE_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_check_availability())


def test_site_service_propagates_subscription_error_for_publish_availability() -> None:
    async def run_check_availability() -> None:
        site = SimpleNamespace(
            id=uuid4(),
            name="강남 한의원",
            site_type=SiteType.LANDING,
            module_key=ModuleKey.MEDICAL,
            status=SiteStatus.DRAFT,
            is_published=False,
            published_at=None,
            created_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
            updated_at=datetime(2026, 6, 7, 2, tzinfo=UTC),
        )
        site_service = SiteService(session=None)
        site_service.site_repository = FakeDetailSiteRepository(site=site)
        site_service.plan_policy_service = FakeFailingPublishPolicyService()

        with pytest.raises(AppException) as exc_info:
            await site_service.check_publish_availability(user_id=uuid4(), site_id=site.id)

        assert exc_info.value.code == error_codes.SUBSCRIPTION_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_check_availability())


def test_plan_policy_blocks_publish_when_limit_is_exceeded() -> None:
    async def run_policy_check() -> None:
        plan_id = uuid4()
        plan_policy_service = PlanPolicyService(
            plan_repository=FakePlanRepository(plan=FakePlan(max_sites=1, can_publish=True)),
            subscription_repository=FakeSubscriptionRepository(plan_id=plan_id),
            site_repository=FakeSiteRepository(used_sites=1),
        )

        with pytest.raises(AppException) as exc_info:
            await plan_policy_service.require_can_publish_site(uuid4())

        assert exc_info.value.code == error_codes.SITE_LIMIT_EXCEEDED
        assert exc_info.value.status_code == 403

    asyncio.run(run_policy_check())


# ---------------------------------------------------------------------------
# Task 5: Redis 캐시 레이어 (get_site / update_site / delete_site)
# ---------------------------------------------------------------------------


class FakeRedisStore:
    """dict 기반 가짜 Redis 클라이언트 — get/setex/delete가 실제 캐시처럼
    동작해서 캐시 히트/미스, 무효화, 사용자 간 키 격리를 검증할 수 있다."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.get_calls: list[str] = []
        self.setex_calls: list[tuple[str, int, str]] = []
        self.delete_calls: list[str] = []

    async def get(self, key: str) -> str | None:
        self.get_calls.append(key)
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.setex_calls.append((key, ttl, value))
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.delete_calls.append(key)
        self.store.pop(key, None)


class CountingFakeSiteService(FakeSiteService):
    """get_site 호출 횟수와 매 호출의 (user_id, site_id)를 추적하는
    FakeSiteService — 캐시 히트 시 서비스(=소유권 검증) 호출이 스킵됐는지,
    반대로 다른 사용자 요청 시 스킵되지 않았는지 검증하기 위한 용도."""

    def __init__(self) -> None:
        super().__init__()
        self.get_site_call_count = 0
        self.get_site_calls: list[tuple[UUID, UUID]] = []

    async def get_site(self, *, user_id: UUID, site_id: UUID) -> SiteResponse:
        self.get_site_call_count += 1
        self.get_site_calls.append((user_id, site_id))
        return await super().get_site(user_id=user_id, site_id=site_id)


def test_get_site_cache_miss_calls_service_and_populates_cache() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    site_id = uuid4()
    fake_site_service = CountingFakeSiteService()
    fake_redis = FakeRedisStore()

    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_site_service] = lambda: fake_site_service

    try:
        with (
            patch.object(sites_module.settings, "redis_enabled", True),
            patch.object(sites_module, "get_redis_client", return_value=fake_redis),
        ):
            client = TestClient(app)
            response = client.get(f"/api/v1/sites/{site_id}")
    finally:
        app.dependency_overrides.clear()

    expected_key = sites_module._site_cache_key(str(site_id), str(current_user.id))

    assert response.status_code == 200
    assert fake_site_service.get_site_call_count == 1
    assert fake_redis.get_calls == [expected_key]
    assert len(fake_redis.setex_calls) == 1
    assert fake_redis.setex_calls[0][0] == expected_key
    assert fake_redis.setex_calls[0][1] == sites_module.SITE_CACHE_TTL
    assert expected_key in fake_redis.store


def test_get_site_cache_hit_skips_service_call() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    site_id = uuid4()
    fake_site_service = CountingFakeSiteService()
    fake_redis = FakeRedisStore()

    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_site_service] = lambda: fake_site_service

    try:
        with (
            patch.object(sites_module.settings, "redis_enabled", True),
            patch.object(sites_module, "get_redis_client", return_value=fake_redis),
        ):
            client = TestClient(app)
            first = client.get(f"/api/v1/sites/{site_id}")
            second = client.get(f"/api/v1/sites/{site_id}")
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    # 첫 요청은 캐시 미스(서비스 호출), 두 번째 요청은 캐시 히트(서비스 스킵)여야 한다.
    assert fake_site_service.get_site_call_count == 1


def test_get_site_cache_does_not_leak_between_different_users_for_same_site_id() -> None:
    """보안 회귀 테스트.

    site_id만으로 캐시 키를 만들면, 사용자 A의 요청으로 채워진 캐시를 다른
    사용자 B가 같은 site_id를 요청했을 때 그대로 재생받아 소유권 검증
    (site_service.get_site 내부의 get_active_site_by_id_and_owner)을 완전히
    우회하는 인가 우회/데이터 유출이 발생한다.

    이 테스트는 캐시 키에 user_id가 포함되어 있어 B의 요청이 A의 캐시를 절대
    히트하지 않는다(=서비스가 B에 대해서도 반드시 다시 호출된다)는 것을 검증한다.
    `_site_cache_key()`에서 user_id를 제거하면(=site_id만 사용) 이 테스트는
    `get_site_call_count == 2` 단언에서 실패해야 한다."""
    user_a = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    user_b = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    site_id = uuid4()
    fake_site_service = CountingFakeSiteService()
    fake_redis = FakeRedisStore()

    app.dependency_overrides[get_site_service] = lambda: fake_site_service

    try:
        with (
            patch.object(sites_module.settings, "redis_enabled", True),
            patch.object(sites_module, "get_redis_client", return_value=fake_redis),
        ):
            client = TestClient(app)

            app.dependency_overrides[require_authenticated] = lambda: user_a
            response_a = client.get(f"/api/v1/sites/{site_id}")

            app.dependency_overrides[require_authenticated] = lambda: user_b
            response_b = client.get(f"/api/v1/sites/{site_id}")
    finally:
        app.dependency_overrides.clear()

    assert response_a.status_code == 200
    assert response_b.status_code == 200

    # 핵심 검증: 같은 site_id라도 사용자가 다르면 서비스(=소유권 검증)가 매번
    # 다시 호출돼야 한다 — 캐시가 소유권 검증을 우회해선 절대 안 된다.
    assert fake_site_service.get_site_call_count == 2
    assert fake_site_service.get_site_calls == [
        (user_a.id, site_id),
        (user_b.id, site_id),
    ]

    key_a = sites_module._site_cache_key(str(site_id), str(user_a.id))
    key_b = sites_module._site_cache_key(str(site_id), str(user_b.id))
    assert key_a != key_b
    assert key_a in fake_redis.store
    assert key_b in fake_redis.store


def test_get_site_does_not_touch_redis_when_disabled() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    site_id = uuid4()
    fake_site_service = CountingFakeSiteService()
    fake_redis = FakeRedisStore()

    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_site_service] = lambda: fake_site_service

    try:
        with patch.object(sites_module, "get_redis_client", return_value=fake_redis):
            client = TestClient(app)
            response = client.get(f"/api/v1/sites/{site_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_site_service.get_site_call_count == 1
    assert fake_redis.get_calls == []
    assert fake_redis.setex_calls == []


def test_update_site_invalidates_cache() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    site_id = uuid4()
    fake_site_service = FakeSiteService()
    fake_redis = FakeRedisStore()
    cache_key = sites_module._site_cache_key(str(site_id), str(current_user.id))
    fake_redis.store[cache_key] = "stale-cached-value"

    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_site_service] = lambda: fake_site_service

    try:
        with (
            patch.object(sites_module.settings, "redis_enabled", True),
            patch.object(sites_module, "get_redis_client", return_value=fake_redis),
        ):
            client = TestClient(app)
            response = client.patch(
                f"/api/v1/sites/{site_id}",
                json={
                    "name": "수정된 한의원",
                    "site_type": "landing",
                    "module_key": "medical",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_redis.delete_calls == [cache_key]
    assert cache_key not in fake_redis.store


def test_delete_site_invalidates_cache() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    site_id = uuid4()
    fake_site_service = FakeSiteService()
    fake_redis = FakeRedisStore()
    cache_key = sites_module._site_cache_key(str(site_id), str(current_user.id))
    fake_redis.store[cache_key] = "stale-cached-value"

    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_site_service] = lambda: fake_site_service

    try:
        with (
            patch.object(sites_module.settings, "redis_enabled", True),
            patch.object(sites_module, "get_redis_client", return_value=fake_redis),
        ):
            client = TestClient(app)
            response = client.delete(f"/api/v1/sites/{site_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert fake_redis.delete_calls == [cache_key]
    assert cache_key not in fake_redis.store


def test_update_and_delete_site_do_not_touch_redis_when_disabled() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    site_id = uuid4()
    fake_site_service = FakeSiteService()
    fake_redis = FakeRedisStore()

    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_site_service] = lambda: fake_site_service

    try:
        with patch.object(sites_module, "get_redis_client", return_value=fake_redis):
            client = TestClient(app)
            patch_response = client.patch(
                f"/api/v1/sites/{site_id}",
                json={
                    "name": "수정된 한의원",
                    "site_type": "landing",
                    "module_key": "medical",
                },
            )
            delete_response = client.delete(f"/api/v1/sites/{site_id}")
    finally:
        app.dependency_overrides.clear()

    assert patch_response.status_code == 200
    assert delete_response.status_code == 204
    assert fake_redis.delete_calls == []
