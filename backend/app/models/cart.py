from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utc_now, uuid_pk
from app.models.book import Book


class Cart(TimestampMixin, Base):
    """The single, persistent cart of a user (``user_id`` is unique)."""

    __tablename__ = "carts"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        sa.UniqueConstraint("cart_id", "book_id"),
        sa.Index("ix_cart_items_cart_added", "cart_id", "added_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    cart_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("carts.id", ondelete="CASCADE"))
    book_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    added_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )

    # lazy="raise" turns accidental lazy loads (fatal under asyncio) into immediate errors.
    book: Mapped[Book] = relationship(lazy="raise")
