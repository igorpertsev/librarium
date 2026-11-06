from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now, uuid_pk


class ReadingListEntry(Base):
    """A title a reader wants to read some day ("Want to read"), separate from the cart.

    Like the waiting list it is per title: the entry names one copy, and any copy of the title
    (copy group) counts.
    """

    __tablename__ = "reading_list_entries"
    __table_args__ = (sa.UniqueConstraint("user_id", "book_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
