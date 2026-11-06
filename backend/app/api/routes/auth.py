from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.dependencies import ClientMetaDep, CurrentUser, SessionDep, SettingsDep
from app.core.config import Settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError, error_payload
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RegisterRequest, TokenResponse
from app.schemas.common import error_responses
from app.schemas.user import UserRead
from app.services import auth as auth_service
from app.services.auth import AuthResult

router = APIRouter(prefix="/auth", tags=["auth"])


# The cookie name is configurable, so it is read from the request instead of a Cookie() param.
def _refresh_cookie(request: Request, settings: Settings) -> str | None:
    return request.cookies.get(settings.refresh_cookie_name)


def _set_refresh_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=settings.refresh_cookie_path,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def _check_origin(request: Request, settings: Settings) -> None:
    """Defence in depth against cross-site requests to cookie-authenticated endpoints."""
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        raise PermissionDeniedError("Request origin is not allowed", code="ORIGIN_NOT_ALLOWED")


def _token_response(result: AuthResult) -> TokenResponse:
    return TokenResponse(
        access_token=result.access_token.token,
        expires_in=result.access_token.expires_in,
        user=UserRead.model_validate(result.user),
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=TokenResponse,
    responses=error_responses(403, 409, 422),
)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    meta: ClientMetaDep,
) -> TokenResponse:
    _check_origin(request, settings)
    result = await auth_service.register(session, settings, body, meta)
    _set_refresh_cookie(response, settings, result.refresh_token)
    return _token_response(result)


@router.post("/login", response_model=TokenResponse, responses=error_responses(401, 403, 422))
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    meta: ClientMetaDep,
) -> TokenResponse:
    _check_origin(request, settings)
    result = await auth_service.login(session, settings, body, meta)
    _set_refresh_cookie(response, settings, result.refresh_token)
    return _token_response(result)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses=error_responses(401, 403),
    description="Rotates the refresh cookie and returns a new access token. "
    "Re-using an already rotated refresh token revokes the whole token family.",
)
async def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    meta: ClientMetaDep,
) -> TokenResponse | JSONResponse:
    _check_origin(request, settings)
    try:
        result = await auth_service.refresh(
            session, settings, _refresh_cookie(request, settings), meta
        )
    except AuthenticationError as exc:
        # Drop the useless cookie together with the error.
        error = JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message),
            headers=exc.headers,
        )
        _clear_refresh_cookie(error, settings)
        return error
    _set_refresh_cookie(response, settings, result.refresh_token)
    return _token_response(result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403))
async def logout(request: Request, session: SessionDep, settings: SettingsDep) -> Response:
    _check_origin(request, settings)
    await auth_service.logout(session, _refresh_cookie(request, settings))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response, settings)
    return response


@router.get("/me", response_model=UserRead, responses=error_responses(401))
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.post(
    "/change-password",
    response_model=TokenResponse,
    responses=error_responses(400, 401, 403, 422),
    description="Changes the password, signs out all other sessions and issues new tokens.",
)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    meta: ClientMetaDep,
) -> TokenResponse:
    _check_origin(request, settings)
    result = await auth_service.change_password(session, settings, user, body, meta)
    _set_refresh_cookie(response, settings, result.refresh_token)
    return _token_response(result)
