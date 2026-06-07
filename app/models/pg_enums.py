from sqlalchemy.dialects.postgresql import ENUM

from app.core.enums import ModuleKey, SiteStatus, SiteType, SubscriptionStatus


def enum_values(enum_cls: type) -> list[str]:
    return [item.value for item in enum_cls]

subscription_status_enum = ENUM(
    SubscriptionStatus,
    name="subscription_status",
    values_callable=enum_values,
    create_type=False,
)
site_status_enum = ENUM(
    SiteStatus,
    name="site_status",
    values_callable=enum_values,
    create_type=False,
)
site_type_enum = ENUM(
    SiteType,
    name="site_type",
    values_callable=enum_values,
    create_type=False,
)
module_key_enum = ENUM(
    ModuleKey,
    name="module_key",
    values_callable=enum_values,
    create_type=False,
)
