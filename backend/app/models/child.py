from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now, uuid_pk


class ChildProfile(Base):
    """A child in a family account: borrows through the parent's account and keeps their
    own reading log and badges (see app.services.family)."""

    __tablename__ = "child_profiles"
    __table_args__ = (
        sa.CheckConstraint(
            "birth_year IS NULL OR birth_year BETWEEN 1990 AND 2100", name="birth_year_range"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    parent_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(sa.String(100))
    birth_year: Mapped[int | None] = mapped_column(sa.SmallInteger)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
