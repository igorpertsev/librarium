"""telegram notifications

The reader's linked Telegram chat and pending link code; when a notification went to Telegram.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-23 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("telegram_link_code", sa.String(length=64), nullable=True))
    op.add_column(
        "users", sa.Column("telegram_link_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint(op.f("uq_users_telegram_chat_id"), "users", ["telegram_chat_id"])
    op.create_unique_constraint(
        op.f("uq_users_telegram_link_code"), "users", ["telegram_link_code"]
    )
    op.add_column(
        "notifications", sa.Column("telegram_sent_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("notifications", "telegram_sent_at")
    op.drop_constraint(op.f("uq_users_telegram_link_code"), "users", type_="unique")
    op.drop_constraint(op.f("uq_users_telegram_chat_id"), "users", type_="unique")
    op.drop_column("users", "telegram_link_expires_at")
    op.drop_column("users", "telegram_link_code")
    op.drop_column("users", "telegram_chat_id")
