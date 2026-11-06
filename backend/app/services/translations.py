"""Missing translations for the whole catalogue (``python -m app.cli translate-books``)."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book, BookTranslation
from app.models.enums import TranslationSource, UiLanguage
from app.schemas.book import BookUpdate
from app.schemas.translation import BookTranslationIn, TranslationSuggestRequest
from app.services import books as books_service
from app.services.translation_lookup import TranslationLookup

_CYRILLIC = re.compile("[\u0400-\u04ff]")


def book_language(book: Book) -> str:
    """The book's language; when it is not recorded, guessed from the title's alphabet."""
    return book.language or ("ru" if _CYRILLIC.search(book.title) else "en")


async def translate_catalogue(
    session: AsyncSession,
    lookup: TranslationLookup,
    *,
    target: UiLanguage,
    machine: bool,
    limit: int,
    pause_seconds: float = 1.0,
    report: Callable[[str], None] = print,
) -> int:
    """Translate up to ``limit`` titles that have no ``target`` translation; returns how many."""
    group = func.coalesce(Book.copy_group_id, Book.id)
    untranslated = (
        select(Book)
        .where(
            Book.is_active.is_(True),
            ~exists().where(BookTranslation.book_id == Book.id, BookTranslation.language == target),
        )
        .ext(distinct_on(group))  # one copy per title; the update reaches every copy
        .order_by(group, Book.id)
    )
    books = sorted((await session.scalars(untranslated)).all(), key=lambda b: b.title.lower())
    done = 0
    for book in books:
        if done >= limit:
            break
        if book_language(book) == target.value:
            continue
        suggestion = await lookup.suggest(
            TranslationSuggestRequest(
                target=target,
                title=book.title,
                author=book.author,
                description=book.description,
                isbn=book.isbn,
                language=book.language,
                machine=machine,
            )
        )
        if not suggestion.title:
            report(f"- {book.title}: nothing found")
            continue
        translation = BookTranslationIn(
            language=target,
            title=suggestion.title,
            author=suggestion.author or "",
            description=suggestion.description or "",
            title_source=suggestion.title_source or TranslationSource.MANUAL,
            description_source=suggestion.description_source or TranslationSource.MANUAL,
            source_url=suggestion.source_url,
        )
        others = [
            BookTranslationIn.model_validate(item, from_attributes=True)
            for item in book.translations
            if item.language != target
        ]
        await books_service.update_book(
            session, book.id, BookUpdate(translations=[*others, translation])
        )
        done += 1
        found = (suggestion.title_source, suggestion.description_source)
        sources = ", ".join(str(source) for source in found if source)
        report(f"+ {book.title} -> {suggestion.title} ({sources})")
        if pause_seconds:
            await asyncio.sleep(pause_seconds)  # be gentle with Wikidata and Wikipedia
    return done
