from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now, uuid_pk


class Stocktake(Base):
    """A count of the books on the shelves (see ``app.services.stocktaking``). Only one can be
    open at a time."""

    __tablename__ = "stocktakes"
    __table_args__ = (
        sa.Index(
            "uq_stocktakes_one_open",
            sa.text("(finished_at IS NULL)"),
            unique=True,
            postgresql_where=sa.text("finished_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    started_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    # Copies marked not available because they were not found (when finishing).
    marked_missing: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")


class StocktakeCount(Base):
    """How many copies of a title were found, or how often an unknown ISBN was scanned."""

    __tablename__ = "stocktake_counts"
    __table_args__ = (
        sa.CheckConstraint("counted >= 0", name="counted_non_negative"),
        sa.CheckConstraint("(group_id IS NULL) <> (isbn IS NULL)", name="title_or_unknown_isbn"),
        sa.UniqueConstraint("stocktake_id", "group_id"),
        sa.UniqueConstraint("stocktake_id", "isbn"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    stocktake_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("stocktakes.id", ondelete="CASCADE"), index=True
    )
    # The title (copy group key, COALESCE(copy_group_id, id)); NULL for an unknown ISBN.
    group_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)
    isbn: Mapped[str | None] = mapped_column(sa.String(20))
    counted: Mapped[int] = mapped_column(sa.Integer, default=0, server_default="0")
