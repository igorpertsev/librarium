from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from app.models.enums import ContactMethod, UiLanguage
from app.schemas.common import ApiModel, RequestModel
from app.schemas.types import (
    AnyPassword,
    FullName,
    Handle,
    LoginEmail,
    NormalizedEmail,
    Password,
    PhoneLike,
)
from app.schemas.user import CONTACT_FIELDS, UserRead, ensure_preferred_contact_has_value


class RegisterRequest(RequestModel):
    email: NormalizedEmail
    password: Password
    full_name: FullName
    whatsapp: PhoneLike = None
    telegram: Handle = None
    instagram: Handle = None
    phone: PhoneLike = None
    preferred_contact_method: ContactMethod | None = None
    # Interface language at sign-up; used for emails.
    preferred_language: UiLanguage | None = None

    @model_validator(mode="after")
    def _validate_contacts(self) -> RegisterRequest:
        values = {name: getattr(self, name) for name in CONTACT_FIELDS}
        # Mirrors the registration form: at least one way to reach the customer.
        if not any(values.values()):
            raise ValueError(
                "Provide at least one contact method: whatsapp, telegram, instagram or phone"
            )
        ensure_preferred_contact_has_value(self.preferred_contact_method, values)
        return self


class LoginRequest(RequestModel):
    email: LoginEmail
    password: AnyPassword


class ChangePasswordRequest(RequestModel):
    current_password: AnyPassword
    new_password: Password


class TokenResponse(ApiModel):
    """The refresh token is never part of a JSON body: it travels in an HttpOnly cookie."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth2 token type, not a secret
    expires_in: int
    user: UserRead
