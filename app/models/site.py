from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ModuleKey, SiteStatus, SiteType
from app.db.base import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.pg_enums import module_key_enum, site_status_enum, site_type_enum


class Site(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "sites"

    owner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    site_type: Mapped[SiteType] = mapped_column(site_type_enum, nullable=False)
    module_key: Mapped[ModuleKey] = mapped_column(module_key_enum, nullable=False)
    status: Mapped[SiteStatus] = mapped_column(
        site_status_enum,
        nullable=False,
        default=SiteStatus.DRAFT,
        server_default=SiteStatus.DRAFT.value,
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_sites_owner_id", "owner_id"),
        Index("idx_sites_status", "status"),
        Index("idx_sites_site_type", "site_type"),
        Index("idx_sites_module_key", "module_key"),
        Index("idx_sites_deleted_at", "deleted_at"),
    )
