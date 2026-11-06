"""A reader's own data: download everything stored about them, or delete the account.

Deleting keeps the orders (the library's lending records) but strips them of the reader's
name and contacts, and anonymises the user row instead of removing it, because orders
reference it. Everything else that is personal (sessions, cart, waiting list, reading list,
email queue) is deleted.
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
    Book,
    Cart,
    Notification,
    Order,
    ReadingListEntry,
    RefreshToken,
    User,
    WaitlistEntry,
)
from app.models.enums import ACTIVE_ORDER_STATUSES, UserRole

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
    if user.role is UserRole.ADMIN:
        raise ConflictError(
            "Administrators cannot delete their own account; ask another administrator",
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
    for table in (RefreshToken, Notification, WaitlistEntry, ReadingListEntry, Cart):
        await session.execute(delete(table).where(table.user_id == user.id))
    user.email = anonymous_email
    user.full_name = DELETED_NAME
    user.whatsapp = user.telegram = user.instagram = user.phone = None
    user.preferred_contact_method = None
    user.preferred_language = None
    user.password_hash = await hash_password(secrets.token_urlsafe(32))  # nobody knows it
    user.is_active = False
    await session.commit()
