from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PaymentProvider, PaymentRequestStatus
from app.models.payment_request import PaymentRequest


class PaymentRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        amount: int,
        currency: str = "KRW",
        provider: PaymentProvider = PaymentProvider.TOSS_PAYMENTS,
        status: PaymentRequestStatus = PaymentRequestStatus.REQUESTED,
        pg_request_id: str | None = None,
        pg_response_json: dict[str, Any] | None = None,
    ) -> PaymentRequest:
        payment_request = PaymentRequest(
            user_id=user_id,
            plan_id=plan_id,
            provider=provider,
            amount=amount,
            currency=currency,
            status=status,
            pg_request_id=pg_request_id,
            pg_response_json=pg_response_json,
        )
        self.session.add(payment_request)
        await self.session.flush()
        return payment_request

    async def update_pg_request_id(
        self,
        payment_request: PaymentRequest,
        *,
        pg_request_id: str,
    ) -> PaymentRequest:
        payment_request.pg_request_id = pg_request_id
        await self.session.flush()
        return payment_request

    async def get_by_order_id_for_update(self, order_id: str) -> PaymentRequest | None:
        stmt = (
            select(PaymentRequest)
            .where(PaymentRequest.pg_request_id == order_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def confirm(
        self,
        payment_request: PaymentRequest,
        *,
        pg_response_json: dict[str, Any],
    ) -> PaymentRequest:
        payment_request.status = PaymentRequestStatus.APPROVED
        payment_request.pg_response_json = pg_response_json
        await self.session.flush()
        return payment_request
