"""FastAPI dependencies: DB session, settings, authentication and authorisation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import Database
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.rate_limit import RateLimiter
from app.core.security import InvalidAccessTokenError, decode_access_token
from app.models import User
from app.models.enums import UserRole
from app.services.auth import ClientMeta


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


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
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
