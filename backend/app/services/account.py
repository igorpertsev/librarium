"""A reader's own data: download everything stored about them, or delete the account.

Deleting keeps the orders (the library's lending records) but strips them of the reader's
name and contacts, and anonymises the user row instead of removing it, because orders
reference it. Everything else that is personal (sessions, cart, waiting list, reading list,
reviews, holds, reservations, email queue) is deleted; held or set-aside copies go to the next
reader in line.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BadRequestError, ConflictError
from app.core.security import hash_password, verify_password
from app.models import (
    AdvanceReservation,
    Book,
    BookHold,
    Cart,
    Notification,
    Order,
    PurchaseRequest,
    PurchaseVote,
    ReadingListEntry,
    ReadingLogEntry,
    RefreshToken,
    Review,
    User,
    WaitlistEntry,
)
from app.models.enums import ACTIVE_ORDER_STATUSES, UserRole
from app.services import waitlist

DELETED_NAME = "Deleted user"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def export_data(session: AsyncSession, user: User) -> dict[str, Any]:
    orders = (
        await session.scalars(
            select(Order)
            .where(Order.user_id == user.id)
            .options(selectinload(Order.items))
            .order_by(Order.created_at)
        )
    ).all()
    waiting = (
        await session.execute(
            select(Book.title, Book.author, WaitlistEntry.created_at)
            .join(Book, Book.id == WaitlistEntry.book_id)
            .where(WaitlistEntry.user_id == user.id)
        )
    ).all()
    saved = (
        await session.execute(
            select(Book.title, Book.author, ReadingListEntry.created_at)
            .join(Book, Book.id == ReadingListEntry.book_id)
            .where(ReadingListEntry.user_id == user.id)
        )
    ).all()
    suggested = (
        await session.execute(
            select(PurchaseRequest.title, PurchaseRequest.author, PurchaseRequest.status)
            .join(PurchaseVote, PurchaseVote.request_id == PurchaseRequest.id)
            .where(PurchaseVote.user_id == user.id)
        )
    ).all()
    finished = (
        await session.execute(
            select(Book.title, Book.author, ReadingLogEntry.finished_on)
            .join(Book, Book.id == ReadingLogEntry.book_id)
            .where(ReadingLogEntry.user_id == user.id)
            .order_by(ReadingLogEntry.finished_on)
        )
    ).all()
    reserved = (
        await session.execute(
            select(Book.title, Book.author, AdvanceReservation.starts_on, AdvanceReservation.status)
            .join(Book, Book.id == AdvanceReservation.book_id)
            .where(AdvanceReservation.user_id == user.id)
            .order_by(AdvanceReservation.starts_on)
        )
    ).all()
    reviews = (
        await session.execute(
            select(Book.title, Review.rating, Review.text, Review.status, Review.created_at)
            .join(Book, Book.id == Review.book_id)
            .where(Review.user_id == user.id)
        )
    ).all()
    emails = (
        await session.scalars(select(Notification).where(Notification.user_id == user.id))
    ).all()
    sessions = (
        await session.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id))
    ).all()
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "profile": {
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value,
            "registered_at": _iso(user.created_at),
            "whatsapp": user.whatsapp,
            "telegram": user.telegram,
            "instagram": user.instagram,
            "phone": user.phone,
            "preferred_contact_method": (
                user.preferred_contact_method.value if user.preferred_contact_method else None
            ),
            "preferred_language": user.preferred_language.value
            if user.preferred_language
            else None,
        },
        "orders": [
            {
                "number": order.number,
                "status": order.status.value,
                "requested_at": _iso(order.created_at),
                "confirmed_at": _iso(order.confirmed_at),
                "returned_at": _iso(order.returned_at),
                "cancelled_at": _iso(order.cancelled_at),
                "due_date": order.due_date.isoformat(),
                "renewals": order.renewal_count,
                "total": f"{order.total_amount} {order.currency}",
                "books": [
                    {"title": item.title, "author": item.author, "isbn": item.isbn}
                    for item in order.items
                ],
            }
            for order in orders
        ],
        "waiting_list": [
            {"title": title, "author": author, "since": _iso(since)}
            for title, author, since in waiting
        ],
        "want_to_read": [
            {"title": title, "author": author, "since": _iso(since)}
            for title, author, since in saved
        ],
        "purchase_votes": [
            {"title": title, "author": author, "status": purchase_status.value}
            for title, author, purchase_status in suggested
        ],
        "reading_log": [
            {"title": title, "author": author, "finished_on": day.isoformat()}
            for title, author, day in finished
        ],
        "reservations": [
            {
                "title": title,
                "author": author,
                "from": starts_on.isoformat(),
                "status": reservation_status.value,
            }
            for title, author, starts_on, reservation_status in reserved
        ],
        "reviews": [
            {
                "title": title,
                "rating": rating,
                "text": text,
                "status": review_status.value,
                "written_at": _iso(written),
            }
            for title, rating, text, review_status, written in reviews
        ],
        "emails": [
            {
                "kind": email.kind.value,
                "status": email.status.value,
                "subject": email.subject,
                "queued_at": _iso(email.created_at),
                "sent_at": _iso(email.sent_at),
            }
            for email in emails
        ],
        "sessions": [
            {
                "signed_in_at": _iso(token.created_at),
                "expires_at": _iso(token.expires_at),
                "revoked_at": _iso(token.revoked_at),
                "browser": token.user_agent,
                "ip_address": token.ip_address,
            }
            for token in sessions
        ],
    }


async def delete_account(session: AsyncSession, user: User, password: str) -> None:
    if not await verify_password(user.password_hash, password):
        raise BadRequestError("Current password is incorrect", code="INVALID_CURRENT_PASSWORD")
    if user.role is not UserRole.CUSTOMER:
        raise ConflictError(
            "Library staff cannot delete their own account; ask an administrator",
            code="ADMIN_ACCOUNT",
        )
    active = await session.scalar(
        select(Order.id)
        .where(Order.user_id == user.id, Order.status.in_(ACTIVE_ORDER_STATUSES))
        .limit(1)
    )
    if active is not None:
        raise ConflictError(
            "Return or cancel your current orders before deleting the account",
            code="ACTIVE_ORDERS",
        )

    anonymous_email = f"deleted-{user.id}@deleted.invalid"
    await session.execute(
        update(Order)
        .where(Order.user_id == user.id)
        .values(
            contact_name=DELETED_NAME,
            contact_email=anonymous_email,
            contact_whatsapp=None,
            contact_telegram=None,
            contact_instagram=None,
            contact_phone=None,
            contact_preferred_method=None,
        )
    )
    released = (
        await session.scalars(
            delete(BookHold).where(BookHold.user_id == user.id).returning(BookHold.book_id)
        )
    ).all()
    set_aside = (
        await session.scalars(
            delete(AdvanceReservation)
            .where(AdvanceReservation.user_id == user.id)
            .returning(AdvanceReservation.book_id)
        )
    ).all()
    await session.execute(
        update(PurchaseRequest)
        .where(PurchaseRequest.created_by_id == user.id)
        .values(created_by_id=None)
    )
    personal = (
        PurchaseVote,
        RefreshToken,
        Notification,
        WaitlistEntry,
        ReadingListEntry,
        ReadingLogEntry,
        Review,
        Cart,
    )
    for table in personal:
        await session.execute(delete(table).where(table.user_id == user.id))
    await waitlist.notify_waiting_readers(session, [*released, *set_aside])
    user.email = anonymous_email
    user.full_name = DELETED_NAME
    user.whatsapp = user.telegram = user.instagram = user.phone = None
    user.preferred_contact_method = None
    user.preferred_language = None
    user.password_hash = await hash_password(secrets.token_urlsafe(32))  # nobody knows it
    user.is_active = False
    await session.commit()
