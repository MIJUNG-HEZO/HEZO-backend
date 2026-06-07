import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

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
from app.schemas.site import SiteCreateRequest, SiteListResponse, SiteResponse
from app.services.plan_policy_service import PlanPolicyService
from app.services.site_service import SiteService


class FakeSiteService:
    def __init__(self) -> None:
        self.created_by_user_id: UUID | None = None
        self.listed_by_user_id: UUID | None = None

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


class FakeSubscription:
    def __init__(self, plan_id: UUID) -> None:
        self.plan_id = plan_id


class FakePlan:
    def __init__(self, max_sites: int) -> None:
        self.max_sites = max_sites


class FakeSubscriptionRepository:
    def __init__(self, plan_id: UUID) -> None:
        self.plan_id = plan_id

    async def get_active_by_user_id(self, _: UUID) -> FakeSubscription:
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


class FakeListSiteRepository:
    def __init__(self, sites: list[SimpleNamespace]) -> None:
        self.sites = sites
        self.owner_id: UUID | None = None

    async def list_active_sites_by_owner(self, owner_id: UUID) -> list[SimpleNamespace]:
        self.owner_id = owner_id
        return self.sites


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


def test_plan_policy_blocks_site_creation_when_limit_is_exceeded() -> None:
    async def run_policy_check() -> None:
        plan_id = uuid4()
        plan_policy_service = PlanPolicyService(
            plan_repository=FakePlanRepository(plan=FakePlan(max_sites=1)),
            subscription_repository=FakeSubscriptionRepository(plan_id=plan_id),
            site_repository=FakeSiteRepository(used_sites=1),
        )

        with pytest.raises(AppException) as exc_info:
            await plan_policy_service.require_can_create_site(uuid4())

        assert exc_info.value.code == error_codes.SITE_LIMIT_EXCEEDED
        assert exc_info.value.status_code == 403

    asyncio.run(run_policy_check())
