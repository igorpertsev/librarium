"""Moving through a series: the volumes around a book, and what a reader could read next."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book, Order, OrderItem, User
from app.models.enums import OrderStatus
from app.repositories.books import BookFilters, copy_group_key
from app.schemas.book import BookRead, BookSort
from app.services import books as books_service

MAX_VOLUMES = 100
# Orders that count as "read or reading" (a cancelled request does not).
_READ = (OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.RETURNED)


@dataclass(frozen=True, slots=True)
class Neighbours:
    previous: BookRead | None
    next: BookRead | None


async def _volumes(session: AsyncSession, series_id: uuid.UUID) -> list[BookRead]:
    """One entry per title of the series, in volume order (unnumbered ones last)."""
    books, _ = await books_service.list_books(
        session,
        BookFilters(series_id=series_id),
        sort=BookSort.SERIES,
        page=1,
        page_size=MAX_VOLUMES,
        group_copies=True,
    )
    return books


async def neighbours(session: AsyncSession, book_id: uuid.UUID) -> Neighbours:
    book = await books_service.get_book(session, book_id)
    position = book.series_position
    if book.series is None or position is None:
        return Neighbours(None, None)
    numbered = [
        v
        for v in await _volumes(session, book.series.id)
        if v.series_position is not None and v.group_id != book.group_id
    ]
    before = [v for v in numbered if v.series_position is not None and v.series_position < position]
    after = [v for v in numbered if v.series_position is not None and v.series_position > position]
    return Neighbours(before[-1] if before else None, after[0] if after else None)


async def next_for_reader(session: AsyncSession, user: User) -> list[BookRead]:
    """For each series the reader has borrowed from, the first volume after the furthest one
    they borrowed that they have not borrowed yet."""
    read = (
        select(Book.series_id, copy_group_key().label("grp"), Book.series_position)
        .join(OrderItem, OrderItem.book_id == Book.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.user_id == user.id, Order.status.in_(_READ), Book.series_id.is_not(None))
    )
    rows = (await session.execute(read)).all()
    furthest: dict[uuid.UUID, float] = {}
    for series_id, _, position in rows:
        if series_id is not None and position is not None:
            furthest[series_id] = max(position, furthest.get(series_id, 0))
    read_groups = {group for _, group, _ in rows}
    suggestions: list[BookRead] = []
    for series_id, reached in furthest.items():
        for volume in await _volumes(session, series_id):
            position = volume.series_position
            if position is not None and position > reached and volume.group_id not in read_groups:
                suggestions.append(volume)
                break
    return sorted(suggestions, key=lambda b: (b.series.name.lower() if b.series else "", b.id))
