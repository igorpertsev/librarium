from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now, uuid_pk
from app.models.book import Book


class WaitlistEntry(Base):
    """A customer waiting for a book that is out ("notify me when it is available").

    When the book becomes available again every waiting customer gets one email and the
    entry is removed (see ``app.services.waitlist``).
    """

    __tablename__ = "waitlist_entries"
    __table_args__ = (sa.UniqueConstraint("user_id", "book_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    book_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )

    book: Mapped[Book] = relationship(lazy="raise")
