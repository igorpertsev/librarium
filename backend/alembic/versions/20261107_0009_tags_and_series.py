"""tags and series

Tags (bilingual topics with a starter list librarians can edit) linked to books, and series
with the position of each book in its series.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-07 10:00:00.000000+00:00
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STARTER_TAGS = [
    ("adventure", "Adventure", "Приключения"),
    ("fantasy", "Fantasy", "Фэнтези"),
    ("science-fiction", "Science fiction", "Научная фантастика"),
    ("detective", "Detective & mystery", "Детектив"),
    ("dystopia", "Dystopia", "Антиутопия"),
    ("romance", "Romance", "Любовный роман"),
    ("horror", "Horror", "Ужасы"),
    ("historical", "Historical", "Историческое"),
    ("humor", "Humor", "Юмор"),
    ("classics", "Classics", "Классика"),
    ("poetry", "Poetry", "Поэзия"),
    ("fairy-tales", "Fairy tales", "Сказки"),
    ("magic", "Magic", "Волшебство"),
    ("animals", "Animals", "Животные"),
    ("school", "School", "Школа"),
    ("friendship", "Friendship", "Дружба"),
    ("family", "Family", "Семья"),
    ("war", "War", "Война"),
    ("coming-of-age", "Coming of age", "Взросление"),
    ("true-story", "True story", "Реальная история"),
]


def upgrade() -> None:
    tags = op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name_en", sa.String(length=64), nullable=False),
        sa.Column("name_ru", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f("ck_tags_slug_format")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("slug", name=op.f("uq_tags_slug")),
    )
    op.create_table(
        "series",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("openlibrary_key", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_series")),
        sa.UniqueConstraint("name", name=op.f("uq_series_name")),
        sa.UniqueConstraint("openlibrary_key", name=op.f("uq_series_openlibrary_key")),
    )
    op.create_table(
        "book_tags",
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["book_id"], ["books.id"], name=op.f("fk_book_tags_book_id_books"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], name=op.f("fk_book_tags_tag_id_tags"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("book_id", "tag_id", name=op.f("pk_book_tags")),
    )
    op.create_index("ix_book_tags_tag_id", "book_tags", ["tag_id"], unique=False)

    op.add_column("books", sa.Column("series_id", sa.Uuid(), nullable=True))
    op.add_column(
        "books", sa.Column("series_position", sa.Numeric(precision=6, scale=2), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_books_series_id_series"), "books", "series", ["series_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_books_series_id"), "books", ["series_id"], unique=False)
    op.create_check_constraint(
        op.f("ck_books_series_position_positive"),
        "books",
        "series_position IS NULL OR series_position > 0",
    )

    op.bulk_insert(
        tags,
        [
            {"id": uuid.uuid4(), "slug": slug, "name_en": name_en, "name_ru": name_ru}
            for slug, name_en, name_ru in STARTER_TAGS
        ],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_books_series_position_positive"), "books", type_="check")
    op.drop_index(op.f("ix_books_series_id"), table_name="books")
    op.drop_constraint(op.f("fk_books_series_id_series"), "books", type_="foreignkey")
    op.drop_column("books", "series_position")
    op.drop_column("books", "series_id")
    op.drop_index("ix_book_tags_tag_id", table_name="book_tags")
    op.drop_table("book_tags")
    op.drop_table("series")
    op.drop_table("tags")
