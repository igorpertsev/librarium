"""reading list

"Want to read": titles a reader keeps for later, separate from the cart.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-09 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reading_list_entries",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["book_id"],
            ["books.id"],
            name=op.f("fk_reading_list_entries_book_id_books"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_reading_list_entries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reading_list_entries")),
        sa.UniqueConstraint(
            "user_id", "book_id", name=op.f("uq_reading_list_entries_user_id_book_id")
        ),
    )
    op.create_index(
        op.f("ix_reading_list_entries_user_id"), "reading_list_entries", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_reading_list_entries_book_id"), "reading_list_entries", ["book_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_reading_list_entries_book_id"), table_name="reading_list_entries")
    op.drop_index(op.f("ix_reading_list_entries_user_id"), table_name="reading_list_entries")
    op.drop_table("reading_list_entries")
