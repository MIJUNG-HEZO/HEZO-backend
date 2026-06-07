"""기본 플랜 데이터 추가

Revision ID: 0002_seed_plans
Revises: 0001_initial_schema
Create Date: 2026-06-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_seed_plans"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

plans_table = sa.table(
    "plans",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("price_monthly", sa.Integer()),
    sa.column("currency", sa.String()),
    sa.column("max_sites", sa.Integer()),
    sa.column("can_publish", sa.Boolean()),
    sa.column("is_active", sa.Boolean()),
)


def upgrade() -> None:
    op.bulk_insert(
        plans_table,
        [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "code": "FREE",
                "name": "Free",
                "price_monthly": 0,
                "currency": "KRW",
                "max_sites": 1,
                "can_publish": False,
                "is_active": True,
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "code": "PRO",
                "name": "Pro",
                "price_monthly": 29000,
                "currency": "KRW",
                "max_sites": 1,
                "can_publish": True,
                "is_active": True,
            },
            {
                "id": "33333333-3333-3333-3333-333333333333",
                "code": "MAX",
                "name": "Max",
                "price_monthly": 99000,
                "currency": "KRW",
                "max_sites": 4,
                "can_publish": True,
                "is_active": True,
            },
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM plans WHERE code IN ('FREE', 'PRO', 'MAX')")
