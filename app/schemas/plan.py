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


class PlanUsagePlan(BaseModel):
    code: str
    name: str


class PlanUsageDetail(BaseModel):
    max_sites: int
    used_sites: int
    remaining_sites: int
    can_create_site: bool
    can_publish: bool


class PlanUsageResponse(BaseModel):
    plan: PlanUsagePlan
    usage: PlanUsageDetail
