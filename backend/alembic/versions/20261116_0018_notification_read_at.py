"""notification read_at

Notifications double as the reader's in-app list (the bell); read_at records when they were
seen. Earlier notifications count as read so nobody starts with a pile of old news.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-16 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("UPDATE notifications SET read_at = now()")
    op.create_index(
        "ix_notifications_user_created", "notifications", ["user_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_column("notifications", "read_at")
