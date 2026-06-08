from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import PaymentProvider, PaymentRequestStatus


class BillingCheckoutRequest(BaseModel):
    plan_code: str = Field(min_length=1, max_length=50)


class BillingCheckoutResponse(BaseModel):
    payment_request_id: UUID
    provider: PaymentProvider
    plan_code: str
    amount: int
    currency: str
    status: PaymentRequestStatus
    payment_params: dict[str, Any]
