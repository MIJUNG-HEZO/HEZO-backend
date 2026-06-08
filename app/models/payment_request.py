from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import PaymentProvider, PaymentRequestStatus
from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.pg_enums import payment_provider_enum, payment_request_status_enum


class PaymentRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_requests"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("plans.id"),
        nullable=False,
    )
    provider: Mapped[PaymentProvider] = mapped_column(
        payment_provider_enum,
        nullable=False,
        default=PaymentProvider.TOSS_PAYMENTS,
        server_default=PaymentProvider.TOSS_PAYMENTS.value,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="KRW",
        server_default="KRW",
    )
    status: Mapped[PaymentRequestStatus] = mapped_column(
        payment_request_status_enum,
        nullable=False,
        default=PaymentRequestStatus.REQUESTED,
        server_default=PaymentRequestStatus.REQUESTED.value,
    )
    pg_request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    pg_response_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_payment_requests_user_id", "user_id"),
        Index("idx_payment_requests_plan_id", "plan_id"),
        Index("idx_payment_requests_status", "status"),
        Index("idx_payment_requests_provider", "provider"),
        Index("idx_payment_requests_created_at", "created_at"),
    )
