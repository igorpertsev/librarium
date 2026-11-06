from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class Series(TimestampMixin, Base):
    """A story told in several books (Harry Potter, ten volumes of a detective series...)."""

    __tablename__ = "series"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(sa.String(300), unique=True)
    # How readers of each interface language know the series ("Гарри Поттер"); empty: ``name``.
    name_en: Mapped[str | None] = mapped_column(sa.String(300))
    name_ru: Mapped[str | None] = mapped_column(sa.String(300))
    description: Mapped[str] = mapped_column(sa.Text, default="", server_default="")
    # Open Library series key (e.g. "OL326110L"): editions in other languages find the
    # same series when they are looked up by ISBN.
    openlibrary_key: Mapped[str | None] = mapped_column(sa.String(32), unique=True)
