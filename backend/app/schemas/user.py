from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import ClassVar

from pydantic import Field, model_validator

from app.models.enums import ContactMethod, UiLanguage, UserRole
from app.schemas.common import ApiModel, Page, PatchModel, RequestModel
from app.schemas.types import FullName, Handle, NormalizedEmail, PhoneLike

CONTACT_FIELDS: tuple[str, ...] = ("whatsapp", "telegram", "instagram", "phone")


def ensure_preferred_contact_has_value(
    preferred: ContactMethod | None, values: dict[str, str | None]
) -> None:
    """The preferred method must point to a filled-in contact (email is always present)."""
    if preferred is None or preferred is ContactMethod.EMAIL:
        return
    if not values.get(preferred.value):
        raise ValueError(f"preferred_contact_method is '{preferred.value}' but it is empty")


class UserRead(ApiModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    whatsapp: str | None
    telegram: str | None
    instagram: str | None
    phone: str | None
    preferred_contact_method: ContactMethod | None
    preferred_language: UiLanguage | None
    created_at: datetime
    updated_at: datetime


class UserUpdate(PatchModel):
    """``PATCH /users/me``. Omitted fields are untouched; ``null`` clears a contact."""

    non_nullable_fields: ClassVar[frozenset[str]] = frozenset({"full_name", "email"})

    full_name: FullName | None = None
    email: NormalizedEmail | None = None
    whatsapp: PhoneLike = None
    telegram: Handle = None
    instagram: Handle = None
    phone: PhoneLike = None
    preferred_contact_method: ContactMethod | None = None
    preferred_language: UiLanguage | None = None


class ActiveLoan(ApiModel):
    """A book currently handed over to a customer (order status ``confirmed``)."""

    order_id: uuid.UUID
    book_id: uuid.UUID
    title: str
    author: str
    cover_url: str | None
    borrowed_at: datetime | None
    due_date: date


class AdminUserRead(UserRead):
    active_loans: list[ActiveLoan]


class AdminUserUpdate(PatchModel):
    non_nullable_fields: ClassVar[frozenset[str]] = frozenset({"role", "is_active"})

    role: UserRole | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> AdminUserUpdate:
        if not self.model_fields_set:
            raise ValueError("Provide at least one of: role, is_active")
        return self


class AdminUserPage(Page[AdminUserRead]):
    pass


class DeleteAccountRequest(RequestModel):
    password: str = Field(min_length=1, max_length=128, description="The current password")
