"""초기 사이트 슬롯 스키마 생성

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

subscription_status_enum = postgresql.ENUM(
    "active",
    "trialing",
    "past_due",
    "canceled",
    "expired",
    name="subscription_status",
    create_type=False,
)
site_status_enum = postgresql.ENUM(
    "draft",
    "archived",
    "deleted",
    name="site_status",
    create_type=False,
)
site_type_enum = postgresql.ENUM(
    "landing",
    "blog",
    "store",
    name="site_type",
    create_type=False,
)
module_key_enum = postgresql.ENUM(
    "medical",
    "personal_blog",
    "restaurant",
    name="module_key",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    subscription_status_enum.create(bind, checkfirst=True)
    site_status_enum.create(bind, checkfirst=True)
    site_type_enum.create(bind, checkfirst=True)
    module_key_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("idx_users_deleted_at", "users", ["deleted_at"])

    op.create_table(
        "plans",
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("price_monthly", sa.Integer(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(), server_default="KRW", nullable=False),
        sa.Column("max_sites", sa.Integer(), server_default="1", nullable=False),
        sa.Column("can_publish", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("idx_plans_code", "plans", ["code"])
    op.create_index("idx_plans_is_active", "plans", ["is_active"])

    op.create_table(
        "subscriptions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            subscription_status_enum,
            server_default="active",
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("renewed_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index("idx_subscriptions_plan_id", "subscriptions", ["plan_id"])
    op.create_index("idx_subscriptions_status", "subscriptions", ["status"])
    op.create_index("idx_subscriptions_user_id", "subscriptions", ["user_id"])

    op.create_table(
        "sites",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("site_type", site_type_enum, nullable=False),
        sa.Column("module_key", module_key_enum, nullable=False),
        sa.Column("status", site_status_enum, server_default="draft", nullable=False),
        sa.Column("is_published", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_sites_deleted_at", "sites", ["deleted_at"])
    op.create_index("idx_sites_module_key", "sites", ["module_key"])
    op.create_index("idx_sites_owner_id", "sites", ["owner_id"])
    op.create_index("idx_sites_site_type", "sites", ["site_type"])
    op.create_index("idx_sites_status", "sites", ["status"])


def downgrade() -> None:
    op.drop_index("idx_sites_status", table_name="sites")
    op.drop_index("idx_sites_site_type", table_name="sites")
    op.drop_index("idx_sites_owner_id", table_name="sites")
    op.drop_index("idx_sites_module_key", table_name="sites")
    op.drop_index("idx_sites_deleted_at", table_name="sites")
    op.drop_table("sites")

    op.drop_index("idx_subscriptions_user_id", table_name="subscriptions")
    op.drop_index("idx_subscriptions_status", table_name="subscriptions")
    op.drop_index("idx_subscriptions_plan_id", table_name="subscriptions")
    op.drop_table("subscriptions")

    op.drop_index("idx_plans_is_active", table_name="plans")
    op.drop_index("idx_plans_code", table_name="plans")
    op.drop_table("plans")

    op.drop_index("idx_users_deleted_at", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    module_key_enum.drop(bind, checkfirst=True)
    site_type_enum.drop(bind, checkfirst=True)
    site_status_enum.drop(bind, checkfirst=True)
    subscription_status_enum.drop(bind, checkfirst=True)
