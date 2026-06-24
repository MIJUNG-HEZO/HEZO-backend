from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import (
    CurrentUser,
    get_subscription_service,
    require_email_verified,
)
from app.schemas.subscription import (
    MySubscriptionResponse,
    SubscriptionUpgradeRequest,
)
from app.services.subscription_service import SubscriptionService

router = APIRouter(
    prefix="/dev/subscriptions",
    tags=["Development"],
)


@router.post("/upgrade", response_model=MySubscriptionResponse)
async def upgrade_subscription_for_development(
    payload: SubscriptionUpgradeRequest,
    current_user: Annotated[CurrentUser, Depends(require_email_verified)],
    subscription_service: Annotated[SubscriptionService, Depends(get_subscription_service)],
) -> MySubscriptionResponse:
    return await subscription_service.upgrade_plan(
        user_id=current_user.id,
        target_plan_code=payload.plan_code,
    )
