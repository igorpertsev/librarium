"""The reader's notification list in the app (the bell).

It shows the same events as the emails (``notifications``), whether or not the email could be
sent, except news that went stale before it was delivered (``expired``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book, Notification, Order, User
from app.models.enums import NotificationStatus
from app.schemas.book import BookBrief
from app.schemas.inbox import Inbox, InboxItem

KEEP = timedelta(days=60)
LIMIT = 30


def _visible(user: User, now: datetime) -> list[ColumnElement[bool]]:
    return [
        Notification.user_id == user.id,
        Notification.status != NotificationStatus.EXPIRED,
        Notification.created_at > now - KEEP,
    ]


async def inbox(session: AsyncSession, user: User, now: datetime | None = None) -> Inbox:
    now = now or datetime.now(UTC)
    rows = (
        await session.execute(
            select(Notification, Order.number, Book)
            .outerjoin(Order, Order.id == Notification.order_id)
            .outerjoin(Book, Book.id == Notification.book_id)
            .where(*_visible(user, now))
            .order_by(Notification.created_at.desc(), Notification.id)
            .limit(LIMIT)
        )
    ).all()
    unread = await session.scalar(
        select(func.count()).where(*_visible(user, now), Notification.read_at.is_(None))
    )
    return Inbox(
        items=[
            InboxItem(
                id=notification.id,
                kind=notification.kind,
                created_at=notification.created_at,
                read=notification.read_at is not None,
                order_id=notification.order_id,
                order_number=number,
                book=BookBrief.model_validate(book) if book is not None else None,
            )
            for notification, number, book in rows
        ],
        unread=int(unread or 0),
    )


async def mark_read(session: AsyncSession, user: User, ids: list[uuid.UUID] | None = None) -> None:
    stmt = (
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=func.now())
    )
    if ids is not None:
        stmt = stmt.where(Notification.id.in_(ids))
    await session.execute(stmt)
    await session.commit()
