from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

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


class ForgotPasswordRequest(RequestModel):
    email: NormalizedEmail


class ResetPasswordRequest(RequestModel):
    token: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    new_password: Password


class TokenResponse(ApiModel):
    """The refresh token is never part of a JSON body: it travels in an HttpOnly cookie."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth2 token type, not a secret
    expires_in: int
    user: UserRead


class LoginMfaRequest(RequestModel):
    mfa_token: Annotated[str, StringConstraints(min_length=20, max_length=2000)]
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=20)]


class MfaSetupRequest(RequestModel):
    password: AnyPassword


class MfaSetup(ApiModel):
    secret: str = Field(description="For typing into the app when the QR code cannot be scanned")
    otpauth_uri: str = Field(description="otpauth:// link to show as a QR code")


class MfaEnableRequest(RequestModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=8)]


class MfaRecoveryCodes(ApiModel):
    recovery_codes: list[str] = Field(description="Each works once; shown only now")
