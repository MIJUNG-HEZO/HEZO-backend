import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, get_billing_service, require_email_verified
from app.core import error_codes
from app.core.enums import PaymentProvider, PaymentRequestStatus, SubscriptionStatus
from app.core.exceptions import AppException
from app.main import app
from app.schemas.billing import (
    BillingCheckoutRequest,
    BillingCheckoutResponse,
    MockPaymentApprovalResponse,
)
from app.services.billing_service import BillingService


class FakeBillingService:
    def __init__(self) -> None:
        self.user_id: UUID | None = None
        self.payload: BillingCheckoutRequest | None = None
        self.payment_request_id = uuid4()

    async def create_checkout(
        self,
        *,
        user_id: UUID,
        payload: BillingCheckoutRequest,
    ) -> BillingCheckoutResponse:
        self.user_id = user_id
        self.payload = payload
        return BillingCheckoutResponse(
            payment_request_id=self.payment_request_id,
            provider=PaymentProvider.TOSS_PAYMENTS,
            plan_code=payload.plan_code.upper(),
            amount=29000,
            currency="KRW",
            status=PaymentRequestStatus.REQUESTED,
            payment_params={
                "amount": 29000,
                "orderId": str(self.payment_request_id),
                "orderName": "HEZO Pro Plan",
                "customerEmail": "user@example.com",
                "successUrl": "http://localhost:3000/billing/success",
                "failUrl": "http://localhost:3000/billing/fail",
            },
        )

    async def mock_approve(
        self,
        *,
        user_id: UUID,
        payment_request_id: UUID,
    ) -> MockPaymentApprovalResponse:
        self.user_id = user_id
        self.payment_request_id = payment_request_id
        return MockPaymentApprovalResponse(
            payment_request_id=payment_request_id,
            payment_status=PaymentRequestStatus.APPROVED,
            previous_plan_code="FREE",
            current_plan_code="PRO",
            subscription_status=SubscriptionStatus.ACTIVE,
        )


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeUserRepository:
    def __init__(self, user: SimpleNamespace | None) -> None:
        self.user = user
        self.user_id: UUID | None = None

    async def get_by_id(self, user_id: UUID) -> SimpleNamespace | None:
        self.user_id = user_id
        return self.user


class FakePlanRepository:
    def __init__(self, plan: SimpleNamespace | None) -> None:
        self.plan = plan
        self.code: str | None = None

    async def get_by_code(self, code: str) -> SimpleNamespace | None:
        self.code = code
        return self.plan


class FakeApprovalPlanRepository:
    def __init__(
        self,
        *,
        target_plan: SimpleNamespace | None,
        previous_plan: SimpleNamespace | None,
    ) -> None:
        self.target_plan = target_plan
        self.previous_plan = previous_plan

    async def get_by_id(self, plan_id: UUID) -> SimpleNamespace | None:
        if self.target_plan is not None and plan_id == self.target_plan.id:
            return self.target_plan
        if self.previous_plan is not None and plan_id == self.previous_plan.id:
            return self.previous_plan
        return None


class FakePaymentRequestRepository:
    def __init__(self, payment_request: SimpleNamespace | None = None) -> None:
        self.created_kwargs: dict[str, object] | None = None
        self.updated_kwargs: dict[str, object] | None = None
        self.marked_approved = False
        self.payment_request = payment_request or SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            plan_id=uuid4(),
            provider=PaymentProvider.TOSS_PAYMENTS,
            amount=29000,
            currency="KRW",
            status=PaymentRequestStatus.REQUESTED,
        )

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.created_kwargs = kwargs
        self.payment_request.provider = kwargs["provider"]
        self.payment_request.amount = kwargs["amount"]
        self.payment_request.currency = kwargs["currency"]
        self.payment_request.status = kwargs["status"]
        return self.payment_request

    async def update_pg_request_id(
        self,
        payment_request: SimpleNamespace,
        *,
        pg_request_id: str,
    ) -> SimpleNamespace:
        self.updated_kwargs = {
            "payment_request": payment_request,
            "pg_request_id": pg_request_id,
        }
        payment_request.pg_request_id = pg_request_id
        return payment_request

    async def get_by_id_for_update(
        self,
        payment_request_id: UUID,
    ) -> SimpleNamespace | None:
        if self.payment_request.id != payment_request_id:
            return None
        return self.payment_request

    async def mark_approved(self, payment_request: SimpleNamespace) -> SimpleNamespace:
        self.marked_approved = True
        payment_request.status = PaymentRequestStatus.APPROVED
        return payment_request


class FakeBillingEventRepository:
    def __init__(self) -> None:
        self.created_kwargs: dict[str, object] | None = None

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.created_kwargs = kwargs
        return SimpleNamespace(id=uuid4(), **kwargs)


class FailingBillingEventRepository:
    async def create(self, **kwargs: object) -> SimpleNamespace:
        raise RuntimeError("Unexpected billing event failure")


class FakeSubscriptionRepository:
    def __init__(self, subscription: SimpleNamespace | None) -> None:
        self.subscription = subscription
        self.changed_kwargs: dict[str, object] | None = None

    async def get_active_by_user_id_for_update(
        self,
        user_id: UUID,
    ) -> SimpleNamespace | None:
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
        return subscription


def make_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        email="user@example.com",
        deleted_at=None,
    )


def make_plan(
    *,
    code: str = "PRO",
    name: str = "Pro",
    price_monthly: int = 29000,
    is_active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        code=code,
        name=name,
        price_monthly=price_monthly,
        currency="KRW",
        is_active=is_active,
    )


def make_payment_request(
    *,
    user_id: UUID,
    plan_id: UUID,
    status: PaymentRequestStatus = PaymentRequestStatus.REQUESTED,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        plan_id=plan_id,
        provider=PaymentProvider.TOSS_PAYMENTS,
        amount=29000,
        currency="KRW",
        status=status,
    )


def test_create_checkout_requires_email_verified_user() -> None:
    client = TestClient(app)

    response = client.post("/api/v1/billing/checkout", json={"plan_code": "PRO"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == error_codes.UNAUTHORIZED


def test_create_checkout_returns_payment_window_params() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    fake_billing_service = FakeBillingService()

    app.dependency_overrides[require_email_verified] = lambda: current_user
    app.dependency_overrides[get_billing_service] = lambda: fake_billing_service

    try:
        client = TestClient(app)
        response = client.post("/api/v1/billing/checkout", json={"plan_code": "pro"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["provider"] == "toss_payments"
    assert body["plan_code"] == "PRO"
    assert body["amount"] == 29000
    assert body["currency"] == "KRW"
    assert body["status"] == "requested"
    assert body["payment_params"]["orderId"] == str(fake_billing_service.payment_request_id)
    assert body["payment_params"]["orderName"] == "HEZO Pro Plan"
    assert fake_billing_service.user_id == current_user.id
    assert fake_billing_service.payload == BillingCheckoutRequest(plan_code="pro")


def test_billing_service_creates_checkout_history_event_and_payment_params() -> None:
    async def run_create_checkout() -> None:
        session = FakeSession()
        user = make_user()
        plan = make_plan()
        payment_request_repository = FakePaymentRequestRepository()
        billing_event_repository = FakeBillingEventRepository()
        service = BillingService(
            session=session,
            user_repository=FakeUserRepository(user),
            plan_repository=FakePlanRepository(plan),
            payment_request_repository=payment_request_repository,
            billing_event_repository=billing_event_repository,
        )

        response = await service.create_checkout(
            user_id=user.id,
            payload=BillingCheckoutRequest(plan_code="pro"),
        )

        assert session.committed is True
        assert session.rolled_back is False
        assert payment_request_repository.created_kwargs == {
            "user_id": user.id,
            "plan_id": plan.id,
            "provider": PaymentProvider.TOSS_PAYMENTS,
            "amount": 29000,
            "currency": "KRW",
            "status": PaymentRequestStatus.REQUESTED,
        }
        assert payment_request_repository.updated_kwargs is not None
        assert payment_request_repository.updated_kwargs["pg_request_id"] == str(
            payment_request_repository.payment_request.id
        )
        assert billing_event_repository.created_kwargs is not None
        assert billing_event_repository.created_kwargs["event_type"] == "checkout_requested"
        assert billing_event_repository.created_kwargs["user_id"] == user.id
        assert (
            billing_event_repository.created_kwargs["payment_request_id"]
            == response.payment_request_id
        )
        assert response.payment_request_id == payment_request_repository.payment_request.id
        assert response.payment_params == {
            "amount": 29000,
            "orderId": str(payment_request_repository.payment_request.id),
            "orderName": "HEZO Pro Plan",
            "customerEmail": "user@example.com",
            "successUrl": "http://localhost:3000/billing/success",
            "failUrl": "http://localhost:3000/billing/fail",
        }

    asyncio.run(run_create_checkout())


def test_billing_service_rejects_missing_plan() -> None:
    async def run_create_checkout() -> None:
        service = BillingService(
            session=FakeSession(),
            user_repository=FakeUserRepository(make_user()),
            plan_repository=FakePlanRepository(None),
        )

        with pytest.raises(AppException) as exc_info:
            await service.create_checkout(
                user_id=uuid4(),
                payload=BillingCheckoutRequest(plan_code="UNKNOWN"),
            )

        assert exc_info.value.code == error_codes.PLAN_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_create_checkout())


def test_billing_service_rejects_inactive_plan() -> None:
    async def run_create_checkout() -> None:
        service = BillingService(
            session=FakeSession(),
            user_repository=FakeUserRepository(make_user()),
            plan_repository=FakePlanRepository(make_plan(is_active=False)),
        )

        with pytest.raises(AppException) as exc_info:
            await service.create_checkout(
                user_id=uuid4(),
                payload=BillingCheckoutRequest(plan_code="PRO"),
            )

        assert exc_info.value.code == error_codes.PLAN_NOT_ACTIVE
        assert exc_info.value.status_code == 400

    asyncio.run(run_create_checkout())


def test_billing_service_rejects_free_plan_checkout() -> None:
    async def run_create_checkout() -> None:
        service = BillingService(
            session=FakeSession(),
            user_repository=FakeUserRepository(make_user()),
            plan_repository=FakePlanRepository(
                make_plan(code="FREE", name="Free", price_monthly=0)
            ),
        )

        with pytest.raises(AppException) as exc_info:
            await service.create_checkout(
                user_id=uuid4(),
                payload=BillingCheckoutRequest(plan_code="FREE"),
            )

        assert exc_info.value.code == error_codes.FREE_PLAN_CANNOT_CHECKOUT
        assert exc_info.value.status_code == 400

    asyncio.run(run_create_checkout())


def test_billing_service_rejects_missing_plan_name_before_creating_history() -> None:
    async def run_create_checkout() -> None:
        session = FakeSession()
        payment_request_repository = FakePaymentRequestRepository()
        service = BillingService(
            session=session,
            user_repository=FakeUserRepository(make_user()),
            plan_repository=FakePlanRepository(make_plan(name="")),
            payment_request_repository=payment_request_repository,
        )

        with pytest.raises(AppException) as exc_info:
            await service.create_checkout(
                user_id=uuid4(),
                payload=BillingCheckoutRequest(plan_code="PRO"),
            )

        assert session.committed is False
        assert session.rolled_back is False
        assert payment_request_repository.created_kwargs is None
        assert exc_info.value.code == error_codes.PAYMENT_REQUEST_FAILED
        assert exc_info.value.status_code == 502

    asyncio.run(run_create_checkout())


def test_mock_approve_requires_email_verified_user() -> None:
    client = TestClient(app)

    response = client.post(f"/api/v1/billing/payments/{uuid4()}/mock-approve")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == error_codes.UNAUTHORIZED


def test_mock_approve_returns_upgraded_subscription() -> None:
    current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))
    fake_billing_service = FakeBillingService()
    payment_request_id = uuid4()

    app.dependency_overrides[require_email_verified] = lambda: current_user
    app.dependency_overrides[get_billing_service] = lambda: fake_billing_service

    try:
        client = TestClient(app)
        response = client.post(
            f"/api/v1/billing/payments/{payment_request_id}/mock-approve"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "payment_request_id": str(payment_request_id),
        "payment_status": "approved",
        "previous_plan_code": "FREE",
        "current_plan_code": "PRO",
        "subscription_status": "active",
    }
    assert fake_billing_service.user_id == current_user.id
    assert fake_billing_service.payment_request_id == payment_request_id


def test_billing_service_mock_approve_upgrades_subscription() -> None:
    async def run_mock_approve() -> None:
        session = FakeSession()
        user_id = uuid4()
        previous_plan = make_plan(code="FREE", name="Free", price_monthly=0)
        target_plan = make_plan(code="PRO", name="Pro", price_monthly=29000)
        payment_request = make_payment_request(
            user_id=user_id,
            plan_id=target_plan.id,
        )
        subscription = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            plan_id=previous_plan.id,
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime.now(UTC),
        )
        payment_repository = FakePaymentRequestRepository(payment_request)
        subscription_repository = FakeSubscriptionRepository(subscription)
        billing_event_repository = FakeBillingEventRepository()
        service = BillingService(
            session=session,
            plan_repository=FakeApprovalPlanRepository(
                target_plan=target_plan,
                previous_plan=previous_plan,
            ),
            payment_request_repository=payment_repository,
            subscription_repository=subscription_repository,
            billing_event_repository=billing_event_repository,
            mock_payment_approval_enabled=True,
        )

        response = await service.mock_approve(
            user_id=user_id,
            payment_request_id=payment_request.id,
        )

        assert session.committed is True
        assert session.rolled_back is False
        assert payment_repository.marked_approved is True
        assert payment_request.status == PaymentRequestStatus.APPROVED
        assert subscription.plan_id == target_plan.id
        assert subscription.status == SubscriptionStatus.ACTIVE
        assert billing_event_repository.created_kwargs == {
            "user_id": user_id,
            "payment_request_id": payment_request.id,
            "event_type": "mock_payment_approved",
            "payload_json": {
                "mock": True,
                "previous_plan_code": "FREE",
                "new_plan_code": "PRO",
                "amount": 29000,
                "currency": "KRW",
            },
        }
        assert response.payment_status == PaymentRequestStatus.APPROVED
        assert response.previous_plan_code == "FREE"
        assert response.current_plan_code == "PRO"
        assert response.subscription_status == SubscriptionStatus.ACTIVE

    asyncio.run(run_mock_approve())


def test_billing_service_mock_approve_requires_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run_mock_approve() -> None:
        monkeypatch.setattr(
            "app.services.billing_service.settings.mock_payment_approval_enabled",
            False,
        )
        service = BillingService(session=FakeSession())

        with pytest.raises(AppException) as exc_info:
            await service.mock_approve(
                user_id=uuid4(),
                payment_request_id=uuid4(),
            )

        assert exc_info.value.code == error_codes.FORBIDDEN
        assert exc_info.value.status_code == 403

    asyncio.run(run_mock_approve())


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (PaymentRequestStatus.APPROVED, error_codes.PAYMENT_ALREADY_APPROVED),
        (PaymentRequestStatus.FAILED, error_codes.PAYMENT_STATUS_NOT_APPROVABLE),
        (PaymentRequestStatus.CANCELED, error_codes.PAYMENT_STATUS_NOT_APPROVABLE),
    ],
)
def test_billing_service_mock_approve_rejects_invalid_status(
    status: PaymentRequestStatus,
    expected_code: str,
) -> None:
    async def run_mock_approve() -> None:
        session = FakeSession()
        user_id = uuid4()
        target_plan = make_plan()
        payment_request = make_payment_request(
            user_id=user_id,
            plan_id=target_plan.id,
            status=status,
        )
        service = BillingService(
            session=session,
            payment_request_repository=FakePaymentRequestRepository(payment_request),
            mock_payment_approval_enabled=True,
        )

        with pytest.raises(AppException) as exc_info:
            await service.mock_approve(
                user_id=user_id,
                payment_request_id=payment_request.id,
            )

        assert session.rolled_back is True
        assert exc_info.value.code == expected_code
        assert exc_info.value.status_code == 409

    asyncio.run(run_mock_approve())


def test_billing_service_mock_approve_rejects_other_users_payment() -> None:
    async def run_mock_approve() -> None:
        session = FakeSession()
        target_plan = make_plan()
        payment_request = make_payment_request(
            user_id=uuid4(),
            plan_id=target_plan.id,
        )
        service = BillingService(
            session=session,
            payment_request_repository=FakePaymentRequestRepository(payment_request),
            mock_payment_approval_enabled=True,
        )

        with pytest.raises(AppException) as exc_info:
            await service.mock_approve(
                user_id=uuid4(),
                payment_request_id=payment_request.id,
            )

        assert session.rolled_back is True
        assert exc_info.value.code == error_codes.FORBIDDEN
        assert exc_info.value.status_code == 403

    asyncio.run(run_mock_approve())


def test_billing_service_mock_approve_requires_active_subscription() -> None:
    async def run_mock_approve() -> None:
        session = FakeSession()
        user_id = uuid4()
        target_plan = make_plan()
        payment_request = make_payment_request(
            user_id=user_id,
            plan_id=target_plan.id,
        )
        service = BillingService(
            session=session,
            plan_repository=FakeApprovalPlanRepository(
                target_plan=target_plan,
                previous_plan=None,
            ),
            payment_request_repository=FakePaymentRequestRepository(payment_request),
            subscription_repository=FakeSubscriptionRepository(None),
            mock_payment_approval_enabled=True,
        )

        with pytest.raises(AppException) as exc_info:
            await service.mock_approve(
                user_id=user_id,
                payment_request_id=payment_request.id,
            )

        assert session.rolled_back is True
        assert exc_info.value.code == error_codes.SUBSCRIPTION_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_mock_approve())


def test_billing_service_mock_approve_rejects_missing_payment_request() -> None:
    async def run_mock_approve() -> None:
        session = FakeSession()
        repository = FakePaymentRequestRepository()
        service = BillingService(
            session=session,
            payment_request_repository=repository,
            mock_payment_approval_enabled=True,
        )

        with pytest.raises(AppException) as exc_info:
            await service.mock_approve(
                user_id=uuid4(),
                payment_request_id=uuid4(),
            )

        assert session.rolled_back is True
        assert exc_info.value.code == error_codes.PAYMENT_REQUEST_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_mock_approve())


@pytest.mark.parametrize(
    ("target_plan", "expected_code", "expected_status"),
    [
        (None, error_codes.PLAN_NOT_FOUND, 404),
        (make_plan(is_active=False), error_codes.PLAN_NOT_ACTIVE, 400),
        (
            make_plan(code="FREE", name="Free", price_monthly=0),
            error_codes.FREE_PLAN_CANNOT_CHECKOUT,
            400,
        ),
    ],
)
def test_billing_service_mock_approve_rejects_invalid_target_plan(
    target_plan: SimpleNamespace | None,
    expected_code: str,
    expected_status: int,
) -> None:
    async def run_mock_approve() -> None:
        session = FakeSession()
        user_id = uuid4()
        target_plan_id = target_plan.id if target_plan is not None else uuid4()
        payment_request = make_payment_request(
            user_id=user_id,
            plan_id=target_plan_id,
        )
        service = BillingService(
            session=session,
            plan_repository=FakeApprovalPlanRepository(
                target_plan=target_plan,
                previous_plan=None,
            ),
            payment_request_repository=FakePaymentRequestRepository(payment_request),
            mock_payment_approval_enabled=True,
        )

        with pytest.raises(AppException) as exc_info:
            await service.mock_approve(
                user_id=user_id,
                payment_request_id=payment_request.id,
            )

        assert session.rolled_back is True
        assert exc_info.value.code == expected_code
        assert exc_info.value.status_code == expected_status

    asyncio.run(run_mock_approve())


def test_billing_service_mock_approve_succeeds_with_pending_status() -> None:
    async def run_mock_approve() -> None:
        session = FakeSession()
        user_id = uuid4()
        previous_plan = make_plan(code="FREE", name="Free", price_monthly=0)
        target_plan = make_plan(code="MAX", name="Max", price_monthly=99000)
        payment_request = make_payment_request(
            user_id=user_id,
            plan_id=target_plan.id,
            status=PaymentRequestStatus.PENDING,
        )
        subscription = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            plan_id=previous_plan.id,
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime.now(UTC),
        )
        service = BillingService(
            session=session,
            plan_repository=FakeApprovalPlanRepository(
                target_plan=target_plan,
                previous_plan=previous_plan,
            ),
            payment_request_repository=FakePaymentRequestRepository(payment_request),
            subscription_repository=FakeSubscriptionRepository(subscription),
            billing_event_repository=FakeBillingEventRepository(),
            mock_payment_approval_enabled=True,
        )

        response = await service.mock_approve(
            user_id=user_id,
            payment_request_id=payment_request.id,
        )

        assert session.committed is True
        assert payment_request.status == PaymentRequestStatus.APPROVED
        assert response.current_plan_code == "MAX"

    asyncio.run(run_mock_approve())


def test_billing_service_mock_approve_rejects_missing_previous_plan() -> None:
    async def run_mock_approve() -> None:
        session = FakeSession()
        user_id = uuid4()
        target_plan = make_plan()
        payment_request = make_payment_request(
            user_id=user_id,
            plan_id=target_plan.id,
        )
        subscription = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            plan_id=uuid4(),
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime.now(UTC),
        )
        service = BillingService(
            session=session,
            plan_repository=FakeApprovalPlanRepository(
                target_plan=target_plan,
                previous_plan=None,
            ),
            payment_request_repository=FakePaymentRequestRepository(payment_request),
            subscription_repository=FakeSubscriptionRepository(subscription),
            mock_payment_approval_enabled=True,
        )

        with pytest.raises(AppException) as exc_info:
            await service.mock_approve(
                user_id=user_id,
                payment_request_id=payment_request.id,
            )

        assert session.rolled_back is True
        assert exc_info.value.code == error_codes.PLAN_NOT_FOUND
        assert exc_info.value.status_code == 404

    asyncio.run(run_mock_approve())


def test_billing_service_mock_approve_rolls_back_unexpected_exception() -> None:
    async def run_mock_approve() -> None:
        session = FakeSession()
        user_id = uuid4()
        previous_plan = make_plan(code="FREE", name="Free", price_monthly=0)
        target_plan = make_plan()
        payment_request = make_payment_request(
            user_id=user_id,
            plan_id=target_plan.id,
        )
        subscription = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            plan_id=previous_plan.id,
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime.now(UTC),
        )
        service = BillingService(
            session=session,
            plan_repository=FakeApprovalPlanRepository(
                target_plan=target_plan,
                previous_plan=previous_plan,
            ),
            payment_request_repository=FakePaymentRequestRepository(payment_request),
            subscription_repository=FakeSubscriptionRepository(subscription),
            billing_event_repository=FailingBillingEventRepository(),
            mock_payment_approval_enabled=True,
        )

        with pytest.raises(RuntimeError, match="Unexpected billing event failure"):
            await service.mock_approve(
                user_id=user_id,
                payment_request_id=payment_request.id,
            )

        assert session.committed is False
        assert session.rolled_back is True

    asyncio.run(run_mock_approve())
