"""User 모델에 role 컬럼 추가 (user / admin)

Revision ID: 0009_add_user_role
Revises: 0008_add_sub_unique_index
Create Date: 2026-06-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_add_user_role"
down_revision: str | None = "0008_add_sub_unique_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
    )


def downgrade() -> None:
    op.drop_column("users", "role")
