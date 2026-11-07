from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, str_enum, uuid_pk
from app.models.enums import ReservationStatus


class AdvanceReservation(TimestampMixin, Base):
    """A copy reserved for a reader from ``starts_on``.

    From one loan period before that date the copy is kept for the reader (nobody else can
    borrow it); on the date it is held for them like a returned book (``book_holds``).
    """

    __tablename__ = "advance_reservations"
    __table_args__ = (
        sa.Index(
            "ix_advance_reservations_active_book",
            "book_id",
            "starts_on",
            postgresql_where=sa.text("status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    book_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("books.id", ondelete="CASCADE"))
    starts_on: Mapped[date] = mapped_column(sa.Date)
    status: Mapped[ReservationStatus] = mapped_column(
        str_enum(ReservationStatus, "reservation_status"),
        default=ReservationStatus.ACTIVE,
        server_default=ReservationStatus.ACTIVE.value,
    )
