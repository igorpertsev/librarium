"""book copies

Copies of one title share books.copy_group_id (NULL = a group of its own).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-06 20:30:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("books", sa.Column("copy_group_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_books_copy_group_id"), "books", ["copy_group_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_books_copy_group_id"), table_name="books")
    op.drop_column("books", "copy_group_id")
