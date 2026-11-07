"""Registration, login and refresh-token rotation with reuse detection."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    PermissionDeniedError,
)
from app.core.security import (
    AccessToken,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.models import RefreshToken, User
from app.models.enums import UserRole
from app.repositories.users import get_user_by_email
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RegisterRequest
from app.services import mfa

logger = logging.getLogger(__name__)

EMAIL_TAKEN_MESSAGE = "An account with this email already exists"


@dataclass(frozen=True, slots=True)
class ClientMeta:
    user_agent: str | None = None
    ip_address: str | None = None


@dataclass(frozen=True, slots=True)
class AuthResult:
    user: User
    access_token: AccessToken
    refresh_token: str  # raw value, only ever placed in the HttpOnly cookie


def email_taken_error() -> ConflictError:
    return ConflictError(EMAIL_TAKEN_MESSAGE, code="EMAIL_ALREADY_EXISTS")


def _now() -> datetime:
    return datetime.now(UTC)


async def _issue_refresh_token(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    meta: ClientMeta,
) -> tuple[str, RefreshToken]:
    raw = generate_refresh_token()
    token = RefreshToken(
        id=uuid.uuid4(),
        user_id=user_id,
        token_hash=hash_refresh_token(raw),
        family_id=family_id,
        expires_at=_now() + timedelta(days=settings.refresh_token_expire_days),
        user_agent=(meta.user_agent or "")[:512] or None,
        ip_address=(meta.ip_address or "")[:45] or None,
    )
    session.add(token)
    await session.flush()
    return raw, token


async def revoke_user_tokens(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def _access_token_for(user: User, settings: Settings) -> AccessToken:
    return create_access_token(user_id=user.id, role=user.role, settings=settings)


async def register(
    session: AsyncSession, settings: Settings, data: RegisterRequest, meta: ClientMeta
) -> AuthResult:
    if await get_user_by_email(session, data.email) is not None:
        raise email_taken_error()

    user = User(
        id=uuid.uuid4(),
        email=data.email,
        password_hash=await hash_password(data.password),
        full_name=data.full_name,
        role=UserRole.CUSTOMER,  # never taken from the client
        whatsapp=data.whatsapp,
        telegram=data.telegram,
        instagram=data.instagram,
        phone=data.phone,
        preferred_contact_method=data.preferred_contact_method,
        preferred_language=data.preferred_language,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:  # concurrent registration with the same email
        await session.rollback()
        raise email_taken_error() from exc

    raw, _ = await _issue_refresh_token(
        session, settings, user_id=user.id, family_id=uuid.uuid4(), meta=meta
    )
    await session.commit()
    return AuthResult(user=user, access_token=_access_token_for(user, settings), refresh_token=raw)


async def login(
    session: AsyncSession, settings: Settings, data: LoginRequest, meta: ClientMeta
) -> AuthResult:
    user = await get_user_by_email(session, data.email)
    # Always run Argon2 so response time does not reveal whether the email exists.
    password_ok = await verify_password(user.password_hash if user else None, data.password)
    if user is None or not password_ok:
        raise AuthenticationError("Invalid email or password", code="INVALID_CREDENTIALS")
    if not user.is_active:
        raise PermissionDeniedError("This account has been disabled", code="ACCOUNT_DISABLED")

    if password_needs_rehash(user.password_hash):
        user.password_hash = await hash_password(data.password)
    if user.mfa_enabled:
        await session.commit()  # keep a rehashed password
        raise mfa.MfaRequiredError(details={"mfa_token": mfa.challenge(settings, user)})
    return await _signed_in(session, settings, user, meta)


async def signed_in(
    session: AsyncSession, settings: Settings, user: User, meta: ClientMeta
) -> AuthResult:
    """Issue a session for a user whose identity is already proven (e.g. by Google)."""
    return await _signed_in(session, settings, user, meta)


async def _signed_in(
    session: AsyncSession, settings: Settings, user: User, meta: ClientMeta
) -> AuthResult:
    raw, _ = await _issue_refresh_token(
        session, settings, user_id=user.id, family_id=uuid.uuid4(), meta=meta
    )
    await session.commit()
    return AuthResult(user=user, access_token=_access_token_for(user, settings), refresh_token=raw)


async def login_second_step(
    session: AsyncSession, settings: Settings, token: str, code: str, meta: ClientMeta
) -> AuthResult:
    """The code from the authenticator app (or a recovery code) after the password."""
    user = await session.get(User, mfa.challenged_user_id(settings, token), with_for_update=True)
    if user is None or not user.mfa_enabled:
        raise AuthenticationError("Sign in again", code="MFA_TOKEN_INVALID")
    if not user.is_active:
        raise PermissionDeniedError("This account has been disabled", code="ACCOUNT_DISABLED")
    if not mfa.verify(settings, user, code):
        await session.rollback()
        raise AuthenticationError("That code is not right", code="INVALID_MFA_CODE")
    return await _signed_in(session, settings, user, meta)


async def refresh(
    session: AsyncSession, settings: Settings, raw_token: str | None, meta: ClientMeta
) -> AuthResult:
    if not raw_token:
        raise AuthenticationError("Refresh token is missing", code="REFRESH_TOKEN_MISSING")

    current = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw_token))
        .with_for_update()
    )
    if current is None:
        raise AuthenticationError("Refresh token is invalid", code="REFRESH_TOKEN_INVALID")

    if current.revoked_at is not None:
        # A rotated/revoked token came back: assume it was stolen and kill the whole family.
        await _revoke_family(session, current.family_id)
        await session.commit()
        logger.warning(
            "Refresh token reuse detected (user=%s, family=%s); family revoked",
            current.user_id,
            current.family_id,
        )
        raise AuthenticationError(
            "Refresh token has already been used", code="REFRESH_TOKEN_REUSED"
        )

    now = _now()
    if current.expires_at <= now:
        current.revoked_at = now
        await session.commit()
        raise AuthenticationError("Refresh token has expired", code="REFRESH_TOKEN_EXPIRED")

    user = await session.get(User, current.user_id)
    if user is None or not user.is_active:
        await _revoke_family(session, current.family_id)
        await session.commit()
        raise AuthenticationError("This account has been disabled", code="ACCOUNT_DISABLED")

    # Insert the successor first so the replaced_by foreign key can point at it.
    raw, successor = await _issue_refresh_token(
        session, settings, user_id=user.id, family_id=current.family_id, meta=meta
    )
    current.revoked_at = now
    current.replaced_by_token_id = successor.id
    await session.commit()
    return AuthResult(user=user, access_token=_access_token_for(user, settings), refresh_token=raw)


async def logout(session: AsyncSession, raw_token: str | None) -> None:
    if not raw_token:
        return
    token = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw_token))
        .with_for_update()
    )
    if token is not None and token.revoked_at is None:
        token.revoked_at = _now()
        await session.commit()


async def change_password(
    session: AsyncSession,
    settings: Settings,
    user: User,
    data: ChangePasswordRequest,
    meta: ClientMeta,
) -> AuthResult:
    if not await verify_password(user.password_hash, data.current_password):
        # Deliberately not 401: the client must not treat this as an expired session.
        raise BadRequestError("Current password is incorrect", code="INVALID_CURRENT_PASSWORD")
    if data.current_password == data.new_password:
        raise BadRequestError(
            "The new password must differ from the current one", code="PASSWORD_UNCHANGED"
        )

    user.password_hash = await hash_password(data.new_password)
    # Sign out every other session; the caller gets a fresh token family.
    await revoke_user_tokens(session, user.id)
    raw, _ = await _issue_refresh_token(
        session, settings, user_id=user.id, family_id=uuid.uuid4(), meta=meta
    )
    await session.commit()
    return AuthResult(user=user, access_token=_access_token_for(user, settings), refresh_token=raw)
