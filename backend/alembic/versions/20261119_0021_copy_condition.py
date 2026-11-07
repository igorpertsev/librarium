"""copy condition

How each copy looks (new, good, worn, damaged) and a librarian's note.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-19 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "books", sa.Column("condition", sa.String(length=32), server_default="good", nullable=False)
    )
    op.add_column("books", sa.Column("condition_note", sa.String(length=300), nullable=True))
    op.create_check_constraint(
        op.f("ck_books_copy_condition"),
        "books",
        "condition IN ('new', 'good', 'worn', 'damaged')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_books_copy_condition"), "books", type_="check")
    op.drop_column("books", "condition_note")
    op.drop_column("books", "condition")
