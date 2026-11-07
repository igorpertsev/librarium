from __future__ import annotations

import uuid
from collections import defaultdict
from http import HTTPStatus

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models import Order, OrderItem, User
from app.models.enums import OrderStatus
from app.repositories.books import escape_like
from app.repositories.users import get_user_by_email
from app.schemas.user import (
    CONTACT_FIELDS,
    ActiveLoan,
    AdminUserRead,
    AdminUserUpdate,
    UserRead,
    UserUpdate,
    ensure_preferred_contact_has_value,
)
from app.services import mfa
from app.services.auth import email_taken_error, revoke_user_tokens


async def update_profile(session: AsyncSession, user: User, patch: UserUpdate) -> User:
    changes = patch.changes()
    new_email = changes.get("email")
    if new_email is not None and new_email != user.email:
        existing = await get_user_by_email(session, new_email)
        if existing is not None and existing.id != user.id:
            raise email_taken_error()

    for field, value in changes.items():
        setattr(user, field, value)

    try:
        ensure_preferred_contact_has_value(
            user.preferred_contact_method, {name: getattr(user, name) for name in CONTACT_FIELDS}
        )
    except ValueError as exc:
        raise AppError(
            str(exc), code="VALIDATION_ERROR", status_code=HTTPStatus.UNPROCESSABLE_ENTITY
        ) from exc

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise email_taken_error() from exc
    return user


async def list_users_with_loans(
    session: AsyncSession, *, q: str | None, page: int, page_size: int
) -> tuple[list[AdminUserRead], int]:
    conditions = []
    if q:
        pattern = f"%{escape_like(q)}%"
        conditions.append(
            or_(User.email.ilike(pattern, escape="\\"), User.full_name.ilike(pattern, escape="\\"))
        )
    total = await session.scalar(select(func.count()).select_from(User).where(*conditions))
    users = list(
        (
            await session.scalars(
                select(User)
                .where(*conditions)
                .order_by(User.created_at.asc(), User.id)
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).all()
    )

    loans: dict[uuid.UUID, list[ActiveLoan]] = defaultdict(list)
    if users:
        # One query for the whole page (no N+1): books handed over and not yet returned.
        rows = await session.execute(
            select(
                Order.user_id,
                Order.id,
                Order.confirmed_at,
                Order.due_date,
                OrderItem.book_id,
                OrderItem.title,
                OrderItem.author,
                OrderItem.cover_url,
            )
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(
                Order.user_id.in_([u.id for u in users]),
                Order.status == OrderStatus.CONFIRMED,
            )
            .order_by(Order.due_date, OrderItem.position)
        )
        for row in rows:
            loans[row.user_id].append(
                ActiveLoan(
                    order_id=row.id,
                    book_id=row.book_id,
                    title=row.title,
                    author=row.author,
                    cover_url=row.cover_url,
                    borrowed_at=row.confirmed_at,
                    due_date=row.due_date,
                )
            )

    items = [
        AdminUserRead(
            **UserRead.model_validate(user).model_dump(), active_loans=loans.get(user.id, [])
        )
        for user in users
    ]
    return items, int(total or 0)


async def admin_update_user(
    session: AsyncSession, admin: User, user_id: uuid.UUID, patch: AdminUserUpdate
) -> User:
    target = await session.get(User, user_id, with_for_update=True)
    if target is None:
        raise NotFoundError("User not found", code="USER_NOT_FOUND")
    changes = patch.changes()
    if changes.pop("reset_mfa", False):
        mfa.reset(target)
    if target.id == admin.id and (
        ("role" in changes and changes["role"] != admin.role)
        or ("is_active" in changes and changes["is_active"] is False)
    ):
        raise ConflictError(
            "You cannot demote or disable your own account", code="CANNOT_MODIFY_SELF"
        )

    for field, value in changes.items():
        setattr(target, field, value)
    if changes.get("is_active") is False:
        await revoke_user_tokens(session, target.id)
    await session.commit()
    return target
