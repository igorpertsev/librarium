from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class PickupPoint(TimestampMixin, Base):
    """A place where readers collect their orders, in time slots within its weekly hours
    (see ``app.services.pickup``)."""

    __tablename__ = "pickup_points"
    __table_args__ = (
        sa.CheckConstraint("slot_minutes BETWEEN 15 AND 240", name="slot_minutes_range"),
        sa.CheckConstraint(
            "slot_capacity IS NULL OR slot_capacity BETWEEN 1 AND 100", name="slot_capacity_range"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(sa.String(120))
    address: Mapped[str] = mapped_column(sa.String(255))
    notes: Mapped[str | None] = mapped_column(sa.String(500))
    # Weekly opening hours: [{"weekday": 0 (Monday) .. 6, "opens": "10:00:00", "closes": ...}],
    # in the library's time zone (library_settings.timezone).
    hours: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=sa.text("'[]'::jsonb")
    )
    slot_minutes: Mapped[int] = mapped_column(sa.SmallInteger, default=60, server_default="60")
    # Orders per slot (NULL: no limit).
    slot_capacity: Mapped[int | None] = mapped_column(sa.SmallInteger)
    active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
