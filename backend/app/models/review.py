from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, str_enum, uuid_pk
from app.models.enums import ReviewStatus


class Review(TimestampMixin, Base):
    """A reader's rating (1-5) of a title they borrowed, with an optional short review.

    One per reader and title: the entry names one copy, any copy of the title counts.
    """

    __tablename__ = "reviews"
    __table_args__ = (
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        sa.UniqueConstraint("user_id", "book_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[int] = mapped_column(sa.SmallInteger)
    text: Mapped[str] = mapped_column(sa.Text, default="", server_default="")
    status: Mapped[ReviewStatus] = mapped_column(
        str_enum(ReviewStatus, "review_status"), index=True
    )
    moderated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
