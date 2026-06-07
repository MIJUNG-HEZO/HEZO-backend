from sqlalchemy.dialects.postgresql import ENUM

from app.core.enums import ModuleKey, SiteStatus, SiteType, SubscriptionStatus

subscription_status_enum = ENUM(
    SubscriptionStatus,
    name="subscription_status",
    create_type=False,
)
site_status_enum = ENUM(
    SiteStatus,
    name="site_status",
    create_type=False,
)
site_type_enum = ENUM(
    SiteType,
    name="site_type",
    create_type=False,
)
module_key_enum = ENUM(
    ModuleKey,
    name="module_key",
    create_type=False,
)
