"""Family accounts: a parent's account with child profiles.

Children borrow through the parent's account (the parent is responsible for the loans) and
keep their own reading log and badges. An order can say which child it is for.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models import ChildProfile, User

MAX_CHILDREN = 6


async def list_children(session: AsyncSession, user: User) -> list[ChildProfile]:
    return list(
        (
            await session.scalars(
                select(ChildProfile)
                .where(ChildProfile.parent_id == user.id)
                .order_by(ChildProfile.created_at, ChildProfile.id)
            )
        ).all()
    )


async def child_of(session: AsyncSession, user: User, child_id: uuid.UUID) -> ChildProfile:
    child = await session.get(ChildProfile, child_id)
    if child is None or child.parent_id != user.id:
        raise NotFoundError("Child profile not found", code="CHILD_NOT_FOUND")
    return child


async def add_child(
    session: AsyncSession, user: User, *, name: str, birth_year: int | None
) -> ChildProfile:
    count = await session.scalar(select(func.count()).where(ChildProfile.parent_id == user.id))
    if (count or 0) >= MAX_CHILDREN:
        raise ConflictError(
            f"A family can have up to {MAX_CHILDREN} children",
            code="TOO_MANY_CHILDREN",
            details={"limit": MAX_CHILDREN},
        )
    child = ChildProfile(id=uuid.uuid4(), parent_id=user.id, name=name, birth_year=birth_year)
    session.add(child)
    await session.commit()
    return child


async def update_child(
    session: AsyncSession, user: User, child_id: uuid.UUID, changes: dict[str, object]
) -> ChildProfile:
    child = await child_of(session, user, child_id)
    for field, value in changes.items():
        setattr(child, field, value)
    await session.commit()
    return child


async def remove_child(session: AsyncSession, user: User, child_id: uuid.UUID) -> None:
    """Their reading log goes with them; orders keep the name they were placed for."""
    child = await child_of(session, user, child_id)
    await session.delete(child)
    await session.commit()
