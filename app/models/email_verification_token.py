from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class EmailVerificationToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_verification_tokens"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_email_verification_tokens_user_id", "user_id"),
        Index("idx_email_verification_tokens_expires_at", "expires_at"),
        Index("idx_email_verification_tokens_used_at", "used_at"),
        Index("idx_email_verification_tokens_revoked_at", "revoked_at"),
    )
