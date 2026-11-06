from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now, uuid_pk

# A book has many tags and a tag many books. Like the rest of the catalogue data, tags are
# kept on every copy of a title and changed for all copies together.
book_tags = sa.Table(
    "book_tags",
    Base.metadata,
    sa.Column("book_id", sa.Uuid, sa.ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("tag_id", sa.Uuid, sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    sa.Index("ix_book_tags_tag_id", "tag_id"),
)


class Tag(Base):
    """A topic readers can browse by (adventure, fantasy, ...), named in both UI languages.

    The list is kept by librarians, so the same topic is not spelt three ways.
    """

    __tablename__ = "tags"
    __table_args__ = (sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(sa.String(64), unique=True)
    name_en: Mapped[str] = mapped_column(sa.String(64))
    name_ru: Mapped[str] = mapped_column(sa.String(64))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
