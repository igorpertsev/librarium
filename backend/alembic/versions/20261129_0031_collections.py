"""collections and book of the month

Librarians' collections of titles; the book of the month in the library settings.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-29 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("title_en", sa.String(length=200), nullable=False),
        sa.Column("title_ru", sa.String(length=200), nullable=True),
        sa.Column("description_en", sa.Text(), server_default="", nullable=False),
        sa.Column("description_ru", sa.Text(), nullable=True),
        sa.Column("featured", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("position", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collections")),
        sa.UniqueConstraint("slug", name=op.f("uq_collections_slug")),
    )
    op.create_table(
        "collection_books",
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collections.id"],
            name=op.f("fk_collection_books_collection_id_collections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("collection_id", "group_id", name=op.f("pk_collection_books")),
    )
    op.add_column("library_settings", sa.Column("pick_group_id", sa.Uuid(), nullable=True))
    op.add_column(
        "library_settings", sa.Column("pick_note_en", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "library_settings", sa.Column("pick_note_ru", sa.String(length=500), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("library_settings", "pick_note_ru")
    op.drop_column("library_settings", "pick_note_en")
    op.drop_column("library_settings", "pick_group_id")
    op.drop_table("collection_books")
    op.drop_table("collections")
