import base64
from datetime import UTC, datetime
from uuid import UUID

import httpx
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
from app.schemas.billing import BillingCheckoutRequest, BillingCheckoutResponse, BillingConfirmResponse

TOSS_CONFIRM_URL = "https://api.tosspayments.com/v1/payments/confirm"


class BillingService:
    def __init__(
        self,
        session: AsyncSession,
        plan_repository: PlanRepository | None = None,
        user_repository: UserRepository | None = None,
        payment_request_repository: PaymentRequestRepository | None = None,
        billing_event_repository: BillingEventRepository | None = None,
        toss_payments_client: TossPaymentsClient | None = None,
        subscription_repository: SubscriptionRepository | None = None,
    ) -> None:
        self.session = session
        self.plan_repository = plan_repository or PlanRepository(session)
        self.user_repository = user_repository or UserRepository(session)
        self.payment_request_repository = payment_request_repository or PaymentRequestRepository(
            session
        )
        self.billing_event_repository = billing_event_repository or BillingEventRepository(session)
        self.toss_payments_client = toss_payments_client or TossPaymentsClient()
        self.subscription_repository = subscription_repository or SubscriptionRepository(session)

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
        except Exception:
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

    async def confirm_payment(
        self,
        *,
        user_id: UUID,
        payment_key: str,
        order_id: str,
        amount: int,
    ) -> BillingConfirmResponse:
        payment_request = await self.payment_request_repository.get_by_order_id_for_update(order_id)
        if payment_request is None:
            raise AppException(
                code=error_codes.PAYMENT_REQUEST_NOT_FOUND,
                message="Payment request not found.",
                status_code=404,
            )
        if payment_request.user_id != user_id:
            raise AppException(
                code=error_codes.FORBIDDEN,
                message="Not authorized to confirm this payment.",
                status_code=403,
            )
        if payment_request.status == PaymentRequestStatus.APPROVED:
            raise AppException(
                code=error_codes.PAYMENT_ALREADY_CONFIRMED,
                message="Payment has already been confirmed.",
                status_code=409,
            )
        if payment_request.amount != amount:
            raise AppException(
                code=error_codes.PAYMENT_AMOUNT_MISMATCH,
                message="Payment amount does not match.",
                status_code=400,
            )

        plan = await self.plan_repository.get_by_id(payment_request.plan_id)
        if plan is None:
            raise AppException(
                code=error_codes.PLAN_NOT_FOUND,
                message="Plan not found.",
                status_code=404,
            )

        # Toss 호출 전 subscription 존재 확인 — Toss 승인 후 DB 실패 시 환불 로직 없으므로
        # 선제적으로 차단하여 "결제 완료 + 구독 미업그레이드" 상태를 방지
        subscription = await self.subscription_repository.get_active_by_user_id_for_update(user_id)
        if subscription is None:
            raise AppException(
                code=error_codes.SUBSCRIPTION_NOT_FOUND,
                message="Active subscription not found.",
                status_code=404,
            )

        # Toss 결제 승인 API 호출
        secret_key = settings.toss_payments_secret_key
        auth_header = base64.b64encode(f"{secret_key}:".encode()).decode()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    TOSS_CONFIRM_URL,
                    headers={
                        "Authorization": f"Basic {auth_header}",
                        "Content-Type": "application/json",
                    },
                    json={"paymentKey": payment_key, "orderId": order_id, "amount": amount},
                )
            toss_response = resp.json()
            if resp.status_code != 200:
                raise AppException(
                    code=error_codes.PAYMENT_CONFIRM_FAILED,
                    message=toss_response.get("message", "Payment confirmation failed."),
                    status_code=502,
                )
        except httpx.RequestError as exc:
            raise AppException(
                code=error_codes.PAYMENT_CONFIRM_FAILED,
                message="Failed to connect to payment gateway.",
                status_code=502,
            ) from exc

        try:
            await self.payment_request_repository.confirm(
                payment_request,
                pg_response_json=toss_response,
            )

            await self.subscription_repository.change_plan(
                subscription,
                plan_id=plan.id,
                started_at=datetime.now(UTC),
            )

            await self.billing_event_repository.create(
                user_id=user_id,
                payment_request_id=payment_request.id,
                event_type="payment_confirmed",
                payload_json={
                    "plan_code": plan.code,
                    "amount": amount,
                    "payment_key": payment_key,
                    "order_id": order_id,
                },
            )
            await self.session.commit()
        except AppException:
            await self.session.rollback()
            raise
        except Exception:
            await self.session.rollback()
            raise

        return BillingConfirmResponse(
            payment_request_id=payment_request.id,
            plan_code=plan.code,
            amount=payment_request.amount,
            status=PaymentRequestStatus.APPROVED,
        )
