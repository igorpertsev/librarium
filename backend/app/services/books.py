from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import Book, CartItem
from app.models.enums import BookStatus
from app.repositories import books as books_repo
from app.repositories.books import BookFilters
from app.schemas.book import BookCreate, BookRead, BookSort, BookStats, BookUpdate


def book_not_found() -> NotFoundError:
    return NotFoundError("Book not found", code="BOOK_NOT_FOUND")


# Catalogue data that every copy of a title shares; status stays per copy.
SHARED_FIELDS = frozenset(
    {
        "title",
        "author",
        "description",
        "category",
        "age_range",
        "cover_url",
        "image_urls",
        "isbn",
        "language",
        "publication_year",
    }
)


async def list_books(
    session: AsyncSession,
    filters: BookFilters,
    *,
    sort: BookSort,
    page: int,
    page_size: int,
    group_copies: bool = False,
) -> tuple[list[BookRead], int]:
    rows, total = await books_repo.list_books(
        session, filters, sort=sort, page=page, page_size=page_size, group_copies=group_copies
    )
    return [
        BookRead.from_book(
            row.book,
            reserved_until=row.reserved_until,
            copies=row.copies,
            copies_available=row.copies_available,
        )
        for row in rows
    ], total


async def get_book(
    session: AsyncSession, book_id: uuid.UUID, *, include_inactive: bool = False
) -> BookRead:
    found = await books_repo.get_book_with_reservation(session, book_id)
    if found is None or (not include_inactive and not found[0].is_active):
        raise book_not_found()
    book, reserved_until = found
    copies, copies_available = await books_repo.copy_counts(session, book)
    return BookRead.from_book(
        book, reserved_until=reserved_until, copies=copies, copies_available=copies_available
    )


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
    changes = patch.changes()
    for field, value in changes.items():
        setattr(book, field, value)
    shared = {field: value for field, value in changes.items() if field in SHARED_FIELDS}
    if shared and book.copy_group_id is not None:
        # The other copies of the title get the same catalogue data.
        await session.execute(
            update(Book)
            .where(Book.copy_group_id == book.copy_group_id, Book.id != book.id)
            .values(**shared)
        )
    await session.commit()
    # Existing orders keep their snapshot; only the catalogue entry changes.
    return await get_book(session, book_id)


async def add_copies(session: AsyncSession, book_id: uuid.UUID, count: int) -> list[BookRead]:
    """New copies of a title, with the same catalogue data, available for lending."""
    book = await session.get(Book, book_id, with_for_update=True)
    if book is None or not book.is_active:
        raise book_not_found()
    if book.copy_group_id is None:
        book.copy_group_id = book.id  # the first copy names the group
    copies = [
        Book(
            id=uuid.uuid4(),
            copy_group_id=book.copy_group_id,
            status=BookStatus.AVAILABLE,
            **{field: getattr(book, field) for field in SHARED_FIELDS},
        )
        for _ in range(count)
    ]
    session.add_all(copies)
    await session.commit()
    return [await get_book(session, copy.id) for copy in copies]


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
