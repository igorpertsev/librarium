from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, str_enum, utc_now, uuid_pk
from app.models.enums import NotificationKind, NotificationStatus


class Notification(Base):
    """Outbox of customer emails.

    Rows are written in the same transaction as the order change that triggers them, so a
    notification is never lost or sent for a change that was rolled back. A background job
    renders and delivers them (see ``app.services.notifications``). ``UNIQUE(order_id, kind)``
    makes every event, including reminders, happen at most once per order.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        sa.UniqueConstraint("order_id", "kind"),
        sa.Index("ix_notifications_status_next_attempt", "status", "next_attempt_at"),
        sa.Index("ix_notifications_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("orders.id", ondelete="CASCADE")
    )
    # For book_available: the book that is back (order_id is NULL then).
    book_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("books.id", ondelete="CASCADE"))
    kind: Mapped[NotificationKind] = mapped_column(str_enum(NotificationKind, "notification_kind"))
    status: Mapped[NotificationStatus] = mapped_column(
        str_enum(NotificationStatus, "notification_status"),
        default=NotificationStatus.PENDING,
        server_default=NotificationStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(sa.SmallInteger, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
    last_error: Mapped[str | None] = mapped_column(sa.String(500))
    # Filled in when the message is rendered and sent (kept for auditing).
    recipient: Mapped[str | None] = mapped_column(sa.String(320))
    subject: Mapped[str | None] = mapped_column(sa.String(300))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    # Also sent to the reader's Telegram chat (once, even when the email is retried).
    telegram_sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    # When the reader saw it in the app's notification list (NULL: unread).
    read_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
