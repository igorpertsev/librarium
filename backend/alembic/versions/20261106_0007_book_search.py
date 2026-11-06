"""book search

Full-text search over title, author and description (generated tsvector + GIN index) and
typo-tolerant matching of title and author (pg_trgm trigram indexes).

Note: revision 0007 is meant to follow 0006 (book copies); on this branch it follows 0003.
When the branches are merged, set down_revision to the previous head.

Revision ID: 0007
Revises: 0003
Create Date: 2026-11-06 21:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('simple', coalesce(author, '')), 'B') || "
    "setweight(to_tsvector('simple', coalesce(description, '')), 'C')"
)


def upgrade() -> None:
    # pg_trgm is a trusted extension: the database owner may create it.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.add_column(
        "books",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_VECTOR_SQL, persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_books_search_vector", "books", ["search_vector"], postgresql_using="gin"
    )
    op.create_index(
        "ix_books_title_trgm",
        "books",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_books_author_trgm",
        "books",
        ["author"],
        postgresql_using="gin",
        postgresql_ops={"author": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_books_author_trgm", table_name="books")
    op.drop_index("ix_books_title_trgm", table_name="books")
    op.drop_index("ix_books_search_vector", table_name="books")
    op.drop_column("books", "search_vector")
    # The extension stays: other objects in the database may use it.
