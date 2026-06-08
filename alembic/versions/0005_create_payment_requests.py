"""create payment requests

Revision ID: 0005_create_payment_requests
Revises: 0004_email_verification_tokens
Create Date: 2026-06-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_create_payment_requests"
down_revision: str | None = "0004_email_verification_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

payment_provider_enum = postgresql.ENUM(
    "toss_payments",
    name="payment_provider",
    create_type=False,
)
payment_request_status_enum = postgresql.ENUM(
    "requested",
    "pending",
    "approved",
    "failed",
    "canceled",
    name="payment_request_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    payment_provider_enum.create(bind, checkfirst=True)
    payment_request_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "payment_requests",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "provider",
            payment_provider_enum,
            server_default="toss_payments",
            nullable=False,
        ),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(), server_default="KRW", nullable=False),
        sa.Column(
            "status",
            payment_request_status_enum,
            server_default="requested",
            nullable=False,
        ),
        sa.Column("pg_request_id", sa.String(), nullable=True),
        sa.Column("pg_response_json", postgresql.JSONB(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        "idx_payment_requests_user_id",
        "payment_requests",
        ["user_id"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_payment_requests_plan_id",
        "payment_requests",
        ["plan_id"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_payment_requests_status",
        "payment_requests",
        ["status"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_payment_requests_provider",
        "payment_requests",
        ["provider"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_payment_requests_created_at",
        "payment_requests",
        ["created_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_payment_requests_created_at",
        table_name="payment_requests",
        if_exists=True,
    )
    op.drop_index(
        "idx_payment_requests_provider",
        table_name="payment_requests",
        if_exists=True,
    )
    op.drop_index(
        "idx_payment_requests_status",
        table_name="payment_requests",
        if_exists=True,
    )
    op.drop_index(
        "idx_payment_requests_plan_id",
        table_name="payment_requests",
        if_exists=True,
    )
    op.drop_index(
        "idx_payment_requests_user_id",
        table_name="payment_requests",
        if_exists=True,
    )
    op.drop_table("payment_requests", if_exists=True)
    payment_request_status_enum.drop(op.get_bind(), checkfirst=True)
    payment_provider_enum.drop(op.get_bind(), checkfirst=True)
