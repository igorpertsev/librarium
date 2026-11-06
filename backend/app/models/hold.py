from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now


class BookHold(Base):
    """A returned copy kept for the reader who has waited longest for its title, until
    ``held_until``; nobody else can borrow it meanwhile (see ``app.services.holds``)."""

    __tablename__ = "book_holds"

    book_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("books.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    held_until: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
