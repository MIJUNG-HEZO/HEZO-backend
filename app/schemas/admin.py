from pydantic import BaseModel


class AdminPipelineItem(BaseModel):
    site_id: str
    publish_status: str
    attempt: int | None = None
    updated_at: str | None = None
    error_message: str | None = None


class AdminPipelineListResponse(BaseModel):
    items: list[AdminPipelineItem]
    total: int


class AdminUserItem(BaseModel):
    id: str
    email: str
    name: str
    role: str
    email_verified: bool
    created_at: str


class AdminUserListResponse(BaseModel):
    items: list[AdminUserItem]
    total: int


class AdminMetricsPlaceholder(BaseModel):
    message: str = "CloudWatch 메트릭은 P5 모니터링 스펙 확정 후 연동 예정"
    available: bool = False
