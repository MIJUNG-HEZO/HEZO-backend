from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, get_subscription_service, require_authenticated
from app.schemas.subscription import MySubscriptionResponse
from app.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.get("/me", response_model=MySubscriptionResponse)
async def get_my_subscription(
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    subscription_service: Annotated[SubscriptionService, Depends(get_subscription_service)],
) -> MySubscriptionResponse:
    return await subscription_service.get_my_subscription(user_id=current_user.id)
