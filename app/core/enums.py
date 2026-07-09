from enum import StrEnum


class SiteStatus(StrEnum):
    # DynamoDB 큐 추적 레코드 + API 응답(SiteCreateAcceptedResponse)에서만 쓰인다.
    # Postgres site_status enum 타입은 create_type=False라 이 값을 모른다 —
    # Site.status 컬럼에 절대 저장하지 말 것(먼저 ALTER TYPE 마이그레이션 필요).
    QUEUED = "queued"
    DRAFT = "draft"
    ARCHIVED = "archived"
    DELETED = "deleted"


class SiteType(StrEnum):
    LANDING = "landing"
    BLOG = "blog"
    STORE = "store"


class ModuleKey(StrEnum):
    MEDICAL = "medical"
    PERSONAL_BLOG = "personal_blog"
    RESTAURANT = "restaurant"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"


class PaymentProvider(StrEnum):
    TOSS_PAYMENTS = "toss_payments"


class PaymentRequestStatus(StrEnum):
    REQUESTED = "requested"
    PENDING = "pending"
    APPROVED = "approved"
    FAILED = "failed"
    CANCELED = "canceled"
