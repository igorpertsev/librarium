from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import Book, CartItem
from app.models.enums import BookStatus
from app.repositories import books as books_repo
from app.repositories.books import BookFilters
from app.schemas.book import BookCreate, BookRead, BookSort, BookStats, BookUpdate


def book_not_found() -> NotFoundError:
    return NotFoundError("Book not found", code="BOOK_NOT_FOUND")


async def list_books(
    session: AsyncSession, filters: BookFilters, *, sort: BookSort, page: int, page_size: int
) -> tuple[list[BookRead], int]:
    rows, total = await books_repo.list_books(
        session, filters, sort=sort, page=page, page_size=page_size
    )
    return [BookRead.from_book(book, reserved_until=until) for book, until in rows], total


async def get_book(
    session: AsyncSession, book_id: uuid.UUID, *, include_inactive: bool = False
) -> BookRead:
    found = await books_repo.get_book_with_reservation(session, book_id)
    if found is None or (not include_inactive and not found[0].is_active):
        raise book_not_found()
    book, reserved_until = found
    return BookRead.from_book(book, reserved_until=reserved_until)


async def age_ranges(session: AsyncSession) -> Sequence[str]:
    return await books_repo.distinct_age_ranges(session)


async def create_book(session: AsyncSession, data: BookCreate) -> BookRead:
    book = Book(id=uuid.uuid4(), **data.model_dump())
    session.add(book)
    await session.commit()
    return BookRead.from_book(book, reserved_until=None)


async def update_book(session: AsyncSession, book_id: uuid.UUID, patch: BookUpdate) -> BookRead:
    book = await session.get(Book, book_id, with_for_update=True)
    if book is None or not book.is_active:
        raise book_not_found()
    for field, value in patch.changes().items():
        setattr(book, field, value)
    await session.commit()
    # Existing orders keep their snapshot; only the catalogue entry changes.
    return await get_book(session, book_id)


async def deactivate_book(session: AsyncSession, book_id: uuid.UUID) -> None:
    """Soft delete: order history keeps referencing the copy, carts drop it."""
    book = await session.get(Book, book_id, with_for_update=True)
    if book is None or not book.is_active:
        raise book_not_found()
    book.is_active = False
    await session.execute(delete(CartItem).where(CartItem.book_id == book_id))
    await session.commit()


async def stats(session: AsyncSession) -> BookStats:
    reserved = books_repo.active_reservation_exists(Book.id)
    row = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(Book.status == BookStatus.AVAILABLE),
                func.count().filter(Book.status == BookStatus.AVAILABLE_SOON),
                func.count().filter(Book.status == BookStatus.NOT_AVAILABLE),
                func.sum(case((reserved, 1), else_=0)),
            ).where(Book.is_active.is_(True))
        )
    ).one()
    return BookStats(
        total=row[0],
        available=row[1],
        available_soon=row[2],
        not_available=row[3],
        reserved=int(row[4] or 0),
    )
