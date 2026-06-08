from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing_event import BillingEvent


class BillingEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        event_type: str,
        user_id: UUID | None = None,
        payment_request_id: UUID | None = None,
        payload_json: dict[str, Any] | None = None,
    ) -> BillingEvent:
        billing_event = BillingEvent(
            user_id=user_id,
            payment_request_id=payment_request_id,
            event_type=event_type,
            payload_json=payload_json,
        )
        self.session.add(billing_event)
        await self.session.flush()
        return billing_event
