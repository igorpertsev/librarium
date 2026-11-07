from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, str_enum, utc_now, uuid_pk
from app.models.enums import BookCategory


class Challenge(Base):
    """A reading challenge set by the library ("10 books this summer"): readers and their
    children join, and books they log as read in its dates count (see app.services.challenges)."""

    __tablename__ = "challenges"
    __table_args__ = (
        sa.CheckConstraint("ends_on >= starts_on", name="dates_in_order"),
        sa.CheckConstraint("goal BETWEEN 1 AND 100", name="goal_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name_en: Mapped[str] = mapped_column(sa.String(200))
    name_ru: Mapped[str | None] = mapped_column(sa.String(200))
    description_en: Mapped[str] = mapped_column(sa.Text, default="", server_default="")
    description_ru: Mapped[str | None] = mapped_column(sa.Text)
    starts_on: Mapped[date] = mapped_column(sa.Date)
    ends_on: Mapped[date] = mapped_column(sa.Date, index=True)
    goal: Mapped[int] = mapped_column(sa.SmallInteger)
    # Only books of this category count (NULL: any book).
    category: Mapped[BookCategory | None] = mapped_column(str_enum(BookCategory, "book_category"))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )


class ChallengeEntry(Base):
    """A reader (or one of their children) taking part in a challenge."""

    __tablename__ = "challenge_entries"
    __table_args__ = (
        sa.UniqueConstraint(
            "challenge_id",
            "user_id",
            "child_id",
            name="uq_challenge_entries_profile",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("challenges.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    child_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("child_profiles.id", ondelete="CASCADE")
    )
    joined_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
