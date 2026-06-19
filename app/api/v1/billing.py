from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, get_billing_service, require_email_verified
from app.schemas.billing import BillingCheckoutRequest, BillingCheckoutResponse, BillingConfirmRequest, BillingConfirmResponse
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
    "/confirm",
    response_model=BillingConfirmResponse,
    status_code=status.HTTP_200_OK,
)
async def confirm_checkout(
    payload: BillingConfirmRequest,
    current_user: Annotated[CurrentUser, Depends(require_email_verified)],
    billing_service: Annotated[BillingService, Depends(get_billing_service)],
) -> BillingConfirmResponse:
    return await billing_service.confirm_checkout(user_id=current_user.id, payload=payload)
