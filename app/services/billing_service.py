from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.enums import PaymentProvider, PaymentRequestStatus
from app.core.exceptions import AppException
from app.integrations.payments.toss_payments_client import TossPaymentsClient
from app.repositories.billing_event_repository import BillingEventRepository
from app.repositories.payment_request_repository import PaymentRequestRepository
from app.repositories.plan_repository import PlanRepository
from app.repositories.user_repository import UserRepository
from app.schemas.billing import BillingCheckoutRequest, BillingCheckoutResponse


class BillingService:
    def __init__(
        self,
        session: AsyncSession,
        plan_repository: PlanRepository | None = None,
        user_repository: UserRepository | None = None,
        payment_request_repository: PaymentRequestRepository | None = None,
        billing_event_repository: BillingEventRepository | None = None,
        toss_payments_client: TossPaymentsClient | None = None,
    ) -> None:
        self.session = session
        self.plan_repository = plan_repository or PlanRepository(session)
        self.user_repository = user_repository or UserRepository(session)
        self.payment_request_repository = payment_request_repository or PaymentRequestRepository(
            session
        )
        self.billing_event_repository = billing_event_repository or BillingEventRepository(session)
        self.toss_payments_client = toss_payments_client or TossPaymentsClient()

    async def create_checkout(
        self,
        *,
        user_id: UUID,
        payload: BillingCheckoutRequest,
    ) -> BillingCheckoutResponse:
        user = await self.user_repository.get_by_id(user_id)
        if user is None or user.deleted_at is not None:
            raise AppException(
                code=error_codes.UNAUTHORIZED,
                message="Authentication is required.",
                status_code=401,
            )

        plan_code = payload.plan_code.upper()
        plan = await self.plan_repository.get_by_code(plan_code)
        if plan is None:
            raise AppException(
                code=error_codes.PLAN_NOT_FOUND,
                message="Plan not found.",
                status_code=404,
                details={"plan_code": plan_code},
            )
        if not plan.is_active:
            raise AppException(
                code=error_codes.PLAN_NOT_ACTIVE,
                message="Plan is not active.",
                status_code=400,
                details={"plan_code": plan_code},
            )
        if plan.code == "FREE" or plan.price_monthly <= 0:
            raise AppException(
                code=error_codes.FREE_PLAN_CANNOT_CHECKOUT,
                message="Free plan cannot create a payment checkout.",
                status_code=400,
                details={"plan_code": plan_code},
            )
        if not plan.name:
            raise AppException(
                code=error_codes.PAYMENT_REQUEST_FAILED,
                message="Failed to create payment request.",
                status_code=502,
            )

        try:
            payment_request = await self.payment_request_repository.create(
                user_id=user.id,
                plan_id=plan.id,
                provider=PaymentProvider.TOSS_PAYMENTS,
                amount=plan.price_monthly,
                currency=plan.currency,
                status=PaymentRequestStatus.REQUESTED,
            )
            payment_params = self.toss_payments_client.create_payment_request_params(
                payment_request=payment_request,
                plan=plan,
                user=user,
            ).to_payload()
            await self.payment_request_repository.update_pg_request_id(
                payment_request,
                pg_request_id=payment_params["orderId"],
            )
            await self.billing_event_repository.create(
                user_id=user.id,
                payment_request_id=payment_request.id,
                event_type="checkout_requested",
                payload_json={
                    "plan_code": plan.code,
                    "amount": plan.price_monthly,
                    "currency": plan.currency,
                    "provider": PaymentProvider.TOSS_PAYMENTS.value,
                    "payment_params": payment_params,
                },
            )
            await self.session.commit()
        except SQLAlchemyError:
            await self.session.rollback()
            raise

        return BillingCheckoutResponse(
            payment_request_id=payment_request.id,
            provider=payment_request.provider,
            plan_code=plan.code,
            amount=payment_request.amount,
            currency=payment_request.currency,
            status=payment_request.status,
            payment_params=payment_params,
        )
