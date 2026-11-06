"""Holds: a returned copy is kept for the reader who has waited longest for its title.

Offering (``app.services.waitlist.notify_waiting_readers``) creates the hold and queues a
"held for you" email. The holder can borrow the copy until ``held_until``; nobody else can.
Ordering it, releasing it or letting it expire ends the hold, and an expired or released copy
is offered to the next reader in line.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BookHold, User
from app.schemas.book import BookRead
from app.services import books as books_service


async def held_by_others(
    session: AsyncSession, book_ids: Iterable[uuid.UUID], user_id: uuid.UUID, now: datetime
) -> set[uuid.UUID]:
    ids = list(book_ids)
    if not ids:
        return set()
    rows = await session.scalars(
        select(BookHold.book_id).where(
            BookHold.book_id.in_(ids), BookHold.user_id != user_id, BookHold.held_until > now
        )
    )
    return set(rows.all())


async def held_for(
    session: AsyncSession, book_id: uuid.UUID, user_id: uuid.UUID, now: datetime
) -> bool:
    hold = await session.get(BookHold, book_id)
    return hold is not None and hold.user_id == user_id and hold.held_until > now


async def consume(session: AsyncSession, user_id: uuid.UUID, book_ids: Iterable[uuid.UUID]) -> None:
    """The holder borrowed these copies: their holds end (in the caller's transaction)."""
    ids = list(book_ids)
    if ids:
        await session.execute(
            delete(BookHold).where(BookHold.user_id == user_id, BookHold.book_id.in_(ids))
        )


@dataclass(frozen=True, slots=True)
class HeldBook:
    book: BookRead
    held_until: datetime


async def list_for(session: AsyncSession, user: User, now: datetime) -> list[HeldBook]:
    holds = (
        await session.scalars(
            select(BookHold)
            .where(BookHold.user_id == user.id, BookHold.held_until > now)
            .order_by(BookHold.held_until)
        )
    ).all()
    found = []
    for hold in holds:
        book = await books_service.get_book(session, hold.book_id)
        found.append(HeldBook(book, hold.held_until))
    return found


async def release(session: AsyncSession, user: User, book_id: uuid.UUID) -> None:
    """The holder does not want the book: it goes to the next reader in line."""
    from app.services import waitlist  # noqa: PLC0415 - waitlist imports this module

    result = await session.execute(
        delete(BookHold)
        .where(BookHold.book_id == book_id, BookHold.user_id == user.id)
        .returning(BookHold.book_id)
    )
    if result.first() is not None:
        await waitlist.notify_waiting_readers(session, [book_id])
    await session.commit()


async def expire(session: AsyncSession, now: datetime) -> int:
    """End holds that ran out and offer those copies to the next readers; returns how many
    ended. Run regularly (the notifier does)."""
    from app.services import waitlist  # noqa: PLC0415 - waitlist imports this module

    ended = (
        await session.scalars(
            delete(BookHold).where(BookHold.held_until <= now).returning(BookHold.book_id)
        )
    ).all()
    if ended:
        await waitlist.notify_waiting_readers(session, ended)
    await session.commit()
    return len(ended)
