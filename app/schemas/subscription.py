from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.enums import SubscriptionStatus
from app.schemas.plan import PlanResponse


class SubscriptionResponse(BaseModel):
    id: UUID
    status: SubscriptionStatus
    started_at: datetime
    ended_at: datetime | None
    renewed_at: datetime | None
    plan: PlanResponse

    model_config = ConfigDict(from_attributes=True)


class MySubscriptionResponse(BaseModel):
    subscription: SubscriptionResponse
