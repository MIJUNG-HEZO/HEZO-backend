"""소셜 계정 연결 테이블 생성

Revision ID: 0007_create_social_accounts
Revises: 0006_create_billing_events
Create Date: 2026-06-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_create_social_accounts"
down_revision: str | None = "0006_create_billing_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "social_accounts",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_user_id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_social_accounts_provider_user_id",
        ),
    )
    op.create_index("idx_social_accounts_user_id", "social_accounts", ["user_id"])
    op.create_index(
        "idx_social_accounts_provider_user_id",
        "social_accounts",
        ["provider", "provider_user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_social_accounts_provider_user_id", table_name="social_accounts")
    op.drop_index("idx_social_accounts_user_id", table_name="social_accounts")
    op.drop_table("social_accounts")
