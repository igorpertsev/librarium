"""calendar feed

The hash of each reader's private calendar feed token.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-27 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("calendar_token_hash", sa.String(length=64), nullable=True))
    op.create_unique_constraint(
        op.f("uq_users_calendar_token_hash"), "users", ["calendar_token_hash"]
    )


def downgrade() -> None:
    op.drop_constraint(op.f("uq_users_calendar_token_hash"), "users", type_="unique")
    op.drop_column("users", "calendar_token_hash")
