from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now, uuid_pk


class Passkey(Base):
    """A WebAuthn credential (passkey) a user signs in with (see app.services.passkeys)."""

    __tablename__ = "passkeys"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    credential_id: Mapped[bytes] = mapped_column(sa.LargeBinary, unique=True)
    public_key: Mapped[bytes] = mapped_column(sa.LargeBinary)  # COSE key
    sign_count: Mapped[int] = mapped_column(sa.BigInteger, default=0, server_default="0")
    transports: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=sa.text("'[]'::jsonb")
    )
    name: Mapped[str] = mapped_column(sa.String(100))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
