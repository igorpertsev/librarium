from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now, uuid_pk


class RefreshToken(Base):
    """Server-side state of an opaque refresh token. Only a SHA-256 hash is stored.

    Tokens issued by successive rotations share a ``family_id``. Presenting a token that was
    already rotated or revoked is treated as theft and revokes the whole family.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), index=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    replaced_by_token_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
    user_agent: Mapped[str | None] = mapped_column(sa.String(512))
    ip_address: Mapped[str | None] = mapped_column(sa.String(45))
