from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now, uuid_pk


class ReadingLogEntry(Base):
    """A title the reader has finished, and when ("I've read it"); badges are counted from
    these (see ``app.services.reading_log``). Per title, like the reading list."""

    __tablename__ = "reading_log_entries"
    # One entry per profile and copy: the reader themselves (child_id NULL) or one child.
    __table_args__ = (
        sa.UniqueConstraint(
            "user_id",
            "child_id",
            "book_id",
            name="uq_reading_log_entries_profile_book",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    # Whose reading: a child of the account, or the reader (NULL).
    child_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("child_profiles.id", ondelete="CASCADE"), index=True
    )
    finished_on: Mapped[date] = mapped_column(sa.Date)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
