"""Seed default plans

Revision ID: 0002_seed_plans
Revises: 0001_initial_schema
Create Date: 2026-06-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_seed_plans"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO plans (
          id, code, name, price_monthly, currency, max_sites, can_publish, is_active
        )
        VALUES
          (
            '11111111-1111-1111-1111-111111111111',
            'FREE',
            'Free',
            0,
            'KRW',
            1,
            false,
            true
          ),
          (
            '22222222-2222-2222-2222-222222222222',
            'PRO',
            'Pro',
            29000,
            'KRW',
            1,
            true,
            true
          ),
          (
            '33333333-3333-3333-3333-333333333333',
            'MAX',
            'Max',
            99000,
            'KRW',
            4,
            true,
            true
          )
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM plans
        WHERE id IN (
          '11111111-1111-1111-1111-111111111111',
          '22222222-2222-2222-2222-222222222222',
          '33333333-3333-3333-3333-333333333333'
        )
        """
    )
