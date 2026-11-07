from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class Collection(TimestampMixin, Base):
    """A list of titles put together by the librarians ("Books about dragons"); featured
    collections are shown as shelves on the catalogue (see app.services.collections)."""

    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(sa.String(80), unique=True)
    title_en: Mapped[str] = mapped_column(sa.String(200))
    title_ru: Mapped[str | None] = mapped_column(sa.String(200))
    description_en: Mapped[str] = mapped_column(sa.Text, default="", server_default="")
    description_ru: Mapped[str | None] = mapped_column(sa.Text)
    featured: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    position: Mapped[int] = mapped_column(sa.SmallInteger, default=0, server_default="0")


class CollectionBook(Base):
    """A title in a collection, by its copy group (every copy of the title belongs to it)."""

    __tablename__ = "collection_books"

    collection_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True)
    position: Mapped[int] = mapped_column(sa.SmallInteger)
