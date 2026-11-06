"""Book queries, including the computed reservation state."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, Exists, ScalarSelect, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models import Book, Order, OrderItem
from app.models.enums import ACTIVE_ORDER_STATUSES, BookCategory, BookStatus
from app.schemas.book import BookSort


def active_reservation_exists(book_id: InstrumentedAttribute[uuid.UUID]) -> Exists:
    """EXISTS(an order in an ACTIVE status contains this copy)."""
    return exists().where(
        OrderItem.book_id == book_id,
        OrderItem.order_id == Order.id,
        Order.status.in_(ACTIVE_ORDER_STATUSES),
    )


def active_reservation_due_date(book_id: InstrumentedAttribute[uuid.UUID]) -> ScalarSelect[date]:
    """Due date of the active order holding this copy; NULL when the copy is free.

    Every active order has a due date, so this also answers "is the copy reserved?".
    """
    return (
        select(Order.due_date)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(OrderItem.book_id == book_id, Order.status.in_(ACTIVE_ORDER_STATUSES))
        .order_by(Order.due_date.desc())
        .limit(1)
        .scalar_subquery()
    )


async def reserved_book_ids(session: AsyncSession, book_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    ids = list(book_ids)
    if not ids:
        return set()
    stmt = (
        select(OrderItem.book_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(OrderItem.book_id.in_(ids), Order.status.in_(ACTIVE_ORDER_STATUSES))
    )
    return set((await session.scalars(stmt)).all())


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# Allow-list mapping from API sort keys to columns; user input never reaches SQL text.
_SORT_COLUMNS: dict[BookSort, ColumnElement[Any]] = {
    BookSort.TITLE: func.lower(Book.title).asc(),
    BookSort.TITLE_DESC: func.lower(Book.title).desc(),
    BookSort.AUTHOR: func.lower(Book.author).asc(),
    BookSort.AUTHOR_DESC: func.lower(Book.author).desc(),
    BookSort.PUBLICATION_YEAR: Book.publication_year.asc().nulls_last(),
    BookSort.PUBLICATION_YEAR_DESC: Book.publication_year.desc().nulls_last(),
    BookSort.CREATED_AT: Book.created_at.asc(),
    BookSort.CREATED_AT_DESC: Book.created_at.desc(),
}


@dataclass(frozen=True, slots=True)
class BookFilters:
    q: str | None = None
    category: BookCategory | None = None
    age_range: str | None = None
    status: BookStatus | None = None
    available: bool | None = None
    include_inactive: bool = False


def _conditions(filters: BookFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if not filters.include_inactive:
        conditions.append(Book.is_active.is_(True))
    if filters.q:
        pattern = f"%{escape_like(filters.q)}%"
        conditions.append(
            or_(
                Book.title.ilike(pattern, escape="\\"),
                Book.author.ilike(pattern, escape="\\"),
                Book.isbn.ilike(pattern, escape="\\"),
            )
        )
    if filters.category is not None:
        conditions.append(Book.category == filters.category)
    if filters.age_range:
        conditions.append(Book.age_range == filters.age_range)
    if filters.status is not None:
        conditions.append(Book.status == filters.status)
    if filters.available is not None:
        reserved = active_reservation_exists(Book.id)
        is_available = Book.is_active.is_(True) & (Book.status == BookStatus.AVAILABLE) & ~reserved
        conditions.append(is_available if filters.available else ~is_available)
    return conditions


async def list_books(
    session: AsyncSession,
    filters: BookFilters,
    *,
    sort: BookSort,
    page: int,
    page_size: int,
) -> tuple[list[tuple[Book, date | None]], int]:
    """Books of one page, each with the due date of the order reserving it (or None)."""
    conditions = _conditions(filters)
    total = await session.scalar(select(func.count()).select_from(Book).where(*conditions))
    stmt = (
        select(Book, active_reservation_due_date(Book.id).label("reserved_until"))
        .where(*conditions)
        .order_by(_SORT_COLUMNS[sort], Book.id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    rows = (await session.execute(stmt)).all()
    return [(row[0], row[1]) for row in rows], int(total or 0)


async def get_book_with_reservation(
    session: AsyncSession, book_id: uuid.UUID
) -> tuple[Book, date | None] | None:
    """The book and the due date of the order reserving it (None when free)."""
    stmt = select(Book, active_reservation_due_date(Book.id).label("reserved_until")).where(
        Book.id == book_id
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return row[0], row[1]


async def distinct_age_ranges(session: AsyncSession) -> Sequence[str]:
    stmt = (
        select(Book.age_range)
        .where(Book.is_active.is_(True), Book.age_range != "")
        .distinct()
        .order_by(Book.age_range)
    )
    return (await session.scalars(stmt)).all()
