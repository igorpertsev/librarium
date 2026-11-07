"""FastAPI dependencies: DB session, settings, authentication and authorisation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import Database
from app.core.exceptions import AppError, AuthenticationError, PermissionDeniedError
from app.core.rate_limit import RateLimiter
from app.core.security import InvalidAccessTokenError, decode_access_token
from app.core.text import MESSAGE as UNSTORABLE_TEXT
from app.core.text import unstorable
from app.models import User
from app.models.enums import STAFF_ROLES, UserRole
from app.services import audit, passkeys
from app.services.auth import ClientMeta
from app.services.library_settings import get_library_settings
from app.services.media_storage import MediaStorage
from app.services.notifications import Sender
from app.services.openlibrary import OpenLibraryClient
from app.services.translation_lookup import TranslationLookup


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    database: Database = request.app.state.db
    # Leaving the context closes the session, rolling back anything not committed
    # (e.g. when a service raises a 409 halfway through a transaction).
    async with database.sessionmaker() as session:
        yield session


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


def get_mail_sender(request: Request) -> Sender | None:
    sender: Sender | None = request.app.state.mail_sender
    return sender


def get_openlibrary(request: Request) -> OpenLibraryClient:
    client: OpenLibraryClient = request.app.state.openlibrary
    return client


def get_translation_lookup(request: Request) -> TranslationLookup:
    lookup: TranslationLookup = request.app.state.translation_lookup
    return lookup


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_media_storage(request: Request) -> MediaStorage:
    storage: MediaStorage = request.app.state.media
    return storage


MediaStorageDep = Annotated[MediaStorage, Depends(get_media_storage)]
MailSenderDep = Annotated[Sender | None, Depends(get_mail_sender)]
OpenLibraryDep = Annotated[OpenLibraryClient, Depends(get_openlibrary)]
TranslationLookupDep = Annotated[TranslationLookup, Depends(get_translation_lookup)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]

_bearer = HTTPBearer(auto_error=False, description="Access token from /auth/login or /auth/refresh")


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError()
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except InvalidAccessTokenError as exc:
        if exc.expired:
            raise AuthenticationError("Access token has expired", code="TOKEN_EXPIRED") from exc
        raise AuthenticationError("Access token is invalid", code="INVALID_TOKEN") from exc

    user = await session.get(User, claims.user_id)
    if user is None:
        raise AuthenticationError("Access token is invalid", code="INVALID_TOKEN")
    if not user.is_active:
        raise AuthenticationError("This account has been disabled", code="ACCOUNT_DISABLED")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    # Authorisation uses the role stored in the database, never the token claim alone.
    if user.role is not UserRole.ADMIN:
        raise PermissionDeniedError("Administrator privileges are required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


async def require_staff(user: CurrentUser, session: SessionDep) -> User:
    """Librarians and administrators (the admin portal); with two-step sign-in when the
    library requires it for staff."""
    if user.role not in STAFF_ROLES:
        raise PermissionDeniedError("Library staff privileges are required")
    # A passkey counts: it is already two factors (the device and its unlock).
    if (
        not user.mfa_enabled
        and (await get_library_settings(session)).require_staff_mfa
        and not await passkeys.has_passkey(session, user.id)
    ):
        raise PermissionDeniedError(
            "Turn on two-step sign-in on your profile to use the admin portal",
            code="MFA_SETUP_REQUIRED",
        )
    return user


StaffUser = Annotated[User, Depends(require_staff)]

AUDITED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# POST endpoints that change nothing, or only a stocktake's counts (one per scanned book).
NOT_AUDITED = frozenset(
    {"admin_suggest_translation", "admin_stocktake_scan", "admin_stocktake_count"}
)


async def audit_trail(
    request: Request, user: StaffUser, session: SessionDep
) -> AsyncIterator[None]:
    """Record staff changes in the activity log once they have succeeded.

    FastAPI has already read the body (it is cached on the request); an endpoint that fails
    raises through the ``yield``, so nothing is recorded for it.
    """
    # File uploads (multipart) are not copied into the log; only JSON bodies are.
    is_json = request.headers.get("content-type", "").startswith("application/json")
    body = await request.body() if request.method in AUDITED_METHODS and is_json else b""
    yield
    route = request.scope.get("route")
    name = getattr(route, "name", None) or request.url.path
    if request.method not in AUDITED_METHODS or name in NOT_AUDITED:
        return
    await audit.record(
        session,
        user,
        action=name,
        method=request.method,
        path=getattr(route, "path", None) or request.url.path,
        path_params=dict(request.path_params),
        query=dict(request.query_params),
        body=body,
    )


def client_meta(request: Request) -> ClientMeta:
    return ClientMeta(
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )


ClientMetaDep = Annotated[ClientMeta, Depends(client_meta)]


class Pagination:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1, le=100_000)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> None:
        self.page = page
        self.page_size = page_size


PaginationDep = Annotated[Pagination, Depends()]


async def storable_parameters(request: Request) -> None:
    """Query and path parameters with a NUL character (``?q=%00``) are refused (see core.text)."""
    if unstorable(list(request.query_params.multi_items())) or unstorable(
        list(request.path_params.values())
    ):
        raise AppError(UNSTORABLE_TEXT, code="INVALID_CHARACTERS", status_code=422)
