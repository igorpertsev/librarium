""" "Want to read": titles a reader keeps for later.

Per title, like the waiting list: an entry names one copy, any copy of the title counts, and
the list shows each title's best copy (one that can be borrowed now, if there is one).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import Book, ReadingListEntry, User
from app.repositories.books import BookFilters, copy_group_key
from app.schemas.book import BookRead, BookSort
from app.services import books as books_service

MAX_ENTRIES = 500


@dataclass(frozen=True, slots=True)
class ReadingListItem:
    book: BookRead
    created_at: datetime


def _entries_of_group(user: User, group: uuid.UUID) -> Select[ReadingListEntry]:
    return (
        select(ReadingListEntry)
        .join(Book, Book.id == ReadingListEntry.book_id)
        .where(ReadingListEntry.user_id == user.id, copy_group_key() == group)
    )


async def list_items(session: AsyncSession, user: User) -> list[ReadingListItem]:
    rows = (
        await session.execute(
            select(copy_group_key(), ReadingListEntry.created_at)
            .join(Book, Book.id == ReadingListEntry.book_id)
            .where(ReadingListEntry.user_id == user.id, Book.is_active.is_(True))
            .order_by(ReadingListEntry.created_at.desc())
            .limit(MAX_ENTRIES)
        )
    ).all()
    added = dict(reversed(rows))  # title -> when it was first added
    if not added:
        return []
    books, _ = await books_service.list_books(
        session,
        BookFilters(groups=tuple(added)),
        sort=BookSort.TITLE,
        page=1,
        page_size=len(added),
        group_copies=True,
    )
    items = [ReadingListItem(book, added[book.group_id]) for book in books]
    return sorted(items, key=lambda item: item.created_at, reverse=True)


async def add(session: AsyncSession, user: User, book_id: uuid.UUID) -> bool:
    """Add the title of this copy; returns False when it was already on the list."""
    book = await session.get(Book, book_id)
    if book is None or not book.is_active:
        raise NotFoundError("Book not found", code="BOOK_NOT_FOUND")
    if await session.scalar(_entries_of_group(user, book.group_id).limit(1)) is not None:
        return False
    session.add(ReadingListEntry(id=uuid.uuid4(), user_id=user.id, book_id=book_id))
    await session.commit()
    return True


async def remove(session: AsyncSession, user: User, book_id: uuid.UUID) -> None:
    """Remove the title of this copy (every copy of it)."""
    book = await session.get(Book, book_id)
    if book is None:
        return
    ids = (
        select(ReadingListEntry.id)
        .join(Book, Book.id == ReadingListEntry.book_id)
        .where(ReadingListEntry.user_id == user.id, copy_group_key() == book.group_id)
    )
    await session.execute(delete(ReadingListEntry).where(ReadingListEntry.id.in_(ids)))
    await session.commit()
