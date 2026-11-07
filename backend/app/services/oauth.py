"""Sign in with Google or Apple (OpenID Connect, authorization code flow with PKCE).

``start`` sends the browser to the provider with a random ``state``, ``nonce`` and PKCE
verifier, kept in a short-lived signed, HttpOnly cookie. On the way back ``finish`` checks the
state against the cookie, exchanges the code (with the verifier) for an ID token, and checks
the token's signature (the provider's published keys), issuer, audience, expiry and nonce.

The account is found by the provider's subject id, or by the verified email address (then the
identity is linked to it), or created. Two-step sign-in still applies: those users finish on
the sign-in page with a code. Apple posts the result back (``response_mode=form_post``) and
needs a client secret signed with the team's key; it sends the person's name only the first
time.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.security import hash_password
from app.models import User, UserIdentity
from app.models.enums import UserRole
from app.repositories.users import get_user_by_email

Provider = Literal["google", "apple"]
STATE_TTL = timedelta(minutes=10)
STATE_AUDIENCE = "librarium-oauth-state"
JWKS_TTL = 3600.0


class OAuthError(AppError):
    status_code = 400
    code = "OAUTH_FAILED"
    message = "Signing in with that provider did not work"


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    name: Provider
    authorize_url: str
    token_url: str
    jwks_url: str
    issuers: frozenset[str]
    client_id: str
    scope: str = "openid email profile"
    extra: dict[str, str] = field(default_factory=dict)


def _apple_client_secret(settings: Settings) -> str:
    """Apple wants a short-lived ES256 JWT signed with the team's private key."""
    assert settings.apple_private_key is not None  # noqa: S101 - checked by providers()
    now = int(time.time())
    return jwt.encode(
        {
            "iss": settings.apple_team_id,
            "iat": now,
            "exp": now + 300,
            "aud": "https://appleid.apple.com",
            "sub": settings.apple_client_id,
        },
        settings.apple_private_key.get_secret_value(),
        algorithm="ES256",
        headers={"kid": settings.apple_key_id},
    )


def providers(settings: Settings) -> dict[Provider, ProviderConfig]:
    """The providers with credentials in the settings."""
    found: dict[Provider, ProviderConfig] = {}
    if settings.google_client_id and settings.google_client_secret:
        found["google"] = ProviderConfig(
            name="google",
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",  # noqa: S106 - a URL, not a secret
            jwks_url="https://www.googleapis.com/oauth2/v3/certs",
            issuers=frozenset({"https://accounts.google.com", "accounts.google.com"}),
            client_id=settings.google_client_id,
            extra={"prompt": "select_account"},
        )
    if (
        settings.apple_client_id
        and settings.apple_team_id
        and settings.apple_key_id
        and settings.apple_private_key
    ):
        found["apple"] = ProviderConfig(
            name="apple",
            authorize_url="https://appleid.apple.com/auth/authorize",
            token_url="https://appleid.apple.com/auth/token",  # noqa: S106 - a URL
            jwks_url="https://appleid.apple.com/auth/keys",
            issuers=frozenset({"https://appleid.apple.com"}),
            client_id=settings.apple_client_id,
            scope="name email",
            extra={"response_mode": "form_post"},
        )
    return found


def _config(settings: Settings, name: str) -> ProviderConfig:
    config = next((c for key, c in providers(settings).items() if key == name), None)
    if config is None:
        raise OAuthError("That sign-in method is not set up", code="OAUTH_NOT_CONFIGURED")
    return config


def redirect_uri(settings: Settings, name: str) -> str:
    return f"{settings.public_api_url}/auth/oauth/{name}/callback"


def _safe_next(path: str | None) -> str:
    """Only paths on this site after signing in, never another address."""
    if path and path.startswith("/") and not path.startswith("//") and "\\" not in path:
        return path[:500]
    return "/"


# --- Start ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Start:
    url: str
    state_cookie: str


def start(settings: Settings, name: str, next_path: str | None) -> Start:
    config = _config(settings, name)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    params = {
        "client_id": config.client_id,
        "redirect_uri": redirect_uri(settings, name),
        "response_type": "code",
        "scope": config.scope,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        **config.extra,
    }
    now = datetime.now(UTC)
    cookie = jwt.encode(
        {
            "aud": STATE_AUDIENCE,
            "exp": now + STATE_TTL,
            "p": name,
            "s": state,
            "n": nonce,
            "v": verifier,
            "next": _safe_next(next_path),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return Start(url=f"{config.authorize_url}?{urlencode(params)}", state_cookie=cookie)


# --- Finish --------------------------------------------------------------------------------


_jwks_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


async def _jwks(http: httpx.AsyncClient, url: str) -> list[dict[str, Any]]:
    cached = _jwks_cache.get(url)
    if cached and time.monotonic() - cached[0] < JWKS_TTL:
        return cached[1]
    try:
        response = await http.get(url, timeout=10)
        response.raise_for_status()
        keys = list(response.json()["keys"])
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise OAuthError("Could not get the provider's keys", code="OAUTH_FAILED") from exc
    _jwks_cache[url] = (time.monotonic(), keys)
    return keys


async def _verify_id_token(
    http: httpx.AsyncClient, config: ProviderConfig, token: str, nonce: str
) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
        keys = await _jwks(http, config.jwks_url)
        match = next((k for k in keys if k.get("kid") == header.get("kid")), None)
        if match is None:
            raise OAuthError("Unknown signing key", code="OAUTH_FAILED")
        key = jwt.PyJWK(match).key
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["RS256", "ES256"],
            audience=config.client_id,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=60,
        )
    except jwt.PyJWTError as exc:
        raise OAuthError("The sign-in token is not valid", code="OAUTH_FAILED") from exc
    if claims.get("iss") not in config.issuers:
        raise OAuthError("The sign-in token is not valid", code="OAUTH_FAILED")
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise OAuthError("The sign-in token is not valid", code="OAUTH_FAILED")
    return claims


def _verified_email(claims: dict[str, Any]) -> str:
    email = str(claims.get("email") or "").strip().lower()
    verified = claims.get("email_verified") in (True, "true")
    if not email or not verified:
        raise OAuthError("The provider did not confirm an email address", code="OAUTH_NO_EMAIL")
    return email


def _name(claims: dict[str, Any], apple_user: str | None, email: str) -> str:
    if claims.get("name"):
        return str(claims["name"])[:200]
    if apple_user:  # Apple sends {"name": {"firstName", "lastName"}} the first time only
        try:
            name = json.loads(apple_user).get("name") or {}
            full = f"{name.get('firstName', '')} {name.get('lastName', '')}".strip()
            if full:
                return full[:200]
        except (ValueError, AttributeError):
            pass
    return email.split("@", 1)[0][:200]


@dataclass(frozen=True, slots=True)
class Finished:
    user: User
    next_path: str


async def finish(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    name: str,
    *,
    state_cookie: str | None,
    state: str | None,
    code: str | None,
    apple_user: str | None = None,
) -> Finished:
    config = _config(settings, name)
    try:
        saved = jwt.decode(
            state_cookie or "",
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=STATE_AUDIENCE,
        )
    except jwt.PyJWTError as exc:
        raise OAuthError("Start signing in again", code="OAUTH_STATE") from exc
    if saved.get("p") != name or not state or not secrets.compare_digest(saved["s"], state):
        raise OAuthError("Start signing in again", code="OAUTH_STATE")
    if not code:
        raise OAuthError("Signing in was cancelled", code="OAUTH_CANCELLED")

    secret = (
        settings.google_client_secret.get_secret_value()
        if name == "google" and settings.google_client_secret
        else _apple_client_secret(settings)
    )
    try:
        response = await http.post(
            config.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(settings, name),
                "client_id": config.client_id,
                "client_secret": secret,
                "code_verifier": saved["v"],
            },
            timeout=15,
        )
        response.raise_for_status()
        id_token = str(response.json()["id_token"])
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise OAuthError("The provider did not accept the sign-in", code="OAUTH_FAILED") from exc

    claims = await _verify_id_token(http, config, id_token, saved["n"])
    email = _verified_email(claims)
    user = await _account(
        session, name, str(claims["sub"]), email, _name(claims, apple_user, email)
    )
    return Finished(user=user, next_path=_safe_next(saved.get("next")))


async def _account(
    session: AsyncSession, provider: str, subject: str, email: str, full_name: str
) -> User:
    identity = await session.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == provider, UserIdentity.subject == subject
        )
    )
    if identity is not None:
        user = await session.get(User, identity.user_id)
        if user is not None:
            return user
    user = await get_user_by_email(session, email)
    if user is None:
        user = User(
            id=uuid.uuid4(),
            email=email,
            # Nobody knows this password; "Forgot password" sets a real one if wanted.
            password_hash=await hash_password(secrets.token_urlsafe(32)),
            full_name=full_name,
            role=UserRole.CUSTOMER,
        )
        session.add(user)
        await session.flush()
    session.add(
        UserIdentity(
            id=uuid.uuid4(), provider=provider, subject=subject, user_id=user.id, email=email
        )
    )
    await session.flush()
    return user
