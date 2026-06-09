import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    CurrentUser,
    get_subscription_service,
    require_authenticated,
)
from app.core import error_codes
from app.core.enums import SubscriptionStatus
from app.core.exceptions import AppException
from app.main import app
from app.repositories.subscription_repository import SubscriptionRepository
from app.schemas.subscription import MySubscriptionResponse, SubscriptionResponse
from app.services.subscription_service import SubscriptionService


class FakeSubscriptionService:
    def __init__(self) -> None:
        self.requested_user_id: UUID | None = None

    async def get_my_subscription(self, *, user_id: UUID) -> MySubscriptionResponse:
        self.requested_user_id = user_id
        return MySubscriptionResponse(
            subscription=SubscriptionResponse(
                id=uuid4(),
                status=SubscriptionStatus.ACTIVE,
                started_at=datetime(2026, 6, 7, tzinfo=UTC),
                ended_at=None,
                renewed_at=None,
                plan=SimpleNamespace(
                    code="FREE",
                    name="Free",
                    price_monthly=0,
                    currency="KRW",
                    max_sites=1,
                    can_publish=False,
                ),
            )
        )


class FakeSubscriptionRepository:
    def __init__(self, subscription: SimpleNamespace | None) -> None:
        self.subscription = subscription
        self.user_id: UUID | None = None
        self.changed_kwargs: dict[str, object] | None = None

    async def get_active_by_user_id(self, user_id: UUID) -> SimpleNamespace | None:
        self.user_id = user_id
        return self.subscription

    async def get_active_by_user_id_for_update(self, user_id: UUID) -> SimpleNamespace | None:
        self.user_id = user_id
        return self.subscription

    async def change_plan(
        self,
        subscription: SimpleNamespace,
        *,
        plan_id: UUID,
        started_at: datetime,
    ) -> SimpleNamespace:
        self.changed_kwargs = {
            "subscription": subscription,
            "plan_id": plan_id,
            "started_at": started_at,
        }
        subscription.plan_id = plan_id
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.started_at = started_at
        subscription.ended_at = None
        subscription.renewed_at = None
        return subscription


class FakePlanRepository:
    def __init__(
        self,
        plan: SimpleNamespace | None = None,
        *,
        plans_by_id: dict[UUID, SimpleNamespace] | None = None,
        plans_by_code: dict[str, SimpleNamespace] | None = None,
    ) -> None:
        self.plan = plan
        self.plans_by_id = plans_by_id or {}
        self.plans_by_code = plans_by_code or {}
        self.plan_id: UUID | None = None
        self.code: str | None = None

    async def get_by_id(self, plan_id: UUID) -> SimpleNamespace | None:
        self.plan_id = plan_id
        if self.plans_by_id:
            return self.plans_by_id.get(plan_id)
        return self.plan

    async def get_by_code(self, code: str) -> SimpleNamespace | None:
        self.code = code
        return self.plans_by_code.get(code)


class FakeServiceSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeWriteSession:
    def __init__(self) -> None:
        self.flushed = False

    async def flush(self) -> None:
        self.flushed = True


def make_plan(
    *,
    code: str,
    price_monthly: int,
    is_active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        code=code,
        name=code.title(),
        price_monthly=price_monthly,
        currency="KRW",
        max_sites=1 if code != "MAX" else 4,
        can_publish=code != "FREE",
        is_active=is_active,
    )


def test_get_my_subscription_requires_authentication() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/subscriptions/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == error_codes.UNAUTHORIZED


def test_get_my_subscription_returns_current_user_subscription() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=None)
    fake_subscription_service = FakeSubscriptionService()

    app.dependency_overrides[require_authenticated] = lambda: current_user
    app.dependency_overrides[get_subscription_service] = lambda: fake_subscription_service

    try:
        client = TestClient(app)
        response = client.get("/api/v1/subscriptions/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["subscription"]["status"] == "active"
    assert body["subscription"]["plan"]["code"] == "FREE"
    assert body["subscription"]["plan"]["can_publish"] is False
    assert fake_subscription_service.requested_user_id == current_user.id


def test_subscription_service_returns_my_subscription_response() -> None:
    async def run_get_my_subscription() -> None:
        user_id = uuid4()
        plan_id = uuid4()
        subscription = SimpleNamespace(
            id=uuid4(),
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime(2026, 6, 7, tzinfo=UTC),
            ended_at=None,
            renewed_at=None,
        )
        plan = SimpleNamespace(
            code="PRO",
            name="Pro",
            price_monthly=29000,
            currency="KRW",
            max_sites=1,
            can_publish=True,
        )
        subscription_service = SubscriptionService(session=None)
        subscription_service.subscription_repository = FakeSubscriptionRepository(subscription)
        subscription_service.plan_repository = FakePlanRepository(plan)

        response = await subscription_service.get_my_subscription(user_id=user_id)

        assert response.subscription.id == subscription.id
        assert response.subscription.status == SubscriptionStatus.ACTIVE
        assert response.subscription.plan.code == "PRO"
        assert response.subscription.plan.can_publish is True
        assert subscription_service.subscription_repository.user_id == user_id
        assert subscription_service.plan_repository.plan_id == plan_id

    asyncio.run(run_get_my_subscription())


def test_subscription_service_raises_subscription_not_found() -> None:
    async def run_get_my_subscription() -> None:
        subscription_service = SubscriptionService(session=None)
        subscription_service.subscription_repository = FakeSubscriptionRepository(None)
        subscription_service.plan_repository = FakePlanRepository(None)

        with pytest.raises(AppException) as exc_info:
            await subscription_service.get_my_subscription(user_id=uuid4())

        assert exc_info.value.code == error_codes.SUBSCRIPTION_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_get_my_subscription())


def test_subscription_service_raises_when_plan_is_missing() -> None:
    async def run_get_my_subscription() -> None:
        subscription = SimpleNamespace(
            id=uuid4(),
            plan_id=uuid4(),
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime(2026, 6, 7, tzinfo=UTC),
            ended_at=None,
            renewed_at=None,
        )
        subscription_service = SubscriptionService(session=None)
        subscription_service.subscription_repository = FakeSubscriptionRepository(subscription)
        subscription_service.plan_repository = FakePlanRepository(None)

        with pytest.raises(AppException) as exc_info:
            await subscription_service.get_my_subscription(user_id=uuid4())

        assert exc_info.value.code == error_codes.SUBSCRIPTION_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_get_my_subscription())


def test_subscription_repository_changes_active_plan() -> None:
    async def run_change_plan() -> None:
        session = FakeWriteSession()
        repository = SubscriptionRepository(session=session)
        started_at = datetime.now(UTC)
        new_plan_id = uuid4()
        subscription = SimpleNamespace(
            plan_id=uuid4(),
            status=SubscriptionStatus.PAST_DUE,
            started_at=datetime(2026, 6, 7, tzinfo=UTC),
            ended_at=datetime.now(UTC),
            renewed_at=datetime.now(UTC),
        )

        result = await repository.change_plan(
            subscription,
            plan_id=new_plan_id,
            started_at=started_at,
        )

        assert result is subscription
        assert subscription.plan_id == new_plan_id
        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.started_at == started_at
        assert subscription.ended_at is None
        assert subscription.renewed_at is None
        assert session.flushed is True

    asyncio.run(run_change_plan())


def test_subscription_service_upgrades_active_subscription_plan() -> None:
    async def run_upgrade_plan() -> None:
        session = FakeServiceSession()
        user_id = uuid4()
        free_plan = make_plan(code="FREE", price_monthly=0)
        pro_plan = make_plan(code="PRO", price_monthly=29000)
        subscription = SimpleNamespace(
            id=uuid4(),
            plan_id=free_plan.id,
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime(2026, 6, 7, tzinfo=UTC),
            ended_at=None,
            renewed_at=None,
        )
        subscription_repository = FakeSubscriptionRepository(subscription)
        plan_repository = FakePlanRepository(
            plans_by_id={free_plan.id: free_plan, pro_plan.id: pro_plan},
            plans_by_code={pro_plan.code: pro_plan},
        )
        subscription_service = SubscriptionService(session=session)
        subscription_service.subscription_repository = subscription_repository
        subscription_service.plan_repository = plan_repository

        response = await subscription_service.upgrade_plan(
            user_id=user_id,
            target_plan_code="pro",
        )

        assert session.committed is True
        assert session.rolled_back is False
        assert subscription_repository.user_id == user_id
        assert subscription_repository.changed_kwargs is not None
        assert subscription_repository.changed_kwargs["plan_id"] == pro_plan.id
        assert subscription.plan_id == pro_plan.id
        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.ended_at is None
        assert subscription.renewed_at is None
        assert response.subscription.id == subscription.id
        assert response.subscription.plan.code == "PRO"

    asyncio.run(run_upgrade_plan())


def test_subscription_service_rejects_upgrade_without_active_subscription() -> None:
    async def run_upgrade_plan() -> None:
        subscription_service = SubscriptionService(session=FakeServiceSession())
        subscription_service.subscription_repository = FakeSubscriptionRepository(None)

        with pytest.raises(AppException) as exc_info:
            await subscription_service.upgrade_plan(
                user_id=uuid4(),
                target_plan_code="PRO",
            )

        assert exc_info.value.code == error_codes.SUBSCRIPTION_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_upgrade_plan())


def test_subscription_service_rejects_upgrade_when_target_plan_is_missing() -> None:
    async def run_upgrade_plan() -> None:
        free_plan = make_plan(code="FREE", price_monthly=0)
        subscription = SimpleNamespace(
            id=uuid4(),
            plan_id=free_plan.id,
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime(2026, 6, 7, tzinfo=UTC),
            ended_at=None,
            renewed_at=None,
        )
        subscription_service = SubscriptionService(session=FakeServiceSession())
        subscription_service.subscription_repository = FakeSubscriptionRepository(subscription)
        subscription_service.plan_repository = FakePlanRepository(
            plans_by_id={free_plan.id: free_plan},
            plans_by_code={},
        )

        with pytest.raises(AppException) as exc_info:
            await subscription_service.upgrade_plan(
                user_id=uuid4(),
                target_plan_code="UNKNOWN",
            )

        assert exc_info.value.code == error_codes.PLAN_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_upgrade_plan())


def test_subscription_service_rejects_inactive_target_plan() -> None:
    async def run_upgrade_plan() -> None:
        free_plan = make_plan(code="FREE", price_monthly=0)
        pro_plan = make_plan(code="PRO", price_monthly=29000, is_active=False)
        subscription = SimpleNamespace(
            id=uuid4(),
            plan_id=free_plan.id,
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime(2026, 6, 7, tzinfo=UTC),
            ended_at=None,
            renewed_at=None,
        )
        subscription_service = SubscriptionService(session=FakeServiceSession())
        subscription_service.subscription_repository = FakeSubscriptionRepository(subscription)
        subscription_service.plan_repository = FakePlanRepository(
            plans_by_id={free_plan.id: free_plan, pro_plan.id: pro_plan},
            plans_by_code={pro_plan.code: pro_plan},
        )

        with pytest.raises(AppException) as exc_info:
            await subscription_service.upgrade_plan(
                user_id=uuid4(),
                target_plan_code="PRO",
            )

        assert exc_info.value.code == error_codes.PLAN_NOT_ACTIVE
        assert exc_info.value.status_code == 400

    asyncio.run(run_upgrade_plan())


@pytest.mark.parametrize(
    ("current_plan", "target_plan"),
    [
        (make_plan(code="PRO", price_monthly=29000), make_plan(code="PRO", price_monthly=29000)),
        (make_plan(code="MAX", price_monthly=49000), make_plan(code="PRO", price_monthly=29000)),
        (make_plan(code="PRO", price_monthly=29000), make_plan(code="FREE", price_monthly=0)),
    ],
)
def test_subscription_service_rejects_non_upgrade_plan_change(
    current_plan: SimpleNamespace,
    target_plan: SimpleNamespace,
) -> None:
    async def run_upgrade_plan() -> None:
        subscription = SimpleNamespace(
            id=uuid4(),
            plan_id=current_plan.id,
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime(2026, 6, 7, tzinfo=UTC),
            ended_at=None,
            renewed_at=None,
        )
        subscription_service = SubscriptionService(session=FakeServiceSession())
        subscription_service.subscription_repository = FakeSubscriptionRepository(subscription)
        subscription_service.plan_repository = FakePlanRepository(
            plans_by_id={current_plan.id: current_plan, target_plan.id: target_plan},
            plans_by_code={target_plan.code: target_plan},
        )

        with pytest.raises(AppException) as exc_info:
            await subscription_service.upgrade_plan(
                user_id=uuid4(),
                target_plan_code=target_plan.code,
            )

        assert exc_info.value.code == error_codes.PLAN_UPGRADE_NOT_ALLOWED
        assert exc_info.value.status_code == 400

    asyncio.run(run_upgrade_plan())
