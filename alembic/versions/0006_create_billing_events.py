"""create billing events

Revision ID: 0006_create_billing_events
Revises: 0005_create_payment_requests
Create Date: 2026-06-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_create_billing_events"
down_revision: str | None = "0005_create_payment_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_events",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payment_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["payment_request_id"], ["payment_requests.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        "idx_billing_events_user_id",
        "billing_events",
        ["user_id"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_billing_events_payment_request_id",
        "billing_events",
        ["payment_request_id"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_billing_events_event_type",
        "billing_events",
        ["event_type"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_billing_events_created_at",
        "billing_events",
        ["created_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_billing_events_created_at",
        table_name="billing_events",
        if_exists=True,
    )
    op.drop_index(
        "idx_billing_events_event_type",
        table_name="billing_events",
        if_exists=True,
    )
    op.drop_index(
        "idx_billing_events_payment_request_id",
        table_name="billing_events",
        if_exists=True,
    )
    op.drop_index(
        "idx_billing_events_user_id",
        table_name="billing_events",
        if_exists=True,
    )
    op.drop_table("billing_events", if_exists=True)
