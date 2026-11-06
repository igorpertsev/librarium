"""Recommendations from what readers borrowed.

Only aggregates are shown: a title appears only when at least ``MIN_READERS`` different
readers borrowed it, so nobody's individual borrowing can be read off the suggestions.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book, Order, OrderItem, ReadingListEntry, book_tags
from app.models.enums import OrderStatus
from app.repositories.books import BookFilters, copy_group_key
from app.schemas.book import BookRead, BookSort
from app.services import books as books_service

MIN_READERS = 2
MAX_SUGGESTIONS = 6
MAX_FOR_READER = 8
_BORROWED = (OrderStatus.CONFIRMED, OrderStatus.RETURNED)


async def _ranked(session: AsyncSession, ranking: list[uuid.UUID]) -> list[BookRead]:
    """The titles (copy groups) in ``ranking`` order, each as its best copy."""
    if not ranking:
        return []
    books, _ = await books_service.list_books(
        session,
        BookFilters(groups=tuple(ranking)),
        sort=BookSort.TITLE,
        page=1,
        page_size=len(ranking),
        group_copies=True,
    )
    by_group = {book.group_id: book for book in books}
    return [by_group[group] for group in ranking if group in by_group]


async def also_borrowed(session: AsyncSession, book_id: uuid.UUID) -> list[BookRead]:
    """Titles most often borrowed by the readers who borrowed this one."""
    book = await books_service.get_book(session, book_id)
    group = copy_group_key()
    readers_of_book = (
        select(Order.user_id)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .join(Book, Book.id == OrderItem.book_id)
        .where(group == book.group_id, Order.status.in_(_BORROWED))
    )
    readers = func.count(func.distinct(Order.user_id))
    rows = (
        await session.execute(
            select(group, readers)
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .join(Book, Book.id == OrderItem.book_id)
            .where(
                Order.user_id.in_(readers_of_book),
                Order.status.in_(_BORROWED),
                group != book.group_id,
                Book.is_active.is_(True),
            )
            .group_by(group)
            .having(readers >= MIN_READERS)
            .order_by(readers.desc(), group)
            .limit(MAX_SUGGESTIONS)
        )
    ).all()
    return await _ranked(session, [row[0] for row in rows])


async def for_reader(session: AsyncSession, user_id: uuid.UUID) -> list[BookRead]:
    """Titles the reader has not borrowed or saved, ranked by how many of their borrowed and
    saved titles share each tag (newest first among equals)."""
    group = copy_group_key()
    borrowed = (
        select(group.label("grp"))
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Book, Book.id == OrderItem.book_id)
        .where(Order.user_id == user_id, Order.status != OrderStatus.CANCELLED)
    )
    saved = (
        select(group.label("grp"))
        .select_from(ReadingListEntry)
        .join(Book, Book.id == ReadingListEntry.book_id)
        .where(ReadingListEntry.user_id == user_id)
    )
    known = borrowed.union(saved).subquery("known")
    weights = (
        select(book_tags.c.tag_id, func.count(func.distinct(group)).label("weight"))
        .join(Book, Book.id == book_tags.c.book_id)
        .where(group.in_(select(known.c.grp)))
        .group_by(book_tags.c.tag_id)
        .subquery("weights")
    )
    score = func.sum(weights.c.weight)
    rows = (
        await session.execute(
            select(group, score)
            .select_from(book_tags)
            .join(weights, weights.c.tag_id == book_tags.c.tag_id)
            .join(Book, Book.id == book_tags.c.book_id)
            .where(Book.is_active.is_(True), group.not_in(select(known.c.grp)))
            .group_by(group)
            .order_by(score.desc(), func.max(Book.created_at).desc())
            .limit(MAX_FOR_READER)
        )
    ).all()
    return await _ranked(session, [row[0] for row in rows])
