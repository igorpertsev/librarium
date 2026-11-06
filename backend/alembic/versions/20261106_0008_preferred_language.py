"""preferred language

users.preferred_language: the interface language the user chose ("en" / "ru"); customer
emails use it. NULL means unknown (emails in English and Russian).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-06 21:30:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # VARCHAR + CHECK, like the other enums (add_column does not emit an Enum's CHECK).
    op.add_column("users", sa.Column("preferred_language", sa.String(length=32), nullable=True))
    op.create_check_constraint(
        op.f("ck_users_ui_language"), "users", "preferred_language IN ('en', 'ru')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_ui_language"), "users", type_="check")
    op.drop_column("users", "preferred_language")
