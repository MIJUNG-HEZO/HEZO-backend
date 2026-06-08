from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, get_billing_service, require_email_verified
from app.schemas.billing import (
    BillingCheckoutRequest,
    BillingCheckoutResponse,
    MockPaymentApprovalResponse,
)
from app.services.billing_service import BillingService

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.post(
    "/checkout",
    response_model=BillingCheckoutResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_checkout(
    payload: BillingCheckoutRequest,
    current_user: Annotated[CurrentUser, Depends(require_email_verified)],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
) -> BillingCheckoutResponse:
    return await billing_service.create_checkout(user_id=current_user.id, payload=payload)


@router.post(
    "/payments/{payment_request_id}/mock-approve",
    response_model=MockPaymentApprovalResponse,
)
async def mock_approve_payment(
    payment_request_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_email_verified)],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
) -> MockPaymentApprovalResponse:
    return await billing_service.mock_approve(
        user_id=current_user.id,
        payment_request_id=payment_request_id,
    )
