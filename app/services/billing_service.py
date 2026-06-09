from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.config import settings
from app.core.constants import FREE_PLAN_CODE
from app.core.enums import PaymentProvider, PaymentRequestStatus
from app.core.exceptions import AppException
from app.integrations.payments.toss_payments_client import TossPaymentsClient
from app.repositories.billing_event_repository import BillingEventRepository
from app.repositories.payment_request_repository import PaymentRequestRepository
from app.repositories.plan_repository import PlanRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.billing import (
    BillingCheckoutRequest,
    BillingCheckoutResponse,
    MockPaymentApprovalResponse,
)


class BillingService:
    def __init__(
        self,
        session: AsyncSession,
        plan_repository: PlanRepository | None = None,
        user_repository: UserRepository | None = None,
        payment_request_repository: PaymentRequestRepository | None = None,
        billing_event_repository: BillingEventRepository | None = None,
        subscription_repository: SubscriptionRepository | None = None,
        toss_payments_client: TossPaymentsClient | None = None,
        mock_payment_approval_enabled: bool | None = None,
    ) -> None:
        self.session = session
        self.plan_repository = plan_repository or PlanRepository(session)
        self.user_repository = user_repository or UserRepository(session)
        self.payment_request_repository = payment_request_repository or PaymentRequestRepository(
            session
        )
        self.billing_event_repository = billing_event_repository or BillingEventRepository(session)
        self.subscription_repository = subscription_repository or SubscriptionRepository(session)
        self.toss_payments_client = toss_payments_client or TossPaymentsClient()
        self.mock_payment_approval_enabled = (
            settings.mock_payment_approval_enabled
            if mock_payment_approval_enabled is None
            else mock_payment_approval_enabled
        )

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
        if plan.code == FREE_PLAN_CODE or plan.price_monthly <= 0:
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

    async def mock_approve(
        self,
        *,
        user_id: UUID,
        payment_request_id: UUID,
    ) -> MockPaymentApprovalResponse:
        if not self.mock_payment_approval_enabled:
            raise AppException(
                code=error_codes.FORBIDDEN,
                message="Mock payment approval is disabled.",
                status_code=403,
            )

        try:
            payment_request = await self.payment_request_repository.get_by_id_for_update(
                payment_request_id
            )
            if payment_request is None:
                raise AppException(
                    code=error_codes.PAYMENT_REQUEST_NOT_FOUND,
                    message="Payment request not found.",
                    status_code=404,
                )
            if payment_request.user_id != user_id:
                raise AppException(
                    code=error_codes.FORBIDDEN,
                    message="Payment request does not belong to the current user.",
                    status_code=403,
                )
            if payment_request.status == PaymentRequestStatus.APPROVED:
                raise AppException(
                    code=error_codes.PAYMENT_ALREADY_APPROVED,
                    message="Payment request is already approved.",
                    status_code=409,
                )
            if payment_request.status not in {
                PaymentRequestStatus.REQUESTED,
                PaymentRequestStatus.PENDING,
            }:
                raise AppException(
                    code=error_codes.PAYMENT_STATUS_NOT_APPROVABLE,
                    message="Payment request status cannot be approved.",
                    status_code=409,
                    details={"status": payment_request.status.value},
                )

            plan = await self.plan_repository.get_by_id(payment_request.plan_id)
            if plan is None:
                raise AppException(
                    code=error_codes.PLAN_NOT_FOUND,
                    message="Plan not found.",
                    status_code=404,
                )
            if not plan.is_active:
                raise AppException(
                    code=error_codes.PLAN_NOT_ACTIVE,
                    message="Plan is not active.",
                    status_code=400,
                    details={"plan_code": plan.code},
                )
            if plan.code == FREE_PLAN_CODE or plan.price_monthly <= 0:
                raise AppException(
                    code=error_codes.FREE_PLAN_CANNOT_CHECKOUT,
                    message="Free plan cannot be approved as a payment.",
                    status_code=400,
                    details={"plan_code": plan.code},
                )

            subscription = await self.subscription_repository.get_active_by_user_id_for_update(
                user_id
            )
            if subscription is None:
                raise AppException(
                    code=error_codes.SUBSCRIPTION_NOT_FOUND,
                    message="Active subscription was not found.",
                    status_code=404,
                )

            previous_plan = await self.plan_repository.get_by_id(subscription.plan_id)
            if previous_plan is None:
                raise AppException(
                    code=error_codes.PLAN_NOT_FOUND,
                    message="Subscription's current plan was not found.",
                    status_code=404,
                )

            approved_at = datetime.now(UTC)
            await self.payment_request_repository.mark_approved(payment_request)
            await self.subscription_repository.change_plan(
                subscription,
                plan_id=plan.id,
                started_at=approved_at,
            )
            await self.billing_event_repository.create(
                user_id=user_id,
                payment_request_id=payment_request.id,
                event_type="mock_payment_approved",
                payload_json={
                    "mock": True,
                    "previous_plan_code": previous_plan.code,
                    "new_plan_code": plan.code,
                    "amount": payment_request.amount,
                    "currency": payment_request.currency,
                },
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        return MockPaymentApprovalResponse(
            payment_request_id=payment_request.id,
            payment_status=payment_request.status,
            previous_plan_code=previous_plan.code,
            current_plan_code=plan.code,
            subscription_status=subscription.status,
        )
