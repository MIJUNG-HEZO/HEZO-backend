"""users FK에 ON DELETE CASCADE 추가

Revision ID: 0009_add_cascade_delete_to_user_fks
Revises: 0008_add_active_subscription_unique_index
Create Date: 2026-06-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_cascade_user_fks"
down_revision: str | None = "0008_add_sub_unique_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # sites.owner_id → users.id
    op.drop_constraint("sites_owner_id_fkey", "sites", type_="foreignkey")
    op.create_foreign_key(
        "sites_owner_id_fkey", "sites", "users", ["owner_id"], ["id"], ondelete="CASCADE"
    )

    # subscriptions.user_id → users.id
    op.drop_constraint("subscriptions_user_id_fkey", "subscriptions", type_="foreignkey")
    op.create_foreign_key(
        "subscriptions_user_id_fkey", "subscriptions", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )

    # refresh_tokens.user_id → users.id
    op.drop_constraint("refresh_tokens_user_id_fkey", "refresh_tokens", type_="foreignkey")
    op.create_foreign_key(
        "refresh_tokens_user_id_fkey", "refresh_tokens", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )

    # social_accounts.user_id → users.id
    op.drop_constraint("social_accounts_user_id_fkey", "social_accounts", type_="foreignkey")
    op.create_foreign_key(
        "social_accounts_user_id_fkey", "social_accounts", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )

    # email_verification_tokens.user_id → users.id
    op.drop_constraint("email_verification_tokens_user_id_fkey", "email_verification_tokens", type_="foreignkey")
    op.create_foreign_key(
        "email_verification_tokens_user_id_fkey", "email_verification_tokens", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )

    # payment_requests.user_id → users.id
    op.drop_constraint("payment_requests_user_id_fkey", "payment_requests", type_="foreignkey")
    op.create_foreign_key(
        "payment_requests_user_id_fkey", "payment_requests", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )

    # billing_events.user_id → users.id (nullable → SET NULL)
    op.drop_constraint("billing_events_user_id_fkey", "billing_events", type_="foreignkey")
    op.create_foreign_key(
        "billing_events_user_id_fkey", "billing_events", "users", ["user_id"], ["id"], ondelete="SET NULL"
    )

    # billing_events.payment_request_id → payment_requests.id (nullable → SET NULL)
    op.drop_constraint("billing_events_payment_request_id_fkey", "billing_events", type_="foreignkey")
    op.create_foreign_key(
        "billing_events_payment_request_id_fkey", "billing_events", "payment_requests", ["payment_request_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("billing_events_payment_request_id_fkey", "billing_events", type_="foreignkey")
    op.create_foreign_key(
        "billing_events_payment_request_id_fkey", "billing_events", "payment_requests", ["payment_request_id"], ["id"]
    )

    op.drop_constraint("billing_events_user_id_fkey", "billing_events", type_="foreignkey")
    op.create_foreign_key(
        "billing_events_user_id_fkey", "billing_events", "users", ["user_id"], ["id"]
    )

    op.drop_constraint("payment_requests_user_id_fkey", "payment_requests", type_="foreignkey")
    op.create_foreign_key(
        "payment_requests_user_id_fkey", "payment_requests", "users", ["user_id"], ["id"]
    )

    op.drop_constraint("email_verification_tokens_user_id_fkey", "email_verification_tokens", type_="foreignkey")
    op.create_foreign_key(
        "email_verification_tokens_user_id_fkey", "email_verification_tokens", "users", ["user_id"], ["id"]
    )

    op.drop_constraint("social_accounts_user_id_fkey", "social_accounts", type_="foreignkey")
    op.create_foreign_key(
        "social_accounts_user_id_fkey", "social_accounts", "users", ["user_id"], ["id"]
    )

    op.drop_constraint("refresh_tokens_user_id_fkey", "refresh_tokens", type_="foreignkey")
    op.create_foreign_key(
        "refresh_tokens_user_id_fkey", "refresh_tokens", "users", ["user_id"], ["id"]
    )

    op.drop_constraint("subscriptions_user_id_fkey", "subscriptions", type_="foreignkey")
    op.create_foreign_key(
        "subscriptions_user_id_fkey", "subscriptions", "users", ["user_id"], ["id"]
    )

    op.drop_constraint("sites_owner_id_fkey", "sites", type_="foreignkey")
    op.create_foreign_key(
        "sites_owner_id_fkey", "sites", "users", ["owner_id"], ["id"]
    )
