import asyncio
from uuid import uuid4

from app.models.billing_event import BillingEvent
from app.repositories.billing_event_repository import BillingEventRepository


class FakeSession:
    def __init__(self) -> None:
        self.added_object: object | None = None
        self.flushed = False

    def add(self, obj: object) -> None:
        self.added_object = obj

    async def flush(self) -> None:
        self.flushed = True


def test_billing_event_repository_creates_event_log() -> None:
    async def run_create() -> None:
        session = FakeSession()
        repository = BillingEventRepository(session=session)
        user_id = uuid4()
        payment_request_id = uuid4()

        billing_event = await repository.create(
            user_id=user_id,
            payment_request_id=payment_request_id,
            event_type="payment_request_created",
            payload_json={"amount": 29000, "currency": "KRW"},
        )

        assert session.added_object is billing_event
        assert session.flushed is True
        assert isinstance(billing_event, BillingEvent)
        assert billing_event.user_id == user_id
        assert billing_event.payment_request_id == payment_request_id
        assert billing_event.event_type == "payment_request_created"
        assert billing_event.payload_json == {"amount": 29000, "currency": "KRW"}

    asyncio.run(run_create())


def test_billing_event_repository_allows_nullable_relations() -> None:
    async def run_create() -> None:
        session = FakeSession()
        repository = BillingEventRepository(session=session)

        billing_event = await repository.create(
            event_type="billing_system_event",
            payload_json={"message": "created without related user or payment request"},
        )

        assert session.added_object is billing_event
        assert session.flushed is True
        assert billing_event.user_id is None
        assert billing_event.payment_request_id is None
        assert billing_event.event_type == "billing_system_event"

    asyncio.run(run_create())
