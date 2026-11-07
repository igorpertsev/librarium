"""Reserving a title for a date ("I need it for the holidays").

The reader picks a title and the day they want it from. A copy is assigned that can be free
by then: no other reservation within a loan period of that day, and not out on a loan due on
or after it. From one loan period before the day nobody else can borrow that copy (it would
not be back in time) and loans of it cannot be extended past the day. On the day (or as soon
as a late copy comes back) the copy is held for the reader like a returned book and they get
a "ready" email; the hold then works as in ``app.services.holds``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models import AdvanceReservation, Book, BookHold, Notification, Order, OrderItem, User
from app.models.enums import (
    ACTIVE_ORDER_STATUSES,
    BookStatus,
    NotificationKind,
    ReservationStatus,
)
from app.repositories.books import copy_group_key, reserved_ahead_exists
from app.schemas.book import BookRead
from app.services import books as books_service
from app.services import waitlist
from app.services.library_settings import get_library_settings

MAX_DAYS_AHEAD = 90
MAX_ACTIVE_PER_READER = 5
# How long a reserved copy waits for the reader once its day has come (at least).
MIN_HOLD = timedelta(hours=48)


def _today() -> date:
    return datetime.now(UTC).date()


@dataclass(frozen=True, slots=True)
class ReservationView:
    id: uuid.UUID
    book: BookRead
    starts_on: date
    status: ReservationStatus


async def _view(session: AsyncSession, reservation: AdvanceReservation) -> ReservationView:
    book = await books_service.get_book(session, reservation.book_id)
    return ReservationView(reservation.id, book, reservation.starts_on, reservation.status)


async def list_for(session: AsyncSession, user: User) -> list[ReservationView]:
    rows = (
        await session.scalars(
            select(AdvanceReservation)
            .where(
                AdvanceReservation.user_id == user.id,
                AdvanceReservation.status == ReservationStatus.ACTIVE,
            )
            .order_by(AdvanceReservation.starts_on)
        )
    ).all()
    return [await _view(session, row) for row in rows]


async def _free_copy_for(
    session: AsyncSession, group: uuid.UUID, starts_on: date, loan: timedelta
) -> Book | None:
    """A copy of the title that will be free on ``starts_on`` for a whole loan, locked."""
    copies = (
        await session.scalars(
            select(Book)
            .where(
                copy_group_key() == group,
                Book.is_active.is_(True),
                Book.status == BookStatus.AVAILABLE,
            )
            .order_by(Book.id)
            .with_for_update()
        )
    ).all()
    for copy in copies:
        clashing_reservation = await session.scalar(
            select(AdvanceReservation.id).where(
                AdvanceReservation.book_id == copy.id,
                AdvanceReservation.status == ReservationStatus.ACTIVE,
                AdvanceReservation.starts_on > starts_on - loan,
                AdvanceReservation.starts_on < starts_on + loan,
            )
        )
        out_too_long = await session.scalar(
            select(Order.id)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(
                OrderItem.book_id == copy.id,
                Order.status.in_(ACTIVE_ORDER_STATUSES),
                Order.due_date >= starts_on,
            )
        )
        if clashing_reservation is None and out_too_long is None:
            return copy
    return None


async def create(
    session: AsyncSession, user: User, book_id: uuid.UUID, starts_on: date
) -> ReservationView:
    today = _today()
    if not today < starts_on <= today + timedelta(days=MAX_DAYS_AHEAD):
        raise BadRequestError(
            f"Choose a day from tomorrow to {MAX_DAYS_AHEAD} days ahead",
            code="INVALID_RESERVATION_DATE",
            details={"max_days_ahead": MAX_DAYS_AHEAD},
        )
    book = await session.get(Book, book_id)
    if book is None or not book.is_active:
        raise NotFoundError("Book not found", code="BOOK_NOT_FOUND")
    group = book.copy_group_id or book.id
    library = await get_library_settings(session, lock="share")
    mine = (
        (
            await session.execute(
                select(copy_group_key())
                .join(AdvanceReservation, AdvanceReservation.book_id == Book.id)
                .where(
                    AdvanceReservation.user_id == user.id,
                    AdvanceReservation.status == ReservationStatus.ACTIVE,
                )
            )
        )
        .scalars()
        .all()
    )
    if group in mine:
        raise ConflictError("You have already reserved this book", code="ALREADY_RESERVED")
    if len(mine) >= MAX_ACTIVE_PER_READER:
        raise ConflictError(
            f"You can reserve up to {MAX_ACTIVE_PER_READER} books ahead",
            code="TOO_MANY_RESERVATIONS",
            details={"limit": MAX_ACTIVE_PER_READER},
        )
    copy = await _free_copy_for(session, group, starts_on, timedelta(days=library.loan_period_days))
    if copy is None:
        raise ConflictError("No copy is free for that day", code="NO_COPY_FOR_DATE")
    reservation = AdvanceReservation(
        id=uuid.uuid4(), user_id=user.id, book_id=copy.id, starts_on=starts_on
    )
    session.add(reservation)
    await session.commit()
    return await _view(session, reservation)


async def cancel(session: AsyncSession, user: User, reservation_id: uuid.UUID) -> None:
    reservation = await session.scalar(
        select(AdvanceReservation)
        .where(
            AdvanceReservation.id == reservation_id,
            AdvanceReservation.user_id == user.id,
            AdvanceReservation.status == ReservationStatus.ACTIVE,
        )
        .with_for_update()
    )
    if reservation is None:
        raise NotFoundError("Reservation not found", code="RESERVATION_NOT_FOUND")
    reservation.status = ReservationStatus.CANCELLED
    # The copy may have been kept for this reservation: readers waiting for it get it now.
    await waitlist.notify_waiting_readers(session, [reservation.book_id])
    await session.commit()


async def kept_copies(session: AsyncSession, book_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """Copies set aside for a reservation (nobody may borrow them until it is fulfilled)."""
    ids = list(book_ids)
    if not ids:
        return set()
    rows = await session.scalars(
        select(Book.id).where(Book.id.in_(ids), reserved_ahead_exists(Book.id))
    )
    return set(rows.all())


async def blocks_renewal(
    session: AsyncSession, book_ids: Iterable[uuid.UUID], new_due: date
) -> bool:
    """A reservation of one of these copies starts before the extended due date."""
    ids = list(book_ids)
    if not ids:
        return False
    found = await session.scalar(
        select(AdvanceReservation.id)
        .where(
            AdvanceReservation.book_id.in_(ids),
            AdvanceReservation.status == ReservationStatus.ACTIVE,
            AdvanceReservation.starts_on <= new_due,
        )
        .limit(1)
    )
    return found is not None


async def activate(session: AsyncSession, now: datetime | None = None) -> int:
    """Hold the copies of reservations whose day has come for their readers (when the copy is
    back); returns how many. Run regularly (the notifier does)."""
    now = now or datetime.now(UTC)
    library = await get_library_settings(session)
    held_until = now + max(timedelta(hours=library.hold_hours), MIN_HOLD)
    due = (
        await session.scalars(
            select(AdvanceReservation)
            .where(
                AdvanceReservation.status == ReservationStatus.ACTIVE,
                AdvanceReservation.starts_on <= now.date(),
            )
            .order_by(AdvanceReservation.starts_on, AdvanceReservation.created_at)
            .with_for_update(skip_locked=True)
        )
    ).all()
    ready = 0
    for reservation in due:
        on_loan = await session.scalar(
            select(OrderItem.id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                OrderItem.book_id == reservation.book_id,
                Order.status.in_(ACTIVE_ORDER_STATUSES),
            )
            .limit(1)
        )
        held = await session.scalar(
            select(BookHold.book_id).where(
                BookHold.book_id == reservation.book_id,
                BookHold.held_until > now,
                BookHold.user_id != reservation.user_id,
            )
        )
        if on_loan is not None or held is not None:
            continue  # still out (returned late): try again next time
        await session.execute(
            pg_insert(BookHold)
            .values(book_id=reservation.book_id, user_id=reservation.user_id, held_until=held_until)
            .on_conflict_do_update(
                index_elements=[BookHold.book_id],
                set_={
                    "user_id": reservation.user_id,
                    "held_until": held_until,
                    "created_at": func.now(),
                },
            )
        )
        reservation.status = ReservationStatus.FULFILLED
        session.add(
            Notification(
                id=uuid.uuid4(),
                user_id=reservation.user_id,
                book_id=reservation.book_id,
                kind=NotificationKind.RESERVATION_READY,
            )
        )
        ready += 1
    await session.commit()
    return ready


@dataclass(frozen=True, slots=True)
class UpcomingReservation:
    id: uuid.UUID
    starts_on: date
    book_id: uuid.UUID
    title: str
    author: str
    reader_name: str
    reader_email: str


async def upcoming(session: AsyncSession, limit: int = 100) -> list[UpcomingReservation]:
    """Admin: active reservations, soonest first."""
    rows = (
        await session.execute(
            select(
                AdvanceReservation.id,
                AdvanceReservation.starts_on,
                Book.id,
                Book.title,
                Book.author,
                User.full_name,
                User.email,
            )
            .join(Book, Book.id == AdvanceReservation.book_id)
            .join(User, User.id == AdvanceReservation.user_id)
            .where(AdvanceReservation.status == ReservationStatus.ACTIVE)
            .order_by(AdvanceReservation.starts_on, AdvanceReservation.created_at)
            .limit(limit)
        )
    ).all()
    return [UpcomingReservation(*row) for row in rows]
