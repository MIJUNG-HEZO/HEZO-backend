from pydantic import BaseModel, ConfigDict


class PlanResponse(BaseModel):
    code: str
    name: str
    price_monthly: int
    currency: str
    max_sites: int
    can_publish: bool

    model_config = ConfigDict(from_attributes=True)


class PlanListResponse(BaseModel):
    items: list[PlanResponse]
