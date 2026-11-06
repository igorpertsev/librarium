"""Books that look like one already in the library: the same ISBN (hyphens and spaces
ignored), or the same title and author (any case). Used to warn before adding a duplicate."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book
from app.repositories.books import BookFilters, copy_group_key
from app.schemas.book import BookRead, BookSort
from app.services import books as books_service

MAX_MATCHES = 5


def isbn_key(isbn: str | None) -> str | None:
    key = re.sub(r"[^0-9X]", "", (isbn or "").upper())
    return key or None


def name_key(title: str | None, author: str | None) -> tuple[str, str] | None:
    if not title or not author or not title.strip() or not author.strip():
        return None
    return title.strip().lower(), author.strip().lower()


def _book_isbn_key() -> ColumnElement[str]:
    return func.regexp_replace(func.upper(Book.isbn), "[^0-9X]", "", "g")


async def find(
    session: AsyncSession, *, isbn: str | None, title: str | None, author: str | None
) -> list[BookRead]:
    """Titles in the library (one entry each, with copy counts) that match."""
    conditions: list[ColumnElement[bool]] = []
    if key := isbn_key(isbn):
        conditions.append(_book_isbn_key() == key)
    if names := name_key(title, author):
        conditions.append(
            and_(func.lower(Book.title) == names[0], func.lower(Book.author) == names[1])
        )
    if not conditions:
        return []
    groups = (
        await session.scalars(
            select(copy_group_key()).where(Book.is_active.is_(True), or_(*conditions)).distinct()
        )
    ).all()
    if not groups:
        return []
    books, _ = await books_service.list_books(
        session,
        BookFilters(groups=tuple(groups)),
        sort=BookSort.TITLE,
        page=1,
        page_size=MAX_MATCHES,
        group_copies=True,
    )
    return books


async def existing_keys(
    session: AsyncSession, isbns: Iterable[str], names: Iterable[tuple[str, str]]
) -> tuple[dict[str, tuple[uuid.UUID, str]], dict[tuple[str, str], tuple[uuid.UUID, str]]]:
    """For a whole import at once: which ISBN keys and (title, author) pairs exist already,
    each mapped to (a copy's id, its title)."""
    isbn_set, name_set = set(isbns), set(names)
    by_isbn: dict[str, tuple[uuid.UUID, str]] = {}
    by_name: dict[tuple[str, str], tuple[uuid.UUID, str]] = {}
    if not isbn_set and not name_set:
        return by_isbn, by_name
    wanted: list[ColumnElement[bool]] = []
    if isbn_set:
        wanted.append(_book_isbn_key().in_(isbn_set))
    if name_set:
        wanted.append(func.lower(Book.title).in_({title for title, _ in name_set}))
    rows = (
        await session.execute(
            select(Book.id, Book.title, Book.author, _book_isbn_key()).where(
                Book.is_active.is_(True), or_(*wanted)
            )
        )
    ).all()
    for book_id, title, author, key in rows:
        if key and key in isbn_set:
            by_isbn.setdefault(key, (book_id, title))
        book_names = name_key(title, author)
        if book_names and book_names in name_set:
            by_name.setdefault(book_names, (book_id, title))
    return by_isbn, by_name
    rows = (
        await session.execute(
            select(Book.id, Book.title, Book.author, _book_isbn_key()).where(
                Book.is_active.is_(True),
                or_(
                    _book_isbn_key().in_(isbn_set) if isbn_set else False,
                    func.lower(Book.title).in_({title for title, _ in name_set})
                    if name_set
                    else False,
                ),
            )
        )
    ).all()
    for book_id, title, author, key in rows:
        if key and key in isbn_set:
            by_isbn.setdefault(key, (book_id, title))
        names = name_key(title, author)
        if names and names in name_set:
            by_name.setdefault(names, (book_id, title))
    return by_isbn, by_name
