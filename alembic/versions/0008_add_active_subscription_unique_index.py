"""사용자당 활성 구독 1개 보장 부분 유니크 인덱스 추가

Revision ID: 0008_add_active_subscription_unique_index
Revises: 0007_create_social_accounts
Create Date: 2026-06-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_add_active_subscription_unique_index"
down_revision: str | None = "0007_create_social_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_subscriptions_active_user_id",
        "subscriptions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_subscriptions_active_user_id", table_name="subscriptions")
