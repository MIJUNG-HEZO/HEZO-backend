from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ModuleKey, SiteStatus, SiteType

VALID_SITE_MODULE_PAIRS = {
    ModuleKey.MEDICAL: SiteType.LANDING,
    ModuleKey.PERSONAL_BLOG: SiteType.BLOG,
    ModuleKey.RESTAURANT: SiteType.STORE,
}


class SiteCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    site_type: SiteType
    module_key: ModuleKey


class SiteUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    site_type: SiteType
    module_key: ModuleKey


class SiteResponse(BaseModel):
    id: UUID
    name: str
    site_type: SiteType
    module_key: ModuleKey
    status: SiteStatus
    is_published: bool
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SiteListResponse(BaseModel):
    items: list[SiteResponse]
    total: int


class SitePublishAvailabilityResponse(BaseModel):
    can_publish: bool
    reason: str | None
    site_status: SiteStatus
    is_published: bool
    plan_code: str
    plan_can_publish: bool
