import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.v1.plans as plans_module
from app.api.deps import (
    CurrentUser,
    get_plan_policy_service,
    get_plan_service,
    require_authenticated,
)
from app.core import error_codes
from app.core.exceptions import AppException
from app.main import app
from app.schemas.plan import PlanListResponse, PlanUsageDetail, PlanUsagePlan, PlanUsageResponse
from app.services.plan_policy_service import PlanPolicyService
from app.services.plan_service import PlanService


class FakePlanService:
    async def list_active_plans(self) -> PlanListResponse:
        return PlanListResponse(
            items=[
                SimpleNamespace(
                    code="FREE",
                    name="Free",
                    price_monthly=0,
                    currency="KRW",
                    max_sites=1,
                    can_publish=False,
                ),
                SimpleNamespace(
                    code="PRO",
                    name="Pro",
                    price_monthly=29000,
                    currency="KRW",
                    max_sites=1,
                    can_publish=True,
                ),
                SimpleNamespace(
                    code="MAX",
                    name="Max",
                    price_monthly=99000,
                    currency="KRW",
                    max_sites=4,
                    can_publish=True,
                ),
            ]
        )


class CountingFakePlanService(FakePlanService):
    """list_active_plans 호출 횟수를 세는 FakePlanService — 캐시 히트 시
    서비스(DB 조회)가 호출되지 않았음을 검증하기 위한 용도."""

    def __init__(self) -> None:
        self.call_count = 0

    async def list_active_plans(self) -> PlanListResponse:
        self.call_count += 1
        return await super().list_active_plans()


class FakePlanPolicyService:
    def __init__(self) -> None:
        self.user_id: UUID | None = None

    async def get_user_usage(self, user_id: UUID) -> PlanUsageResponse:
        self.user_id = user_id
        return PlanUsageResponse(
            plan=PlanUsagePlan(code="MAX", name="Max"),
            usage=PlanUsageDetail(
                max_sites=4,
                used_sites=2,
                remaining_sites=2,
                can_create_site=True,
                can_publish=True,
            ),
        )


class FakePlanRepository:
    async def list_active(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                code="FREE",
                name="Free",
                price_monthly=0,
                currency="KRW",
                max_sites=1,
                can_publish=False,
            ),
            SimpleNamespace(
                code="PRO",
                name="Pro",
                price_monthly=29000,
                currency="KRW",
                max_sites=1,
                can_publish=True,
            ),
        ]


class FakePolicySubscriptionRepository:
    def __init__(self, subscription: SimpleNamespace | None) -> None:
        self.subscription = subscription
        self.user_id: UUID | None = None

    async def get_active_by_user_id(self, user_id: UUID) -> SimpleNamespace | None:
        self.user_id = user_id
        return self.subscription

    async def get_active_by_user_id_for_update(self, user_id: UUID) -> SimpleNamespace | None:
        self.user_id = user_id
        return self.subscription


class FakePolicyPlanRepository:
    def __init__(self, plan: SimpleNamespace | None) -> None:
        self.plan = plan
        self.plan_id: UUID | None = None

    async def get_by_id(self, plan_id: UUID) -> SimpleNamespace | None:
        self.plan_id = plan_id
        return self.plan


class FakePolicySiteRepository:
    def __init__(self, used_sites: int) -> None:
        self.used_sites = used_sites
        self.owner_id: UUID | None = None

    async def count_active_sites_by_owner(self, owner_id: UUID) -> int:
        self.owner_id = owner_id
        return self.used_sites

    async def count_published_sites_by_owner(self, owner_id: UUID) -> int:
        self.owner_id = owner_id
        return self.used_sites


def test_list_plans_does_not_require_authentication() -> None:
    app.dependency_overrides[get_plan_service] = lambda: FakePlanService()

    try:
        client = TestClient(app)
        response = client.get("/api/v1/plans")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["code"] == "FREE"
    assert body["items"][0]["can_publish"] is False
    assert body["items"][1]["code"] == "PRO"
    assert body["items"][2]["code"] == "MAX"


def test_plan_service_returns_active_plan_list_response() -> None:
    async def run_list_plans() -> None:
        plan_service = PlanService(session=None)
        plan_service.plan_repository = FakePlanRepository()

        response = await plan_service.list_active_plans()

        assert len(response.items) == 2
        assert response.items[0].code == "FREE"
        assert response.items[0].price_monthly == 0
        assert response.items[1].code == "PRO"
        assert response.items[1].can_publish is True

    asyncio.run(run_list_plans())


def test_get_my_plan_usage_requires_authentication() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/plans/me/usage")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == error_codes.UNAUTHORIZED


def test_get_my_plan_usage_returns_current_user_usage() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    fake_plan_policy_service = FakePlanPolicyService()

    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_plan_policy_service] = lambda: fake_plan_policy_service

    try:
        client = TestClient(app)
        response = client.get("/api/v1/plans/me/usage")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == {"code": "MAX", "name": "Max"}
    assert body["usage"] == {
        "max_sites": 4,
        "used_sites": 2,
        "remaining_sites": 2,
        "can_create_site": True,
        "can_publish": True,
    }
    assert fake_plan_policy_service.user_id == current_user.id


def test_plan_policy_service_returns_user_usage() -> None:
    async def run_get_usage() -> None:
        user_id = uuid4()
        plan_id = uuid4()
        plan_policy_service = PlanPolicyService(
            plan_repository=FakePolicyPlanRepository(
                plan=SimpleNamespace(
                    code="PRO",
                    name="Pro",
                    max_sites=1,
                    can_publish=True,
                )
            ),
            subscription_repository=FakePolicySubscriptionRepository(
                subscription=SimpleNamespace(plan_id=plan_id)
            ),
            site_repository=FakePolicySiteRepository(used_sites=0),
        )

        response = await plan_policy_service.get_user_usage(user_id)

        assert response.plan.code == "PRO"
        assert response.plan.name == "Pro"
        assert response.usage.max_sites == 1
        assert response.usage.used_sites == 0
        assert response.usage.remaining_sites == 1
        assert response.usage.can_create_site is True
        assert response.usage.can_publish is True
        assert plan_policy_service.subscription_repository.user_id == user_id
        assert plan_policy_service.plan_repository.plan_id == plan_id
        assert plan_policy_service.site_repository.owner_id == user_id

    asyncio.run(run_get_usage())


def test_plan_policy_service_usage_never_returns_negative_remaining_sites() -> None:
    async def run_get_usage() -> None:
        plan_policy_service = PlanPolicyService(
            plan_repository=FakePolicyPlanRepository(
                plan=SimpleNamespace(
                    code="FREE",
                    name="Free",
                    max_sites=1,
                    can_publish=False,
                )
            ),
            subscription_repository=FakePolicySubscriptionRepository(
                subscription=SimpleNamespace(plan_id=uuid4())
            ),
            site_repository=FakePolicySiteRepository(used_sites=3),
        )

        response = await plan_policy_service.get_user_usage(uuid4())

        assert response.usage.used_sites == 3
        assert response.usage.remaining_sites == 0
        assert response.usage.can_create_site is True  # draft 생성은 항상 허용
        assert response.usage.can_publish is False

    asyncio.run(run_get_usage())


def test_plan_policy_service_usage_raises_subscription_not_found() -> None:
    async def run_get_usage() -> None:
        plan_policy_service = PlanPolicyService(
            plan_repository=FakePolicyPlanRepository(plan=None),
            subscription_repository=FakePolicySubscriptionRepository(subscription=None),
            site_repository=FakePolicySiteRepository(used_sites=0),
        )

        with pytest.raises(AppException) as exc_info:
            await plan_policy_service.get_user_usage(uuid4())

        assert exc_info.value.code == error_codes.SUBSCRIPTION_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_get_usage())


def test_plan_policy_service_usage_raises_when_plan_is_missing() -> None:
    async def run_get_usage() -> None:
        plan_policy_service = PlanPolicyService(
            plan_repository=FakePolicyPlanRepository(plan=None),
            subscription_repository=FakePolicySubscriptionRepository(
                subscription=SimpleNamespace(plan_id=uuid4())
            ),
            site_repository=FakePolicySiteRepository(used_sites=0),
        )

        with pytest.raises(AppException) as exc_info:
            await plan_policy_service.get_user_usage(uuid4())

        assert exc_info.value.code == error_codes.SUBSCRIPTION_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_get_usage())


def test_plan_policy_allows_site_creation_when_usage_is_below_limit() -> None:
    async def run_policy_check() -> None:
        user_id = uuid4()
        plan_id = uuid4()
        plan_policy_service = PlanPolicyService(
            plan_repository=FakePolicyPlanRepository(plan=SimpleNamespace(max_sites=2)),
            subscription_repository=FakePolicySubscriptionRepository(
                subscription=SimpleNamespace(plan_id=plan_id)
            ),
            site_repository=FakePolicySiteRepository(used_sites=1),
        )

        await plan_policy_service.require_can_create_site(user_id)

        assert plan_policy_service.subscription_repository.user_id == user_id
        assert plan_policy_service.plan_repository.plan_id == plan_id

    asyncio.run(run_policy_check())


def test_plan_policy_rejects_site_creation_without_active_subscription() -> None:
    async def run_policy_check() -> None:
        plan_policy_service = PlanPolicyService(
            plan_repository=FakePolicyPlanRepository(plan=None),
            subscription_repository=FakePolicySubscriptionRepository(subscription=None),
            site_repository=FakePolicySiteRepository(used_sites=0),
        )

        with pytest.raises(AppException) as exc_info:
            await plan_policy_service.require_can_create_site(uuid4())

        assert exc_info.value.code == error_codes.SUBSCRIPTION_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_policy_check())


def test_plan_policy_rejects_site_creation_when_plan_is_missing() -> None:
    async def run_policy_check() -> None:
        plan_policy_service = PlanPolicyService(
            plan_repository=FakePolicyPlanRepository(plan=None),
            subscription_repository=FakePolicySubscriptionRepository(
                subscription=SimpleNamespace(plan_id=uuid4())
            ),
            site_repository=FakePolicySiteRepository(used_sites=0),
        )

        with pytest.raises(AppException) as exc_info:
            await plan_policy_service.require_can_create_site(uuid4())

        assert exc_info.value.code == error_codes.SUBSCRIPTION_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_policy_check())


def test_plan_policy_rejects_publish_when_limit_is_reached() -> None:
    async def run_policy_check() -> None:
        plan_policy_service = PlanPolicyService(
            plan_repository=FakePolicyPlanRepository(
                plan=SimpleNamespace(max_sites=1, can_publish=True)
            ),
            subscription_repository=FakePolicySubscriptionRepository(
                subscription=SimpleNamespace(plan_id=uuid4())
            ),
            site_repository=FakePolicySiteRepository(used_sites=1),
        )

        with pytest.raises(AppException) as exc_info:
            await plan_policy_service.require_can_publish_site(uuid4())

        assert exc_info.value.code == error_codes.SITE_LIMIT_EXCEEDED
        assert exc_info.value.status_code == 403

    asyncio.run(run_policy_check())


def test_plan_policy_returns_publish_policy() -> None:
    async def run_policy_check() -> None:
        user_id = uuid4()
        plan_id = uuid4()
        plan_policy_service = PlanPolicyService(
            plan_repository=FakePolicyPlanRepository(
                plan=SimpleNamespace(code="PRO", can_publish=True)
            ),
            subscription_repository=FakePolicySubscriptionRepository(
                subscription=SimpleNamespace(plan_id=plan_id)
            ),
            site_repository=FakePolicySiteRepository(used_sites=0),
        )

        response = await plan_policy_service.get_publish_policy(user_id)

        assert response.plan_code == "PRO"
        assert response.plan_can_publish is True
        assert plan_policy_service.subscription_repository.user_id == user_id
        assert plan_policy_service.plan_repository.plan_id == plan_id

    asyncio.run(run_policy_check())


def test_plan_policy_publish_policy_raises_subscription_not_found() -> None:
    async def run_policy_check() -> None:
        plan_policy_service = PlanPolicyService(
            plan_repository=FakePolicyPlanRepository(plan=None),
            subscription_repository=FakePolicySubscriptionRepository(subscription=None),
            site_repository=FakePolicySiteRepository(used_sites=0),
        )

        with pytest.raises(AppException) as exc_info:
            await plan_policy_service.get_publish_policy(uuid4())

        assert exc_info.value.code == error_codes.SUBSCRIPTION_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_policy_check())


def test_plan_policy_publish_policy_raises_when_plan_is_missing() -> None:
    async def run_policy_check() -> None:
        plan_policy_service = PlanPolicyService(
            plan_repository=FakePolicyPlanRepository(plan=None),
            subscription_repository=FakePolicySubscriptionRepository(
                subscription=SimpleNamespace(plan_id=uuid4())
            ),
            site_repository=FakePolicySiteRepository(used_sites=0),
        )

        with pytest.raises(AppException) as exc_info:
            await plan_policy_service.get_publish_policy(uuid4())

        assert exc_info.value.code == error_codes.SUBSCRIPTION_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_policy_check())


# ---------------------------------------------------------------------------
# Task 5: Redis 캐시 레이어 (list_plans)
# ---------------------------------------------------------------------------


def test_list_plans_cache_hit_skips_service_call() -> None:
    """redis_enabled=True + 캐시 히트 시 plan_service.list_active_plans()가
    호출되지 않고(=DB 조회 스킵) 캐시된 값을 그대로 반환해야 한다."""
    fake_plan_service = CountingFakePlanService()
    cached_body = PlanListResponse(
        items=[
            SimpleNamespace(
                code="CACHED",
                name="Cached Plan",
                price_monthly=1,
                currency="KRW",
                max_sites=1,
                can_publish=True,
            )
        ]
    ).model_dump_json()

    fake_redis_client = AsyncMock()
    fake_redis_client.get.return_value = cached_body

    app.dependency_overrides[get_plan_service] = lambda: fake_plan_service

    try:
        with (
            patch.object(plans_module.settings, "redis_enabled", True),
            patch.object(plans_module, "get_redis_client", return_value=fake_redis_client),
        ):
            client = TestClient(app)
            response = client.get("/api/v1/plans")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["code"] == "CACHED"
    assert fake_plan_service.call_count == 0
    fake_redis_client.get.assert_awaited_once_with(plans_module.PLANS_CACHE_KEY)
    fake_redis_client.setex.assert_not_called()


def test_list_plans_cache_miss_calls_service_and_populates_cache() -> None:
    """redis_enabled=True + 캐시 미스 시 plan_service가 호출되고, 그 결과가
    cache_set(setex)을 통해 캐시에 저장돼야 한다."""
    fake_plan_service = CountingFakePlanService()

    fake_redis_client = AsyncMock()
    fake_redis_client.get.return_value = None

    app.dependency_overrides[get_plan_service] = lambda: fake_plan_service

    try:
        with (
            patch.object(plans_module.settings, "redis_enabled", True),
            patch.object(plans_module, "get_redis_client", return_value=fake_redis_client),
        ):
            client = TestClient(app)
            response = client.get("/api/v1/plans")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["code"] == "FREE"
    assert fake_plan_service.call_count == 1
    fake_redis_client.setex.assert_awaited_once()
    setex_args = fake_redis_client.setex.await_args.args
    assert setex_args[0] == plans_module.PLANS_CACHE_KEY
    assert setex_args[1] == plans_module.PLANS_CACHE_TTL


def test_list_plans_does_not_touch_redis_when_disabled() -> None:
    """redis_enabled=False(기본값)이면 캐시 코드 경로가 완전히 스킵돼야 한다
    (Redis 미가용 환경에서도 기존 동작이 그대로 유지됨을 보장)."""
    fake_plan_service = CountingFakePlanService()
    fake_redis_client = AsyncMock()

    app.dependency_overrides[get_plan_service] = lambda: fake_plan_service

    try:
        with patch.object(plans_module, "get_redis_client", return_value=fake_redis_client):
            client = TestClient(app)
            response = client.get("/api/v1/plans")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_plan_service.call_count == 1
    fake_redis_client.get.assert_not_called()
    fake_redis_client.setex.assert_not_called()


# ---------------------------------------------------------------------------
# Task 8-B: Redis Graceful Degradation (list_plans)
# ---------------------------------------------------------------------------


def test_list_plans_falls_back_to_db_when_redis_get_raises() -> None:
    """Redis client.get()이 예외를 던져도(연결 장애 등) 500이 아니라
    DB 조회 결과로 정상 응답해야 한다 — Redis 장애가 요청 실패로 전파되면
    안 된다는 것이 이 태스크의 핵심 목표다."""
    fake_plan_service = CountingFakePlanService()

    fake_redis_client = AsyncMock()
    fake_redis_client.get.side_effect = Exception("Redis connection refused")

    app.dependency_overrides[get_plan_service] = lambda: fake_plan_service

    try:
        with (
            patch.object(plans_module.settings, "redis_enabled", True),
            patch.object(plans_module, "get_redis_client", return_value=fake_redis_client),
        ):
            client = TestClient(app)
            response = client.get("/api/v1/plans")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["code"] == "FREE"
    assert fake_plan_service.call_count == 1


def test_list_plans_returns_200_when_cache_write_fails_after_fallback() -> None:
    """캐시 미스로 DB 폴백까지 갔는데, 그 결과를 캐시에 쓰는 setex마저
    실패해도(예: Redis가 읽기는 되지만 쓰기 타임아웃 등) 응답은 여전히
    200이어야 한다 — 캐시 쓰기 실패가 요청 성공 여부에 영향을 주면 안 된다."""
    fake_plan_service = CountingFakePlanService()

    fake_redis_client = AsyncMock()
    fake_redis_client.get.return_value = None
    fake_redis_client.setex.side_effect = Exception("Redis write timeout")

    app.dependency_overrides[get_plan_service] = lambda: fake_plan_service

    try:
        with (
            patch.object(plans_module.settings, "redis_enabled", True),
            patch.object(plans_module, "get_redis_client", return_value=fake_redis_client),
        ):
            client = TestClient(app)
            response = client.get("/api/v1/plans")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["code"] == "FREE"
    assert fake_plan_service.call_count == 1
