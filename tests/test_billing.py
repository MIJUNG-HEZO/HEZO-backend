import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, get_billing_service, require_email_verified
from app.core import error_codes
from app.core.enums import PaymentProvider, PaymentRequestStatus
from app.core.exceptions import AppException
from app.main import app
from app.schemas.billing import BillingCheckoutRequest, BillingCheckoutResponse
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


class FakePaymentRequestRepository:
    def __init__(self) -> None:
        self.created_kwargs: dict[str, object] | None = None
        self.updated_kwargs: dict[str, object] | None = None
        self.payment_request = SimpleNamespace(
            id=uuid4(),
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

    async def update_pg_request_payload(
        self,
        payment_request: SimpleNamespace,
        *,
        pg_request_id: str,
        pg_response_json: dict[str, object],
    ) -> SimpleNamespace:
        self.updated_kwargs = {
            "payment_request": payment_request,
            "pg_request_id": pg_request_id,
            "pg_response_json": pg_response_json,
        }
        payment_request.pg_request_id = pg_request_id
        payment_request.pg_response_json = pg_response_json
        return payment_request


class FakeBillingEventRepository:
    def __init__(self) -> None:
        self.created_kwargs: dict[str, object] | None = None

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.created_kwargs = kwargs
        return SimpleNamespace(id=uuid4(), **kwargs)


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


def test_billing_service_rolls_back_when_payment_params_fail() -> None:
    async def run_create_checkout() -> None:
        session = FakeSession()
        service = BillingService(
            session=session,
            user_repository=FakeUserRepository(make_user()),
            plan_repository=FakePlanRepository(make_plan(name="")),
            payment_request_repository=FakePaymentRequestRepository(),
        )

        with pytest.raises(AppException) as exc_info:
            await service.create_checkout(
                user_id=uuid4(),
                payload=BillingCheckoutRequest(plan_code="PRO"),
            )

        assert session.committed is False
        assert session.rolled_back is True
        assert exc_info.value.code == error_codes.PAYMENT_REQUEST_FAILED
        assert exc_info.value.status_code == 502

    asyncio.run(run_create_checkout())
