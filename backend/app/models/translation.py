from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, str_enum, utc_now
from app.models.enums import TranslationSource, UiLanguage


class BookTranslation(Base):
    """A book's title, author and description in another interface language.

    The book row keeps the text of the edition on the shelf; readers whose interface is in
    ``language`` see this text instead (and the original title next to it). Like the rest of
    the catalogue data it is kept on every copy of a title and changed for all copies.
    ``*_source`` says where the text came from: typed by a librarian, an official name from
    Wikidata, a Wikipedia summary (``source_url`` for the CC BY-SA attribution) or a machine
    translation.
    """

    __tablename__ = "book_translations"
    __table_args__ = (
        sa.Index(
            "ix_book_translations_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("books.id", ondelete="CASCADE"), primary_key=True
    )
    language: Mapped[UiLanguage] = mapped_column(
        str_enum(UiLanguage, "translation_language"), primary_key=True
    )
    title: Mapped[str] = mapped_column(sa.String(500))
    author: Mapped[str] = mapped_column(sa.String(300), default="", server_default="")
    description: Mapped[str] = mapped_column(sa.Text, default="", server_default="")
    title_source: Mapped[TranslationSource] = mapped_column(
        str_enum(TranslationSource, "translation_title_source"),
        default=TranslationSource.MANUAL,
        server_default=TranslationSource.MANUAL.value,
    )
    description_source: Mapped[TranslationSource] = mapped_column(
        str_enum(TranslationSource, "translation_description_source"),
        default=TranslationSource.MANUAL,
        server_default=TranslationSource.MANUAL.value,
    )
    source_url: Mapped[str | None] = mapped_column(sa.String(2048))
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=sa.func.now()
    )
