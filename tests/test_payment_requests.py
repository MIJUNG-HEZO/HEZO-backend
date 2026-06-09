import asyncio
from uuid import uuid4

from app.core.enums import PaymentProvider, PaymentRequestStatus
from app.models.payment_request import PaymentRequest
from app.repositories.payment_request_repository import PaymentRequestRepository


class FakeSession:
    def __init__(self) -> None:
        self.added_object: object | None = None
        self.flushed = False

    def add(self, obj: object) -> None:
        self.added_object = obj

    async def flush(self) -> None:
        self.flushed = True


def test_payment_request_repository_creates_requested_payment_history() -> None:
    async def run_create() -> None:
        session = FakeSession()
        repository = PaymentRequestRepository(session=session)
        user_id = uuid4()
        plan_id = uuid4()

        payment_request = await repository.create(
            user_id=user_id,
            plan_id=plan_id,
            amount=29000,
            pg_request_id="order-id",
            pg_response_json={"orderName": "HEZO Pro"},
        )

        assert session.added_object is payment_request
        assert session.flushed is True
        assert payment_request.user_id == user_id
        assert payment_request.plan_id == plan_id
        assert payment_request.provider == PaymentProvider.TOSS_PAYMENTS
        assert payment_request.amount == 29000
        assert payment_request.currency == "KRW"
        assert payment_request.status == PaymentRequestStatus.REQUESTED
        assert payment_request.pg_request_id == "order-id"
        assert payment_request.pg_response_json == {"orderName": "HEZO Pro"}

    asyncio.run(run_create())


def test_payment_request_repository_allows_explicit_provider_and_status() -> None:
    async def run_create() -> None:
        session = FakeSession()
        repository = PaymentRequestRepository(session=session)

        payment_request = await repository.create(
            user_id=uuid4(),
            plan_id=uuid4(),
            amount=99000,
            currency="KRW",
            provider=PaymentProvider.TOSS_PAYMENTS,
            status=PaymentRequestStatus.PENDING,
        )

        assert isinstance(payment_request, PaymentRequest)
        assert payment_request.provider == PaymentProvider.TOSS_PAYMENTS
        assert payment_request.status == PaymentRequestStatus.PENDING
        assert payment_request.amount == 99000

    asyncio.run(run_create())
