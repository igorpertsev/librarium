"""Two-step sign-in with an authenticator app (TOTP) and one-time recovery codes.

Turning it on: the reader confirms their password, scans the QR code (``otpauth://`` link) and
types one code; then they get ten recovery codes, shown once. Signing in: after the password,
``/auth/login`` answers ``403 MFA_REQUIRED`` with a short-lived ``mfa_token``, and
``/auth/login/mfa`` takes that token with a code from the app or a recovery code. A code
cannot be used twice. Administrators can require it for staff and reset it for a user.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import totp
from app.core.config import Settings
from app.core.exceptions import AppError, AuthenticationError, BadRequestError, ConflictError
from app.core.security import verify_password
from app.models import User
from app.models.enums import STAFF_ROLES
from app.services.library_settings import get_library_settings

CHALLENGE_TTL = timedelta(minutes=5)
CHALLENGE_AUDIENCE = "librarium-mfa"


class MfaRequiredError(AppError):
    status_code = 403
    code = "MFA_REQUIRED"
    message = "Enter the code from your authenticator app"


def _box(settings: Settings) -> totp.SecretBox:
    return totp.SecretBox(settings.jwt_secret)


async def _check_password(user: User, password: str) -> None:
    if not await verify_password(user.password_hash, password):
        raise BadRequestError("Current password is incorrect", code="INVALID_CURRENT_PASSWORD")


@dataclass(frozen=True, slots=True)
class Setup:
    secret: str
    otpauth_uri: str


async def start_setup(
    session: AsyncSession, settings: Settings, user: User, password: str
) -> Setup:
    await _check_password(user, password)
    if user.mfa_enabled:
        raise ConflictError("Two-step sign-in is already on", code="MFA_ALREADY_ENABLED")
    secret = totp.new_secret()
    user.mfa_pending_secret = _box(settings).seal(secret)
    await session.commit()
    return Setup(secret=secret, otpauth_uri=totp.provisioning_uri(secret, user.email))


async def enable(session: AsyncSession, settings: Settings, user: User, code: str) -> list[str]:
    """Confirm the app with a first code; returns the recovery codes (shown only now)."""
    pending = _box(settings).open(user.mfa_pending_secret) if user.mfa_pending_secret else None
    if pending is None:
        raise ConflictError("Start setting up two-step sign-in first", code="MFA_SETUP_NOT_STARTED")
    step = totp.matching_step(pending, code)
    if step is None:
        raise BadRequestError("That code is not right", code="INVALID_MFA_CODE")
    codes = totp.new_recovery_codes()
    user.mfa_secret = user.mfa_pending_secret
    user.mfa_pending_secret = None
    user.mfa_enabled_at = datetime.now(UTC)
    user.mfa_last_step = step
    user.mfa_recovery_hashes = [totp.hash_recovery_code(c) for c in codes]
    await session.commit()
    return codes


def reset(user: User) -> None:
    """Turn it off (in the caller's transaction)."""
    user.mfa_secret = None
    user.mfa_pending_secret = None
    user.mfa_enabled_at = None
    user.mfa_last_step = None
    user.mfa_recovery_hashes = []


async def disable(session: AsyncSession, user: User, password: str) -> None:
    await _check_password(user, password)
    if user.role in STAFF_ROLES and (await get_library_settings(session)).require_staff_mfa:
        raise ConflictError(
            "The library requires two-step sign-in for staff", code="MFA_REQUIRED_BY_LIBRARY"
        )
    reset(user)
    await session.commit()


def verify(settings: Settings, user: User, code: str) -> bool:
    """A code from the app (not used before) or an unused recovery code; marks it used."""
    secret = _box(settings).open(user.mfa_secret) if user.mfa_secret else None
    if secret is not None:
        step = totp.matching_step(secret, code, after=user.mfa_last_step)
        if step is not None:
            user.mfa_last_step = step
            return True
    hashed = totp.hash_recovery_code(code)
    if hashed in user.mfa_recovery_hashes:
        user.mfa_recovery_hashes = [h for h in user.mfa_recovery_hashes if h != hashed]
        return True
    return False


def challenge(settings: Settings, user: User) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(user.id),
        "type": "mfa",
        "iss": settings.jwt_issuer,
        "aud": CHALLENGE_AUDIENCE,
        "iat": now,
        "exp": now + CHALLENGE_TTL,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def challenged_user_id(settings: Settings, token: str) -> uuid.UUID:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=CHALLENGE_AUDIENCE,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
        if claims.get("type") != "mfa":
            raise jwt.InvalidTokenError("wrong token type")
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise AuthenticationError(
            "Sign in again: the sign-in step expired", code="MFA_TOKEN_INVALID"
        ) from exc
