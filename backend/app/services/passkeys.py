"""Passkeys: signing in with WebAuthn (Face ID, Touch ID, Windows Hello, a phone or a key).

Adding one: the signed-in user confirms their password, the browser creates a credential for this
site (``rp_id`` = the host of APP_BASE_URL) and we keep its public key. Signing in: the browser
offers the passkeys it has for this site (no email needed) and signs our challenge; we check the
signature, the origin (the frontend's origins) and that the user was verified on the device.
The challenge travels in a short-lived signed ``state`` token, so nothing waits on the server.
A passkey sign-in needs no extra code: it is already two factors (the device and its unlock).
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlsplit

import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import Settings
from app.core.exceptions import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.security import verify_password
from app.models import Passkey, User

STATE_TTL = timedelta(minutes=5)
STATE_AUDIENCE = "librarium-passkey"
MAX_PASSKEYS = 10
RP_NAME = "Little Dragon"
Ceremony = Literal["register", "login"]


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def relying_party(settings: Settings) -> tuple[str, list[str]]:
    """The site passkeys belong to (host of APP_BASE_URL) and the origins allowed to use them."""
    rp_id = urlsplit(settings.app_base_url).hostname or "localhost"
    origins = sorted({_origin(settings.app_base_url), *settings.cors_origins})
    return rp_id, origins


def _state(
    settings: Settings, challenge: bytes, ceremony: Ceremony, user_id: uuid.UUID | None
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "aud": STATE_AUDIENCE,
        "iat": now,
        "exp": now + STATE_TTL,
        "c": ceremony,
        "ch": base64.urlsafe_b64encode(challenge).decode(),
    }
    if user_id is not None:
        claims["sub"] = str(user_id)
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _challenge(
    settings: Settings, state: str, ceremony: Ceremony, user_id: uuid.UUID | None = None
) -> bytes:
    try:
        claims = jwt.decode(
            state, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience=STATE_AUDIENCE
        )
        if claims.get("c") != ceremony or (
            user_id is not None and claims.get("sub") != str(user_id)
        ):
            raise jwt.InvalidTokenError("wrong ceremony")
        return base64.urlsafe_b64decode(claims["ch"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise AuthenticationError("Start again: that took too long", code="PASSKEY_STATE") from exc


# --- Adding a passkey ------------------------------------------------------------------------


async def registration_options(
    session: AsyncSession, settings: Settings, user: User, password: str
) -> tuple[dict[str, Any], str]:
    if not await verify_password(user.password_hash, password):
        raise BadRequestError("Current password is incorrect", code="INVALID_CURRENT_PASSWORD")
    rp_id, _ = relying_party(settings)
    existing = (
        await session.scalars(select(Passkey.credential_id).where(Passkey.user_id == user.id))
    ).all()
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=RP_NAME,
        user_name=user.email,
        user_id=user.id.bytes,
        user_display_name=user.full_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=c) for c in existing],
    )
    return json.loads(options_to_json(options)), _state(
        settings, options.challenge, "register", user.id
    )


async def register(
    session: AsyncSession,
    settings: Settings,
    user: User,
    *,
    state: str,
    credential: dict[str, Any],
    name: str,
) -> Passkey:
    challenge = _challenge(settings, state, "register", user.id)
    count = await session.scalar(select(func.count(Passkey.id)).where(Passkey.user_id == user.id))
    if (count or 0) >= MAX_PASSKEYS:
        raise ConflictError(f"At most {MAX_PASSKEYS} passkeys", code="TOO_MANY_PASSKEYS")
    rp_id, origins = relying_party(settings)
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origins,
            require_user_verification=True,
        )
    except (InvalidRegistrationResponse, ValueError, KeyError, TypeError) as exc:
        raise BadRequestError("The passkey could not be checked", code="PASSKEY_INVALID") from exc
    taken = await session.scalar(
        select(Passkey.id).where(Passkey.credential_id == verified.credential_id)
    )
    if taken is not None:
        raise ConflictError("This passkey is already registered", code="PASSKEY_EXISTS")
    transports = credential.get("response", {}).get("transports") or []
    passkey = Passkey(
        id=uuid.uuid4(),
        user_id=user.id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        transports=[str(t) for t in transports][:8] if isinstance(transports, list) else [],
        name=name,
    )
    session.add(passkey)
    await session.commit()
    return passkey


async def list_passkeys(session: AsyncSession, user: User) -> list[Passkey]:
    found = await session.scalars(
        select(Passkey).where(Passkey.user_id == user.id).order_by(Passkey.created_at)
    )
    return list(found)


async def remove(session: AsyncSession, user: User, passkey_id: uuid.UUID) -> None:
    passkey = await session.get(Passkey, passkey_id)
    if passkey is None or passkey.user_id != user.id:
        raise NotFoundError("Passkey not found", code="PASSKEY_NOT_FOUND")
    await session.delete(passkey)
    await session.commit()


async def has_passkey(session: AsyncSession, user_id: uuid.UUID) -> bool:
    found = await session.scalar(select(Passkey.id).where(Passkey.user_id == user_id).limit(1))
    return found is not None


# --- Signing in ------------------------------------------------------------------------------


def login_options(settings: Settings) -> tuple[dict[str, Any], str]:
    rp_id, _ = relying_party(settings)
    options = generate_authentication_options(
        rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED
    )
    return json.loads(options_to_json(options)), _state(settings, options.challenge, "login", None)


async def login(
    session: AsyncSession, settings: Settings, *, state: str, credential: dict[str, Any]
) -> User:
    challenge = _challenge(settings, state, "login")
    try:
        credential_id = base64url_to_bytes(str(credential.get("rawId") or credential["id"]))
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Unknown passkey", code="PASSKEY_UNKNOWN") from exc
    passkey = await session.scalar(
        select(Passkey).where(Passkey.credential_id == credential_id).with_for_update()
    )
    if passkey is None:
        raise AuthenticationError("Unknown passkey", code="PASSKEY_UNKNOWN")
    user = await session.get(User, passkey.user_id)
    if user is None:  # pragma: no cover - the passkey goes with the user
        raise AuthenticationError("Unknown passkey", code="PASSKEY_UNKNOWN")
    if not user.is_active:
        raise PermissionDeniedError("This account has been disabled", code="ACCOUNT_DISABLED")
    rp_id, origins = relying_party(settings)
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origins,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except (InvalidAuthenticationResponse, ValueError, KeyError, TypeError) as exc:
        await session.rollback()
        raise AuthenticationError("The passkey did not sign in", code="PASSKEY_INVALID") from exc
    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = datetime.now(UTC)
    await session.flush()
    return user
