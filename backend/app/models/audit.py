from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now, uuid_pk


class AuditEvent(Base):
    """A change made through the staff API: who, which endpoint, which record, what was sent
    (secrets redacted). Written after the change succeeded (see ``app.services.audit``)."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Kept when the account is deleted later; the email is a snapshot.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actor_email: Mapped[str] = mapped_column(sa.String(320))
    action: Mapped[str] = mapped_column(sa.String(100), index=True)
    method: Mapped[str] = mapped_column(sa.String(10))
    path: Mapped[str] = mapped_column(sa.String(300))
    entity_type: Mapped[str | None] = mapped_column(sa.String(40))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now(), index=True
    )
