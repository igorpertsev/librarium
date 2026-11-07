from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now, uuid_pk


class UserIdentity(Base):
    """An outside sign-in (Google, Apple) linked to an account (see app.services.oauth)."""

    __tablename__ = "user_identities"
    __table_args__ = (sa.UniqueConstraint("provider", "subject"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    provider: Mapped[str] = mapped_column(sa.String(20))
    # The provider's stable id for the person ("sub" in the ID token).
    subject: Mapped[str] = mapped_column(sa.String(255))
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(sa.String(320))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
