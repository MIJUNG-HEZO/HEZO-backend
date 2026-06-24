from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import PaymentProvider, PaymentRequestStatus


class BillingCheckoutRequest(BaseModel):
    plan_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")


class BillingCheckoutResponse(BaseModel):
    payment_request_id: UUID
    provider: PaymentProvider
    plan_code: str
    amount: int
    currency: str
    status: PaymentRequestStatus
    payment_params: dict[str, Any]


class BillingConfirmRequest(BaseModel):
    payment_key: str = Field(alias="paymentKey", min_length=1)
    order_id: str = Field(alias="orderId", min_length=1)
    amount: int = Field(gt=0)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BillingConfirmResponse(BaseModel):
    payment_request_id: UUID
    plan_code: str
    amount: int
    status: PaymentRequestStatus
