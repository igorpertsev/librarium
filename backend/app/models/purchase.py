from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, str_enum, utc_now, uuid_pk
from app.models.enums import PurchaseStatus


class PurchaseRequest(TimestampMixin, Base):
    """A book readers would like the library to buy (see ``app.services.purchases``)."""

    __tablename__ = "purchase_requests"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(sa.String(500))
    author: Mapped[str] = mapped_column(sa.String(300))
    isbn: Mapped[str | None] = mapped_column(sa.String(20))
    note: Mapped[str | None] = mapped_column(sa.String(500))
    status: Mapped[PurchaseStatus] = mapped_column(
        str_enum(PurchaseStatus, "purchase_status"),
        default=PurchaseStatus.OPEN,
        server_default=PurchaseStatus.OPEN.value,
        index=True,
    )
    librarian_note: Mapped[str | None] = mapped_column(sa.String(500))
    # The catalogue book, once added.
    book_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("books.id", ondelete="SET NULL")
    )


class PurchaseVote(Base):
    __tablename__ = "purchase_votes"

    request_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("purchase_requests.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
