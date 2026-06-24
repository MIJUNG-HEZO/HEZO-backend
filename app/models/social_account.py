from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SocialAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "social_accounts"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_social_accounts_provider_user_id",
        ),
        Index("idx_social_accounts_user_id", "user_id"),
        Index("idx_social_accounts_provider_user_id", "provider", "provider_user_id"),
    )
