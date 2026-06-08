"""이메일 인증 토큰 테이블 생성

Revision ID: 0004_email_verification_tokens
Revises: 0003_create_refresh_tokens
Create Date: 2026-06-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_email_verification_tokens"
down_revision: str | None = "0003_create_refresh_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_verification_tokens",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "idx_email_verification_tokens_expires_at",
        "email_verification_tokens",
        ["expires_at"],
    )
    op.create_index(
        "idx_email_verification_tokens_revoked_at",
        "email_verification_tokens",
        ["revoked_at"],
    )
    op.create_index(
        "idx_email_verification_tokens_used_at",
        "email_verification_tokens",
        ["used_at"],
    )
    op.create_index(
        "idx_email_verification_tokens_user_id",
        "email_verification_tokens",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_index("idx_email_verification_tokens_used_at", table_name="email_verification_tokens")
    op.drop_index(
        "idx_email_verification_tokens_revoked_at",
        table_name="email_verification_tokens",
    )
    op.drop_index(
        "idx_email_verification_tokens_expires_at",
        table_name="email_verification_tokens",
    )
    op.drop_table("email_verification_tokens")
