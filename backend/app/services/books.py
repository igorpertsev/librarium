from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import Book, BookTranslation, CartItem, Series
from app.models.enums import BookStatus
from app.repositories import books as books_repo
from app.repositories.books import BookFilters
from app.schemas.book import (
    BookCreate,
    BookRead,
    BookSort,
    BookStats,
    BookUpdate,
    BulkBookUpdate,
    BulkResult,
)
from app.schemas.translation import BookTranslationIn
from app.services import catalog, waitlist


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
        "series_id",
        "series_position",
    }
)
# Request fields that are not columns: resolved into tags and series_id.
_LINK_FIELDS = frozenset({"tags", "series_name", "series_openlibrary_key", "translations"})


def translation_rows(items: Sequence[BookTranslationIn | BookTranslation]) -> list[BookTranslation]:
    """New rows (one book's) from request data or from another copy's translations."""
    return [
        BookTranslation(
            language=item.language,
            title=item.title,
            author=item.author,
            description=item.description,
            title_source=item.title_source,
            description_source=item.description_source,
            source_url=item.source_url,
        )
        for item in items
    ]


async def _resolve_series_id(
    session: AsyncSession,
    *,
    series_id: uuid.UUID | None,
    series_name: str | None,
    openlibrary_key: str | None,
) -> uuid.UUID | None:
    if series_id is not None:
        if await session.get(Series, series_id) is None:
            raise catalog.series_not_found()
        return series_id
    if series_name:
        series = await catalog.find_or_create_series(
            session, name=series_name, openlibrary_key=openlibrary_key
        )
        return series.id
    return None


async def new_book(session: AsyncSession, data: BookCreate) -> Book:
    """Add a book (not committed): the caller commits, e.g. after a whole CSV import."""
    book = Book(id=uuid.uuid4(), **data.model_dump(exclude=set(_LINK_FIELDS | {"series_id"})))
    book.series_id = await _resolve_series_id(
        session,
        series_id=data.series_id,
        series_name=data.series_name,
        openlibrary_key=data.series_openlibrary_key,
    )
    if book.series_id is None:
        book.series_position = None
    book.tags = await catalog.resolve_tags(session, data.tags)
    book.translations = translation_rows(data.translations)
    session.add(book)
    return book


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


async def languages(session: AsyncSession) -> Sequence[str]:
    return await books_repo.distinct_languages(session)


async def age_ranges(session: AsyncSession) -> Sequence[str]:
    return await books_repo.distinct_age_ranges(session)


async def create_book(session: AsyncSession, data: BookCreate) -> BookRead:
    book = await new_book(session, data)
    await session.commit()
    return await get_book(session, book.id)


async def update_book(session: AsyncSession, book_id: uuid.UUID, patch: BookUpdate) -> BookRead:
    book = await session.get(Book, book_id, with_for_update=True)
    if book is None or not book.is_active:
        raise book_not_found()
    changes = patch.changes()
    tags = changes.pop("tags", None)
    translations = patch.translations if "translations" in changes else None
    changes.pop("translations", None)
    series_name = changes.pop("series_name", None)
    openlibrary_key = changes.pop("series_openlibrary_key", None)
    if "series_id" in changes or series_name:
        changes["series_id"] = await _resolve_series_id(
            session,
            series_id=changes.get("series_id"),
            series_name=series_name,
            openlibrary_key=openlibrary_key,
        )
        if changes["series_id"] is None:
            changes["series_position"] = None
    for field, value in changes.items():
        setattr(book, field, value)
    if "series_id" in changes:  # keep the loaded relationship in step with the column
        book.series = (
            await session.get(Series, changes["series_id"]) if changes["series_id"] else None
        )
    if tags is not None:
        book.tags = await catalog.resolve_tags(session, tags)
    if translations is not None:
        await _replace_translations(session, book, translations)

    if book.copy_group_id is not None:
        await _update_other_copies(
            session, book, changes, translations, tags_changed=tags is not None
        )
    if book.status is BookStatus.AVAILABLE:
        await waitlist.notify_waiting_readers(session, [book.id])
    await session.commit()
    # Existing orders keep their snapshot; only the catalogue entry changes.
    return await get_book(session, book_id)


async def _update_other_copies(
    session: AsyncSession,
    book: Book,
    changes: dict[str, Any],
    translations: Sequence[BookTranslationIn] | None,
    *,
    tags_changed: bool,
) -> None:
    """The other copies of the title get the same catalogue data."""
    shared = {field: value for field, value in changes.items() if field in SHARED_FIELDS}
    if shared:
        await session.execute(
            update(Book)
            .where(Book.copy_group_id == book.copy_group_id, Book.id != book.id)
            .values(**shared)
        )
    if tags_changed or translations is not None:
        others = await session.scalars(
            select(Book).where(Book.copy_group_id == book.copy_group_id, Book.id != book.id)
        )
        for copy in others:
            if tags_changed:
                copy.tags = list(book.tags)
            if translations is not None:
                await _replace_translations(session, copy, translations)


async def _replace_translations(
    session: AsyncSession, book: Book, items: Sequence[BookTranslationIn]
) -> None:
    # Delete first: the new rows have the same primary key (book, language).
    book.translations = []
    await session.flush()
    book.translations = translation_rows(items)


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
            tags=list(book.tags),
            translations=translation_rows(book.translations),
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


async def bulk_update(session: AsyncSession, body: BulkBookUpdate) -> BulkResult:
    """Apply one change to every copy of the chosen titles, in one transaction."""
    groups = select(books_repo.copy_group_key()).where(Book.id.in_(body.book_ids)).scalar_subquery()
    copies = list(
        (
            await session.scalars(
                select(Book)
                .where(books_repo.copy_group_key().in_(groups), Book.is_active.is_(True))
                .order_by(Book.id)
                .with_for_update()
            )
        ).all()
    )
    if not copies:
        raise book_not_found()
    add = await catalog.resolve_tags(session, body.add_tags)
    remove = {tag.slug for tag in await catalog.resolve_tags(session, body.remove_tags)}
    for copy in copies:
        if body.status is not None:
            copy.status = body.status
        if body.category is not None:
            copy.category = body.category
        if body.condition is not None:
            copy.condition = body.condition
        if add or remove:
            kept = [tag for tag in copy.tags if tag.slug not in remove]
            copy.tags = kept + [tag for tag in add if tag not in kept]
        if body.deactivate:
            copy.is_active = False
    ids = [copy.id for copy in copies]
    if body.deactivate:
        await session.execute(delete(CartItem).where(CartItem.book_id.in_(ids)))
    elif body.status is BookStatus.AVAILABLE:
        await waitlist.notify_waiting_readers(session, ids)
    await session.commit()
    return BulkResult(
        titles=len({copy.copy_group_id or copy.id for copy in copies}), copies=len(ids)
    )
