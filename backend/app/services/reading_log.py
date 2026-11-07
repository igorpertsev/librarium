"""Reading log: titles a reader has finished ("I've read it"), and badges for children.

Per title, like the reading list. Badges are worked out from the log every time, so removing a
title can take a badge away again; nothing is stored about them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import String, cast, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.models import Book, Order, OrderItem, ReadingLogEntry, User
from app.models.enums import OrderStatus
from app.repositories.books import BookFilters, copy_group_key
from app.schemas.book import BookRead, BookSort
from app.services import books as books_service

MAX_ENTRIES = 1000
MAX_SUGGESTIONS = 6
EARLIEST = date(1900, 1, 1)


@dataclass(frozen=True, slots=True)
class Badge:
    key: str
    earned: bool
    progress: int
    goal: int


@dataclass(frozen=True, slots=True)
class LoggedBook:
    book: BookRead
    finished_on: date


@dataclass(frozen=True, slots=True)
class ReadingLog:
    entries: list[LoggedBook]
    total: int
    this_year: int
    badges: list[Badge]
    to_log: list[BookRead]  # borrowed titles not in the log yet ("finished one of these?")


@dataclass(frozen=True, slots=True)
class _Read:
    group: uuid.UUID
    finished_on: date
    category: str
    language: str | None
    series_id: uuid.UUID | None


def _today() -> date:
    return datetime.now(UTC).date()


async def _read(session: AsyncSession, user: User) -> list[_Read]:
    rows = (
        await session.execute(
            select(
                copy_group_key(),
                func.max(ReadingLogEntry.finished_on),
                func.min(Book.category),
                func.min(Book.language),
                func.min(cast(Book.series_id, String)),
            )
            .join(Book, Book.id == ReadingLogEntry.book_id)
            .where(ReadingLogEntry.user_id == user.id)
            .group_by(copy_group_key())
            .limit(MAX_ENTRIES)
        )
    ).all()
    return [
        _Read(
            group=group,
            finished_on=finished,
            category=str(category),
            language=language,
            series_id=uuid.UUID(series) if series else None,
        )
        for group, finished, category, language, series in rows
    ]


async def _completed_series(session: AsyncSession, read: list[_Read]) -> int:
    """Series of at least two titles of which the reader has read every title."""
    read_groups = {item.group for item in read}
    series_ids = {item.series_id for item in read if item.series_id}
    if not series_ids:
        return 0
    rows = (
        await session.execute(
            select(Book.series_id, func.array_agg(func.distinct(copy_group_key())))
            .where(Book.series_id.in_(series_ids), Book.is_active.is_(True))
            .group_by(Book.series_id)
        )
    ).all()
    return sum(1 for _, groups in rows if len(groups) >= 2 and set(groups) <= read_groups)


def _months_in_a_row(read: list[_Read], today: date) -> int:
    """How many of the last three calendar months (this one included) have a finished title."""
    months = {(item.finished_on.year, item.finished_on.month) for item in read}
    found = 0
    year, month = today.year, today.month
    for _ in range(3):
        if (year, month) in months:
            found += 1
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return found


def _badge(key: str, progress: int, goal: int) -> Badge:
    return Badge(key=key, earned=progress >= goal, progress=min(progress, goal), goal=goal)


async def _badges(session: AsyncSession, read: list[_Read], today: date) -> list[Badge]:
    total = len(read)
    return [
        _badge("first_book", total, 1),
        _badge("five_books", total, 5),
        _badge("ten_books", total, 10),
        _badge("twenty_five_books", total, 25),
        _badge("explorer", len({item.category for item in read}), 3),
        _badge("two_languages", len({item.language for item in read if item.language}), 2),
        _badge("series_finisher", await _completed_series(session, read), 1),
        _badge("three_months", _months_in_a_row(read, today), 3),
    ]


async def _books(session: AsyncSession, groups: list[uuid.UUID]) -> dict[uuid.UUID, BookRead]:
    if not groups:
        return {}
    books, _ = await books_service.list_books(
        session,
        BookFilters(groups=tuple(groups)),
        sort=BookSort.TITLE,
        page=1,
        page_size=len(groups),
        group_copies=True,
    )
    return {book.group_id: book for book in books}


async def _borrowed_not_logged(
    session: AsyncSession, user: User, logged: set[uuid.UUID]
) -> list[uuid.UUID]:
    rows = (
        await session.execute(
            select(copy_group_key(), func.max(Order.created_at))
            .join(OrderItem, OrderItem.book_id == Book.id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.user_id == user.id,
                Order.status.in_([OrderStatus.CONFIRMED, OrderStatus.RETURNED]),
            )
            .group_by(copy_group_key())
            .order_by(func.max(Order.created_at).desc())
            .limit(MAX_SUGGESTIONS + len(logged))
        )
    ).all()
    return [group for group, _ in rows if group not in logged][:MAX_SUGGESTIONS]


async def reading_log(session: AsyncSession, user: User) -> ReadingLog:
    today = _today()
    read = sorted(await _read(session, user), key=lambda item: item.finished_on, reverse=True)
    logged = {item.group for item in read}
    suggested = await _borrowed_not_logged(session, user, logged)
    books = await _books(session, [item.group for item in read] + suggested)
    return ReadingLog(
        entries=[
            LoggedBook(books[item.group], item.finished_on) for item in read if item.group in books
        ],
        total=len(read),
        this_year=sum(1 for item in read if item.finished_on.year == today.year),
        badges=await _badges(session, read, today),
        to_log=[books[group] for group in suggested if group in books],
    )


async def mark_read(
    session: AsyncSession, user: User, book_id: uuid.UUID, finished_on: date | None = None
) -> None:
    """Log the title of this copy as finished (on ``finished_on``, default today); logging
    it again changes the day."""
    day = finished_on or _today()
    if not EARLIEST <= day <= _today():
        raise BadRequestError("The day must not be in the future", code="INVALID_FINISHED_ON")
    book = await session.get(Book, book_id)
    if book is None:
        raise NotFoundError("Book not found", code="BOOK_NOT_FOUND")
    existing = await session.scalar(
        select(ReadingLogEntry)
        .join(Book, Book.id == ReadingLogEntry.book_id)
        .where(ReadingLogEntry.user_id == user.id, copy_group_key() == book.group_id)
        .limit(1)
    )
    if existing is not None:
        existing.finished_on = day
    else:
        session.add(
            ReadingLogEntry(id=uuid.uuid4(), user_id=user.id, book_id=book_id, finished_on=day)
        )
    await session.commit()


async def unmark(session: AsyncSession, user: User, book_id: uuid.UUID) -> None:
    """Take the title of this copy (every copy of it) off the log."""
    book = await session.get(Book, book_id)
    if book is None:
        return
    ids = (
        select(ReadingLogEntry.id)
        .join(Book, Book.id == ReadingLogEntry.book_id)
        .where(ReadingLogEntry.user_id == user.id, copy_group_key() == book.group_id)
    )
    await session.execute(delete(ReadingLogEntry).where(ReadingLogEntry.id.in_(ids)))
    await session.commit()
