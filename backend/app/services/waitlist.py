"""Waiting list: customers ask to be emailed when a book that is out comes back.

Waiting is per title: an entry names one copy, but any copy of the title (copy group) that
becomes available counts. Everyone waiting is emailed at the same moment and their entries
are removed; the first to order gets the book. While anybody waits for a title, its current
borrowers cannot extend their loans (see ``app.services.orders.renewal_refusal``).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Book, BookHold, LibrarySettings, Notification, User, WaitlistEntry
from app.models.enums import BookStatus, NotificationKind
from app.models.library_settings import SETTINGS_ROW_ID
from app.repositories.books import copy_group_key, reserved_book_ids


async def _groups(session: AsyncSession, book_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """Copy groups (titles) of the given copies."""
    ids = list(book_ids)
    if not ids:
        return set()
    return set((await session.scalars(select(copy_group_key()).where(Book.id.in_(ids)))).all())


async def free_copies(
    session: AsyncSession, groups: set[uuid.UUID]
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """(title, copy) of copies anyone could order right now: active, status available, not in
    an active order and not held for a reader."""
    if not groups:
        return []
    rows = (
        await session.execute(
            select(copy_group_key(), Book.id)
            .where(
                copy_group_key().in_(groups),
                Book.is_active,
                Book.status == BookStatus.AVAILABLE,
                ~exists().where(BookHold.book_id == Book.id, BookHold.held_until > func.now()),
            )
            .order_by(Book.id)
        )
    ).all()
    reserved = await reserved_book_ids(session, [book_id for _, book_id in rows])
    return [(group, book_id) for group, book_id in rows if book_id not in reserved]


async def available_groups(session: AsyncSession, groups: set[uuid.UUID]) -> set[uuid.UUID]:
    """Titles with at least one copy that can be ordered right now."""
    return {group for group, _ in await free_copies(session, groups)}


def _entries_for_groups(groups: set[uuid.UUID]) -> Select[uuid.UUID]:
    return (
        select(WaitlistEntry.id)
        .join(Book, Book.id == WaitlistEntry.book_id)
        .where(copy_group_key().in_(groups))
    )


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
    group = book.copy_group_id or book.id
    if await available_groups(session, {group}):
        raise ConflictError(
            "This book is available now: add it to your cart instead", code="BOOK_AVAILABLE"
        )
    # One entry per title: waiting for any copy is waiting for all of them.
    existing = await session.scalar(
        select(WaitlistEntry)
        .where(WaitlistEntry.user_id == user.id, WaitlistEntry.id.in_(_entries_for_groups({group})))
        .options(selectinload(WaitlistEntry.book))
    )
    if existing is not None:
        return existing, False
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
    """Stop waiting for the title of this copy."""
    groups = await _groups(session, [book_id])
    if groups:
        await session.execute(
            delete(WaitlistEntry).where(
                WaitlistEntry.user_id == user.id, WaitlistEntry.id.in_(_entries_for_groups(groups))
            )
        )
        await session.commit()


async def notify_waiting_readers(session: AsyncSession, book_ids: Iterable[uuid.UUID]) -> int:
    """Pass free copies of these books' titles to the readers waiting for them. With holds
    (library setting ``hold_hours`` > 0) each free copy is held for the reader who has waited
    longest; without, everybody waiting is emailed and the first to order gets it. Runs inside
    the caller's transaction; returns how many readers were told."""
    await session.flush()  # the caller's status change must be visible to the queries below
    groups = await _groups(session, book_ids)
    library = await session.get(LibrarySettings, SETTINGS_ROW_ID)
    hold_hours = library.hold_hours if library is not None else 0
    if hold_hours > 0:
        return await _offer_holds(session, groups, timedelta(hours=hold_hours))
    available = await available_groups(session, groups)
    if not available:
        return 0
    entries = (
        await session.execute(
            delete(WaitlistEntry)
            .where(WaitlistEntry.id.in_(_entries_for_groups(available)))
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


async def _offer_holds(session: AsyncSession, groups: set[uuid.UUID], hold_for: timedelta) -> int:
    offered = 0
    held_until = datetime.now(UTC) + hold_for
    for group, copy_id in await free_copies(session, groups):
        first = await session.scalar(
            select(WaitlistEntry)
            .where(WaitlistEntry.id.in_(_entries_for_groups({group})))
            .order_by(WaitlistEntry.created_at, WaitlistEntry.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if first is None:
            continue  # nobody (else) waiting for this title
        await session.delete(first)
        # An expired hold on this copy may still be stored: replace it.
        await session.execute(
            pg_insert(BookHold)
            .values(book_id=copy_id, user_id=first.user_id, held_until=held_until)
            .on_conflict_do_update(
                index_elements=[BookHold.book_id],
                set_={"user_id": first.user_id, "held_until": held_until, "created_at": func.now()},
            )
        )
        session.add(
            Notification(
                id=uuid.uuid4(),
                user_id=first.user_id,
                book_id=copy_id,
                kind=NotificationKind.BOOK_HELD,
            )
        )
        await session.flush()
        offered += 1
    return offered


async def has_waiting_readers(
    session: AsyncSession, book_ids: Iterable[uuid.UUID], *, except_user: uuid.UUID
) -> bool:
    groups = await _groups(session, book_ids)
    if not groups:
        return False
    return bool(
        await session.scalar(
            select(
                exists().where(
                    WaitlistEntry.id.in_(_entries_for_groups(groups)),
                    WaitlistEntry.user_id != except_user,
                )
            )
        )
    )
