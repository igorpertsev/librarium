"""Waiting list: customers ask to be emailed when a book that is out comes back.

Everyone waiting is emailed at the same moment and their entries are removed; the first to
order gets the book. While anybody waits for a book, its current borrower cannot extend the
loan (see ``app.services.orders.renewal_refusal``).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Book, Notification, User, WaitlistEntry
from app.models.enums import BookStatus, NotificationKind
from app.repositories.books import reserved_book_ids


async def _available_ids(session: AsyncSession, book_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """Books that can be ordered right now: active, status available and not reserved."""
    ids = list(book_ids)
    if not ids:
        return set()
    candidates = set(
        (
            await session.scalars(
                select(Book.id).where(
                    Book.id.in_(ids), Book.is_active, Book.status == BookStatus.AVAILABLE
                )
            )
        ).all()
    )
    return candidates - await reserved_book_ids(session, candidates)


async def list_entries(session: AsyncSession, user: User) -> list[WaitlistEntry]:
    stmt = (
        select(WaitlistEntry)
        .join(Book, Book.id == WaitlistEntry.book_id)
        .where(WaitlistEntry.user_id == user.id, Book.is_active)
        .options(selectinload(WaitlistEntry.book))
        .order_by(WaitlistEntry.created_at, WaitlistEntry.id)
    )
    return list((await session.scalars(stmt)).all())


async def join(session: AsyncSession, user: User, book_id: uuid.UUID) -> tuple[WaitlistEntry, bool]:
    """Add the book to the user's waiting list; returns (entry, created)."""
    book = await session.get(Book, book_id)
    if book is None or not book.is_active:
        raise NotFoundError("Book not found", code="BOOK_NOT_FOUND")
    if book_id in await _available_ids(session, [book_id]):
        raise ConflictError(
            "This book is available now: add it to your cart instead", code="BOOK_AVAILABLE"
        )
    inserted = await session.scalar(
        pg_insert(WaitlistEntry)
        .values(id=uuid.uuid4(), user_id=user.id, book_id=book_id)
        .on_conflict_do_nothing(index_elements=[WaitlistEntry.user_id, WaitlistEntry.book_id])
        .returning(WaitlistEntry.id)
    )
    await session.commit()
    entry = await session.scalar(
        select(WaitlistEntry)
        .where(WaitlistEntry.user_id == user.id, WaitlistEntry.book_id == book_id)
        .options(selectinload(WaitlistEntry.book))
    )
    assert entry is not None  # noqa: S101 - inserted or already present
    return entry, inserted is not None


async def leave(session: AsyncSession, user: User, book_id: uuid.UUID) -> None:
    await session.execute(
        delete(WaitlistEntry).where(
            WaitlistEntry.user_id == user.id, WaitlistEntry.book_id == book_id
        )
    )
    await session.commit()


async def notify_waiting_readers(session: AsyncSession, book_ids: Iterable[uuid.UUID]) -> int:
    """Queue a "book is back" email for everyone waiting for any of these books that is now
    available, and clear their entries. Runs inside the caller's transaction."""
    await session.flush()  # the caller's status change must be visible to the queries below
    available = await _available_ids(session, book_ids)
    if not available:
        return 0
    entries = (
        await session.execute(
            delete(WaitlistEntry)
            .where(WaitlistEntry.book_id.in_(available))
            .returning(WaitlistEntry.user_id, WaitlistEntry.book_id)
        )
    ).all()
    if entries:
        await session.execute(
            pg_insert(Notification),
            [
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "book_id": book_id,
                    "kind": NotificationKind.BOOK_AVAILABLE,
                }
                for user_id, book_id in entries
            ],
        )
    return len(entries)


async def has_waiting_readers(
    session: AsyncSession, book_ids: Iterable[uuid.UUID], *, except_user: uuid.UUID
) -> bool:
    ids = list(book_ids)
    if not ids:
        return False
    return bool(
        await session.scalar(
            select(
                exists().where(WaitlistEntry.book_id.in_(ids), WaitlistEntry.user_id != except_user)
            )
        )
    )
