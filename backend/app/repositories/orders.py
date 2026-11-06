from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Order, OrderItem
from app.models.enums import OrderStatus


def _with_items(stmt: Select[Order]) -> Select[Order]:
    # Two extra round-trips per page (items, then books), independent of the page size.
    return stmt.options(selectinload(Order.items).selectinload(OrderItem.book))


async def get_order(
    session: AsyncSession, order_id: uuid.UUID, *, user_id: uuid.UUID | None = None
) -> Order | None:
    stmt = select(Order).where(Order.id == order_id)
    if user_id is not None:
        stmt = stmt.where(Order.user_id == user_id)
    return await session.scalar(_with_items(stmt).execution_options(populate_existing=True))


async def lock_order(
    session: AsyncSession, order_id: uuid.UUID, *, user_id: uuid.UUID | None = None
) -> Order | None:
    stmt = select(Order).where(Order.id == order_id).with_for_update()
    if user_id is not None:
        stmt = stmt.where(Order.user_id == user_id)
    return await session.scalar(stmt)


async def list_orders(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    status: OrderStatus | None,
    page: int,
    page_size: int,
) -> tuple[list[Order], int]:
    conditions: list[ColumnElement[bool]] = []
    if user_id is not None:
        conditions.append(Order.user_id == user_id)
    if status is not None:
        conditions.append(Order.status == status)
    total = await session.scalar(select(func.count()).select_from(Order).where(*conditions))
    stmt = _with_items(
        select(Order)
        .where(*conditions)
        .order_by(Order.created_at.desc(), Order.id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return list((await session.scalars(stmt)).all()), int(total or 0)
