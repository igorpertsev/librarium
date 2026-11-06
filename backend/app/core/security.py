"""Password hashing (Argon2id), access tokens (JWT) and opaque refresh tokens."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.models.enums import UserRole

ACCESS_TOKEN_TYPE = "access"  # noqa: S105 - token type marker, not a secret

# argon2-cffi defaults: Argon2id, time_cost=3, memory_cost=64 MiB, parallelism=4.
_password_hasher = PasswordHasher()


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A valid hash used to equalise timing when the account does not exist."""
    return _password_hasher.hash(secrets.token_urlsafe(16))


def _hash_password_sync(password: str) -> str:
    return _password_hasher.hash(password)


def _verify_password_sync(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


async def hash_password(password: str) -> str:
    """Hash a password off the event loop (Argon2 is intentionally CPU/memory heavy)."""
    return await run_in_threadpool(_hash_password_sync, password)


async def verify_password(password_hash: str | None, password: str) -> bool:
    """Verify a password; with ``password_hash=None`` burns the same time and returns False."""
    if password_hash is None:
        await run_in_threadpool(_verify_password_sync, _dummy_hash(), password)
        return False
    return await run_in_threadpool(_verify_password_sync, password_hash, password)


def password_needs_rehash(password_hash: str) -> bool:
    return _password_hasher.check_needs_rehash(password_hash)


@dataclass(frozen=True, slots=True)
class AccessToken:
    token: str
    expires_in: int
    jti: str


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    role: str
    jti: str
    issued_at: datetime
    expires_at: datetime


class InvalidAccessTokenError(Exception):
    def __init__(self, *, expired: bool = False) -> None:
        super().__init__("expired" if expired else "invalid")
        self.expired = expired


def create_access_token(
    *, user_id: uuid.UUID, role: UserRole, settings: Settings, now: datetime | None = None
) -> AccessToken:
    issued_at = now or datetime.now(UTC)
    lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "type": ACCESS_TOKEN_TYPE,
        "jti": jti,
        "iat": int(issued_at.timestamp()),
        "nbf": int(issued_at.timestamp()),
        "exp": int((issued_at + lifetime).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return AccessToken(token=token, expires_in=int(lifetime.total_seconds()), jti=jti)


def decode_access_token(token: str, settings: Settings) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "role", "exp", "iat", "jti", "type"]},
            leeway=5,
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidAccessTokenError(expired=True) from exc
    except jwt.PyJWTError as exc:
        raise InvalidAccessTokenError from exc

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise InvalidAccessTokenError
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except ValueError as exc:
        raise InvalidAccessTokenError from exc
    return AccessTokenClaims(
        user_id=user_id,
        role=str(payload["role"]),
        jti=str(payload["jti"]),
        issued_at=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
        expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
    )


def generate_refresh_token() -> str:
    """256+ bits of randomness, URL-safe. Only its hash is ever stored."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    # Refresh tokens are high-entropy random values, so a fast hash is sufficient
    # (a slow KDF only matters for low-entropy secrets such as passwords).
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
