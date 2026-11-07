from __future__ import annotations

import logging
from email.message import EmailMessage

from fastapi import APIRouter, BackgroundTasks, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.dependencies import (
    ClientMetaDep,
    CurrentUser,
    MailSenderDep,
    RateLimiterDep,
    SessionDep,
    SettingsDep,
)
from app.core.config import Settings
from app.core.exceptions import (
    AppError,
    AuthenticationError,
    PermissionDeniedError,
    error_payload,
)
from app.core.rate_limit import (
    FORGOT_PASSWORD_PER_EMAIL,
    FORGOT_PASSWORD_PER_IP,
    LOGIN_FAILURES_PER_EMAIL,
    LOGIN_PER_IP,
    PASSWORD_FAILURES_PER_USER,
    REFRESH_PER_IP,
    REGISTER_PER_IP,
    RESET_PASSWORD_PER_IP,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginMfaRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.common import error_responses
from app.schemas.user import UserRead
from app.services import auth as auth_service
from app.services import mfa, password_reset
from app.services.auth import AuthResult, ClientMeta
from app.services.notifications import Sender

logger = logging.getLogger(__name__)

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


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
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


def _client_ip(meta: ClientMeta) -> str:
    return meta.ip_address or "unknown"


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
    responses=error_responses(403, 409, 422, 429),
)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    meta: ClientMetaDep,
    limiter: RateLimiterDep,
) -> TokenResponse:
    _check_origin(request, settings)
    limiter.consume(f"register:ip:{_client_ip(meta)}", REGISTER_PER_IP)
    result = await auth_service.register(session, settings, body, meta)
    _set_refresh_cookie(response, settings, result.refresh_token)
    return _token_response(result)


@router.post(
    "/login",
    response_model=TokenResponse,
    responses=error_responses(401, 403, 422, 429),
    description="After 10 failed attempts for one email address within 15 minutes, further "
    "attempts are refused with 429 until the window has passed.",
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    meta: ClientMetaDep,
    limiter: RateLimiterDep,
) -> TokenResponse:
    _check_origin(request, settings)
    limiter.consume(f"login:ip:{_client_ip(meta)}", LOGIN_PER_IP)
    email_key = f"login:email:{body.email}"
    limiter.check(email_key, LOGIN_FAILURES_PER_EMAIL)
    try:
        result = await auth_service.login(session, settings, body, meta)
    except AuthenticationError:
        limiter.hit(email_key, LOGIN_FAILURES_PER_EMAIL)
        raise
    limiter.reset(email_key)
    _set_refresh_cookie(response, settings, result.refresh_token)
    return _token_response(result)


@router.post(
    "/login/mfa",
    response_model=TokenResponse,
    responses=error_responses(401, 403, 422, 429),
    description="Second step of signing in with two-step sign-in on: the mfa_token from the "
    "403 MFA_REQUIRED answer of /auth/login and a code from the authenticator app (or a "
    "recovery code).",
)
async def login_mfa(
    body: LoginMfaRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    meta: ClientMetaDep,
    limiter: RateLimiterDep,
) -> TokenResponse:
    _check_origin(request, settings)
    limiter.consume(f"login:ip:{_client_ip(meta)}", LOGIN_PER_IP)
    user_key = f"mfa:{mfa.challenged_user_id(settings, body.mfa_token)}"
    limiter.check(user_key, LOGIN_FAILURES_PER_EMAIL)
    try:
        result = await auth_service.login_second_step(
            session, settings, body.mfa_token, body.code, meta
        )
    except AuthenticationError:
        limiter.hit(user_key, LOGIN_FAILURES_PER_EMAIL)
        raise
    limiter.reset(user_key)
    _set_refresh_cookie(response, settings, result.refresh_token)
    return _token_response(result)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses=error_responses(401, 403, 429),
    description="Rotates the refresh cookie and returns a new access token. "
    "Re-using an already rotated refresh token revokes the whole token family.",
)
async def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    meta: ClientMetaDep,
    limiter: RateLimiterDep,
) -> TokenResponse | JSONResponse:
    _check_origin(request, settings)
    limiter.consume(f"refresh:ip:{_client_ip(meta)}", REFRESH_PER_IP)
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
        clear_refresh_cookie(error, settings)
        return error
    _set_refresh_cookie(response, settings, result.refresh_token)
    return _token_response(result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(403))
async def logout(request: Request, session: SessionDep, settings: SettingsDep) -> Response:
    _check_origin(request, settings)
    await auth_service.logout(session, _refresh_cookie(request, settings))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response, settings)
    return response


@router.get("/me", response_model=UserRead, responses=error_responses(401))
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.post(
    "/change-password",
    response_model=TokenResponse,
    responses=error_responses(400, 401, 403, 422, 429),
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
    limiter: RateLimiterDep,
) -> TokenResponse:
    _check_origin(request, settings)
    key = f"change-password:user:{user.id}"
    limiter.check(key, PASSWORD_FAILURES_PER_USER)
    try:
        result = await auth_service.change_password(session, settings, user, body, meta)
    except AppError as exc:
        if exc.code == "INVALID_CURRENT_PASSWORD":
            limiter.hit(key, PASSWORD_FAILURES_PER_USER)
        raise
    limiter.reset(key)
    _set_refresh_cookie(response, settings, result.refresh_token)
    return _token_response(result)


async def _send_reset_email(send: Sender, message: EmailMessage) -> None:
    try:
        await send(message)
    except Exception:  # the client already got its answer; log and move on
        logger.exception("Could not send the password reset email")


@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,
    responses=error_responses(403, 422, 429),
    description="Emails a password reset link if an active account uses this address. "
    "The answer is the same either way, so it does not reveal which addresses are registered.",
)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    session: SessionDep,
    settings: SettingsDep,
    meta: ClientMetaDep,
    limiter: RateLimiterDep,
    send: MailSenderDep,
) -> Response:
    _check_origin(request, settings)
    limiter.consume(f"forgot-password:ip:{_client_ip(meta)}", FORGOT_PASSWORD_PER_IP)
    limiter.consume(f"forgot-password:email:{body.email}", FORGOT_PASSWORD_PER_EMAIL)
    message = await password_reset.build_reset_email(session, settings, body.email)
    if message is not None:
        if send is None:
            logger.warning("SMTP_HOST is not set: the password reset email was not sent")
        else:
            background.add_task(_send_reset_email, send, message)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(400, 403, 422, 429),
    description="Sets a new password with the token from the reset email and signs the "
    "account out everywhere. Fails with INVALID_RESET_TOKEN for expired or used links.",
)
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    meta: ClientMetaDep,
    limiter: RateLimiterDep,
) -> Response:
    _check_origin(request, settings)
    limiter.consume(f"reset-password:ip:{_client_ip(meta)}", RESET_PASSWORD_PER_IP)
    await password_reset.reset_password(session, settings, body.token, body.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
