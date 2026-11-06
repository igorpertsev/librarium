from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, str_enum, uuid_pk
from app.models.enums import BookCategory, BookStatus

# "simple" configuration: no stemming, so it treats English and Russian text alike.
SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('simple', coalesce(author, '')), 'B') || "
    "setweight(to_tsvector('simple', coalesce(description, '')), 'C')"
)


class Book(TimestampMixin, Base):
    """One physical copy of a book.

    Reservations are tracked per copy (``book_id``). Copies of the same title are separate
    rows that share ``copy_group_id`` (NULL means "a group of its own"; the group key is
    ``COALESCE(copy_group_id, id)``): the catalogue shows one entry per group, and edits to
    the description apply to every copy of the group.
    """

    __tablename__ = "books"
    __table_args__ = (
        sa.CheckConstraint(
            "publication_year IS NULL OR publication_year BETWEEN 0 AND 9999",
            name="publication_year_range",
        ),
        sa.Index("ix_books_active_status", "is_active", "status"),
        # Full-text search (title, author, description) and typo-tolerant matching (pg_trgm).
        sa.Index("ix_books_search_vector", "search_vector", postgresql_using="gin"),
        sa.Index(
            "ix_books_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        sa.Index(
            "ix_books_author_trgm",
            "author",
            postgresql_using="gin",
            postgresql_ops={"author": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(sa.String(500))
    author: Mapped[str] = mapped_column(sa.String(300), index=True)
    description: Mapped[str] = mapped_column(sa.Text, default="", server_default="")
    category: Mapped[BookCategory] = mapped_column(
        str_enum(BookCategory, "book_category"), index=True
    )
    age_range: Mapped[str] = mapped_column(sa.String(20), default="", server_default="")
    status: Mapped[BookStatus] = mapped_column(
        str_enum(BookStatus, "book_status"),
        default=BookStatus.AVAILABLE,
        server_default=BookStatus.AVAILABLE.value,
    )
    cover_url: Mapped[str | None] = mapped_column(sa.String(2048))
    image_urls: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(sa.String(2048)),
        default=list,
        server_default=sa.text("'{}'"),
    )
    isbn: Mapped[str | None] = mapped_column(sa.String(32), index=True)
    language: Mapped[str | None] = mapped_column(sa.String(16))
    publication_year: Mapped[int | None] = mapped_column(sa.SmallInteger)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    copy_group_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, index=True)

    @property
    def group_id(self) -> uuid.UUID:
        """The same for every copy of a title."""
        return self.copy_group_id or self.id

    search_vector: Mapped[str] = mapped_column(
        postgresql.TSVECTOR,
        sa.Computed(SEARCH_VECTOR_SQL, persisted=True),
        deferred=True,  # only used in WHERE / ORDER BY
    )
