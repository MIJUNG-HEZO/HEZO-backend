import base64
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import httpx

from app.core.config import settings


class PaymentRequestLike(Protocol):
    id: UUID


class PlanLike(Protocol):
    code: str
    name: str
    price_monthly: int


class UserLike(Protocol):
    email: str | None


@dataclass(frozen=True)
class TossPaymentRequestParams:
    amount: int
    order_id: str
    order_name: str
    customer_email: str | None
    success_url: str
    fail_url: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "amount": self.amount,
            "orderId": self.order_id,
            "orderName": self.order_name,
            "customerEmail": self.customer_email,
            "successUrl": self.success_url,
            "failUrl": self.fail_url,
        }


class TossPaymentsClient:
    def __init__(
        self,
        *,
        success_url: str | None = None,
        fail_url: str | None = None,
    ) -> None:
        self.success_url = success_url or settings.toss_payments_success_url
        self.fail_url = fail_url or settings.toss_payments_fail_url

    def create_payment_request_params(
        self,
        *,
        payment_request: PaymentRequestLike,
        plan: PlanLike,
        user: UserLike,
    ) -> TossPaymentRequestParams:
        order_id = str(payment_request.id)
        # Toss Payments orderId constraint: letters, numbers, "-", "_", 6-64 chars.
        return TossPaymentRequestParams(
            amount=plan.price_monthly,
            order_id=order_id,
            order_name=self._build_order_name(plan),
            customer_email=user.email,
            success_url=self.success_url,
            fail_url=self.fail_url,
        )

    def _build_order_name(self, plan: PlanLike) -> str:
        plan_name = plan.name
        if not plan_name:
            raise ValueError("Plan name is required to build Toss Payments orderName.")
        return f"HEZO {plan_name} Plan"

    def _auth_header(self) -> str:
        token = base64.b64encode(f"{settings.toss_payments_secret_key}:".encode()).decode()
        return f"Basic {token}"

    async def confirm_payment(
        self,
        *,
        payment_key: str,
        order_id: str,
        amount: int,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.tosspayments.com/v1/payments/confirm",
                headers={
                    "Authorization": self._auth_header(),
                    "Content-Type": "application/json",
                },
                json={"paymentKey": payment_key, "orderId": order_id, "amount": amount},
            )
        response.raise_for_status()
        return response.json()
