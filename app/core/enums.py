from enum import StrEnum


class SiteStatus(StrEnum):
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
