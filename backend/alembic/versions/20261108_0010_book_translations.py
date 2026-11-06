"""book translations

Title, author and description of a book in the other interface language, with where each
came from (librarian, Wikidata, Wikipedia, machine translation).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-08 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCES = "'manual', 'wikidata', 'wikipedia', 'machine'"


def upgrade() -> None:
    op.create_table(
        "book_translations",
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("author", sa.String(length=300), server_default="", nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("title_source", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column(
            "description_source", sa.String(length=32), server_default="manual", nullable=False
        ),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "language IN ('en', 'ru')", name=op.f("ck_book_translations_translation_language")
        ),
        sa.CheckConstraint(
            f"title_source IN ({SOURCES})",
            name=op.f("ck_book_translations_translation_title_source"),
        ),
        sa.CheckConstraint(
            f"description_source IN ({SOURCES})",
            name=op.f("ck_book_translations_translation_description_source"),
        ),
        sa.ForeignKeyConstraint(
            ["book_id"],
            ["books.id"],
            name=op.f("fk_book_translations_book_id_books"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("book_id", "language", name=op.f("pk_book_translations")),
    )
    # Typo-tolerant search by the translated title ("над пропастью" finds the English book).
    op.create_index(
        "ix_book_translations_title_trgm",
        "book_translations",
        ["title"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_book_translations_title_trgm",
        table_name="book_translations",
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.drop_table("book_translations")
