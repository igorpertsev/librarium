from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, str_enum, uuid_pk
from app.models.enums import ContactMethod, UiLanguage, UserRole


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Emails are normalised (trimmed, lower-cased) before storage; enforce it in the DB.
        sa.CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(sa.String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(sa.String(255))
    full_name: Mapped[str] = mapped_column(sa.String(200))
    role: Mapped[UserRole] = mapped_column(
        str_enum(UserRole, "user_role"),
        default=UserRole.CUSTOMER,
        server_default=UserRole.CUSTOMER.value,
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())

    whatsapp: Mapped[str | None] = mapped_column(sa.String(100))
    telegram: Mapped[str | None] = mapped_column(sa.String(100))
    instagram: Mapped[str | None] = mapped_column(sa.String(100))
    phone: Mapped[str | None] = mapped_column(sa.String(100))
    preferred_contact_method: Mapped[ContactMethod | None] = mapped_column(
        str_enum(ContactMethod, "contact_method")
    )
    # Interface language chosen by the user; emails use it (NULL: English and Russian).
    preferred_language: Mapped[UiLanguage | None] = mapped_column(
        str_enum(UiLanguage, "ui_language")
    )

    def contact_value(self, method: ContactMethod | None) -> str | None:
        if method is None:
            return None
        if method is ContactMethod.EMAIL:
            return self.email
        value: str | None = getattr(self, method.value)
        return value
