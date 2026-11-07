"""The scan desk: a librarian scans a copy's label and sees where it stands (in an order waiting
to be handed over, out on loan, held for a reader, or free), to hand over or take back the order."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BookHold, Order, OrderItem, User
from app.models.enums import ACTIVE_ORDER_STATUSES, OrderStatus
from app.schemas.book import BookRead
from app.services.books import get_book


@dataclass(frozen=True, slots=True)
class DeskOrder:
    id: uuid.UUID
    number: int
    status: OrderStatus
    reader_name: str
    child_name: str | None
    due_date: date
    pickup_at: datetime | None
    book_count: int


@dataclass(frozen=True, slots=True)
class DeskCopy:
    book: BookRead
    order: DeskOrder | None
    held_for: str | None
    held_until: datetime | None


async def copy_at_desk(session: AsyncSession, book_id: uuid.UUID) -> DeskCopy:
    book = await get_book(session, book_id, include_inactive=True)  # 404 for an unknown copy
    count = (
        select(func.count(OrderItem.id))
        .where(OrderItem.order_id == Order.id)
        .correlate(Order)
        .scalar_subquery()
    )
    row = (
        await session.execute(
            select(Order, User.full_name, count)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .join(User, User.id == Order.user_id)
            .where(OrderItem.book_id == book_id, Order.status.in_(ACTIVE_ORDER_STATUSES))
            .limit(1)
        )
    ).first()
    order = (
        DeskOrder(
            id=row[0].id,
            number=row[0].number,
            status=row[0].status,
            reader_name=row[1],
            child_name=row[0].child_name,
            due_date=row[0].due_date,
            pickup_at=row[0].pickup_at,
            book_count=int(row[2]),
        )
        if row
        else None
    )
    hold = (
        await session.execute(
            select(BookHold.held_until, User.full_name)
            .join(User, User.id == BookHold.user_id)
            .where(BookHold.book_id == book_id, BookHold.held_until > datetime.now(UTC))
        )
    ).first()
    return DeskCopy(
        book=book,
        order=order,
        held_for=hold[1] if hold else None,
        held_until=hold[0] if hold else None,
    )
