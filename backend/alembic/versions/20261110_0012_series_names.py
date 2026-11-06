"""series names

English and Russian names of a series for readers of each interface language.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-10 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("series", sa.Column("name_en", sa.String(length=300), nullable=True))
    op.add_column("series", sa.Column("name_ru", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("series", "name_ru")
    op.drop_column("series", "name_en")
