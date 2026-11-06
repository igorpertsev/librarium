"""Pickup points and time slots.

A pickup point is open at weekly hours in the library's time zone; every opening period is
cut into slots of ``slot_minutes``. Readers choose a slot from now + ``MIN_NOTICE`` up to
``SLOT_DAYS`` ahead when they place an order; with ``slot_capacity`` set, a slot takes that
many orders (cancelled ones do not count). While the library has an active pickup point, a
new order must name one.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models import Order, PickupPoint
from app.models.enums import OrderStatus
from app.schemas.pickup import OpeningHours, PickupChoice, PickupPointCreate, PickupPointUpdate
from app.services.library_settings import get_library_settings

SLOT_DAYS = 14
MIN_NOTICE = timedelta(hours=1)


@dataclass(frozen=True)
class Slot:
    starts_at: datetime
    ends_at: datetime
    left: int | None


def _hours(point: PickupPoint) -> list[OpeningHours]:
    return [OpeningHours.model_validate(item) for item in point.hours]


def slot_starts(point: PickupPoint, zone: ZoneInfo, now: datetime) -> Iterator[datetime]:
    """Start of every slot from ``now + MIN_NOTICE`` to ``SLOT_DAYS`` ahead, in order (UTC)."""
    earliest = now + MIN_NOTICE
    length = timedelta(minutes=point.slot_minutes)
    hours = sorted(_hours(point), key=lambda h: h.opens)
    today = now.astimezone(zone).date()
    for offset in range(SLOT_DAYS + 1):
        day = today + timedelta(days=offset)
        for period in (h for h in hours if h.weekday == day.weekday()):
            start = datetime.combine(day, period.opens, zone)
            closes = datetime.combine(day, period.closes, zone)
            while start + length <= closes:
                if start >= earliest:
                    yield start.astimezone(UTC)
                start += length


async def _zone(session: AsyncSession) -> ZoneInfo:
    return ZoneInfo((await get_library_settings(session)).timezone)


async def _taken(
    session: AsyncSession, point_id: uuid.UUID, starts: list[datetime]
) -> dict[datetime, int]:
    if not starts:
        return {}
    rows = await session.execute(
        select(Order.pickup_at, func.count())
        .where(
            Order.pickup_point_id == point_id,
            Order.pickup_at.in_(starts),
            Order.status != OrderStatus.CANCELLED,
        )
        .group_by(Order.pickup_at)
    )
    return {at: count for at, count in rows if at is not None}


async def list_active(session: AsyncSession) -> list[PickupPoint]:
    return list(
        (
            await session.scalars(
                select(PickupPoint).where(PickupPoint.active).order_by(PickupPoint.name)
            )
        ).all()
    )


async def slots(
    session: AsyncSession, point_id: uuid.UUID, *, now: datetime | None = None
) -> list[Slot]:
    point = await session.get(PickupPoint, point_id)
    if point is None or not point.active:
        raise NotFoundError("Pickup point not found", code="PICKUP_POINT_NOT_FOUND")
    starts = list(slot_starts(point, await _zone(session), now or datetime.now(UTC)))
    taken = await _taken(session, point.id, starts) if point.slot_capacity else {}
    length = timedelta(minutes=point.slot_minutes)
    return [
        Slot(
            starts_at=start,
            ends_at=start + length,
            left=None
            if point.slot_capacity is None
            else max(point.slot_capacity - taken.get(start, 0), 0),
        )
        for start in starts
    ]


async def choose(
    session: AsyncSession, choice: PickupChoice | None, *, now: datetime | None = None
) -> tuple[PickupPoint | None, datetime | None]:
    """Check the reader's pickup point and slot for a new order (call inside its transaction).

    The point's row is locked so two checkouts cannot both take the last place in a slot.
    """
    if choice is None or choice.pickup_point_id is None:
        if await session.scalar(select(PickupPoint.id).where(PickupPoint.active).limit(1)):
            raise BadRequestError("Choose where and when to pick up", code="PICKUP_REQUIRED")
        return None, None
    point = await session.scalar(
        select(PickupPoint)
        .where(PickupPoint.id == choice.pickup_point_id, PickupPoint.active)
        .with_for_update()
    )
    if point is None:
        raise NotFoundError("Pickup point not found", code="PICKUP_POINT_NOT_FOUND")
    at = choice.pickup_at
    if at is None or at.tzinfo is None:
        raise BadRequestError("Choose a pickup time", code="INVALID_PICKUP_SLOT")
    at = at.astimezone(UTC)
    zone = await _zone(session)
    if at not in set(slot_starts(point, zone, now or datetime.now(UTC))):
        raise BadRequestError("That pickup time is not available", code="INVALID_PICKUP_SLOT")
    if point.slot_capacity is not None:
        taken = (await _taken(session, point.id, [at])).get(at, 0)
        if taken >= point.slot_capacity:
            raise ConflictError("That pickup time is fully booked", code="PICKUP_SLOT_FULL")
    return point, at


# --- Administration ----------------------------------------------------------------------


async def list_all(session: AsyncSession) -> list[PickupPoint]:
    stmt = select(PickupPoint).order_by(PickupPoint.active.desc(), PickupPoint.name)
    return list((await session.scalars(stmt)).all())


def _stored_hours(hours: list[OpeningHours]) -> list[dict[str, object]]:
    ordered = sorted(hours, key=lambda h: (h.weekday, h.opens))
    return [h.model_dump(mode="json") for h in ordered]


async def create(session: AsyncSession, body: PickupPointCreate) -> PickupPoint:
    values = body.model_dump()
    values["hours"] = _stored_hours(body.hours)
    point = PickupPoint(**values)
    session.add(point)
    await session.commit()
    await session.refresh(point)
    return point


async def update(
    session: AsyncSession, point_id: uuid.UUID, body: PickupPointUpdate
) -> PickupPoint:
    point = await session.get(PickupPoint, point_id, with_for_update=True)
    if point is None:
        raise NotFoundError("Pickup point not found", code="PICKUP_POINT_NOT_FOUND")
    changes = body.changes()
    if body.hours is not None:
        changes["hours"] = _stored_hours(body.hours)
    for field, value in changes.items():
        setattr(point, field, value)
    await session.commit()
    await session.refresh(point)
    return point


async def delete(session: AsyncSession, point_id: uuid.UUID) -> None:
    point = await session.get(PickupPoint, point_id)
    if point is None:
        raise NotFoundError("Pickup point not found", code="PICKUP_POINT_NOT_FOUND")
    if await session.scalar(select(Order.id).where(Order.pickup_point_id == point_id).limit(1)):
        raise ConflictError(
            "Orders use this pickup point; switch it off instead", code="PICKUP_POINT_IN_USE"
        )
    await session.delete(point)
    await session.commit()
