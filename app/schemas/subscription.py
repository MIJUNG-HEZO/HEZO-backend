from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class SubscriptionUpgradeRequest(BaseModel):
    plan_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("plan_code")
    @classmethod
    def normalize_plan_code(cls, value: str) -> str:
        return value.upper()
