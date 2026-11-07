from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now, uuid_pk


class PushSubscription(Base):
    """A browser or installed app that receives Web Push notifications for a reader
    (see app.services.web_push). The endpoint belongs to the browser's push service."""

    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(sa.String(2048), unique=True)
    p256dh: Mapped[str] = mapped_column(sa.String(200))  # the browser's public key
    auth: Mapped[str] = mapped_column(sa.String(100))  # its authentication secret
    user_agent: Mapped[str | None] = mapped_column(sa.String(300))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
    last_sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
