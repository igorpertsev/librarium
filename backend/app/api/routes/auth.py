from __future__ import annotations

import logging
from email.message import EmailMessage
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Form, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    ClientMetaDep,
    CurrentUser,
    MailSenderDep,
    RateLimiterDep,
    SessionDep,
    SettingsDep,
)
from app.api.prefix import API_PREFIX
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
    OAuthProviders,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.common import error_responses
from app.schemas.passkey import PasskeyOptions, PasskeySignIn
from app.schemas.user import UserRead
from app.services import auth as auth_service
from app.services import mfa, oauth, passkeys, password_reset
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
    "/passkey/options",
    response_model=PasskeyOptions,
    responses=error_responses(403, 429),
    description="Start signing in with a passkey: options for navigator.credentials.get() "
    "(any passkey of this site) and a state to send back.",
)
async def passkey_options(
    request: Request, settings: SettingsDep, meta: ClientMetaDep, limiter: RateLimiterDep
) -> PasskeyOptions:
    _check_origin(request, settings)
    limiter.consume(f"login:ip:{_client_ip(meta)}", LOGIN_PER_IP)
    options, state = passkeys.login_options(settings)
    return PasskeyOptions(options=options, state=state)


@router.post(
    "/passkey",
    response_model=TokenResponse,
    responses=error_responses(401, 403, 422, 429),
    description="Finish signing in with a passkey (no two-step code needed: the passkey is "
    "already two factors).",
)
async def passkey_sign_in(
    body: PasskeySignIn,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    meta: ClientMetaDep,
    limiter: RateLimiterDep,
) -> TokenResponse:
    _check_origin(request, settings)
    limiter.consume(f"login:ip:{_client_ip(meta)}", LOGIN_PER_IP)
    user = await passkeys.login(session, settings, state=body.state, credential=body.credential)
    result = await auth_service.signed_in(session, settings, user, meta)
    _set_refresh_cookie(response, settings, result.refresh_token)
    return _token_response(result)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={
        204: {"description": "No refresh cookie: nobody is signed in on this browser"},
        **error_responses(401, 403, 429),
    },
    description="Rotates the refresh cookie and returns a new access token. "
    "Re-using an already rotated refresh token revokes the whole token family. Without a "
    "refresh cookie the answer is 204, so a visitor's page load is not an error.",
)
async def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    meta: ClientMetaDep,
    limiter: RateLimiterDep,
) -> TokenResponse | Response:
    _check_origin(request, settings)
    limiter.consume(f"refresh:ip:{_client_ip(meta)}", REFRESH_PER_IP)
    token = _refresh_cookie(request, settings)
    if token is None:
        return Response(status_code=204)  # a visitor: nothing to restore
    try:
        result = await auth_service.refresh(session, settings, token, meta)
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


# --- Sign in with Google / Apple --------------------------------------------------------

OAUTH_COOKIE = "oauth_state"


@router.get("/oauth/providers", response_model=OAuthProviders)
async def oauth_providers(settings: SettingsDep) -> OAuthProviders:
    """The outside sign-in methods this library has set up (shown on the sign-in page)."""
    return OAuthProviders(providers=list(oauth.providers(settings)))


@router.get(
    "/oauth/{provider}/start",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    responses=error_responses(400, 429),
)
async def oauth_start(
    provider: str,
    settings: SettingsDep,
    meta: ClientMetaDep,
    limiter: RateLimiterDep,
    next_path: Annotated[str | None, Query(alias="next", max_length=500)] = None,
) -> RedirectResponse:
    """Send the browser to the provider; it comes back to the callback."""
    limiter.consume(f"oauth:ip:{_client_ip(meta)}", LOGIN_PER_IP)
    started = oauth.start(settings, provider, next_path)
    response = RedirectResponse(started.url, status_code=status.HTTP_302_FOUND)
    # Apple posts the answer back from its own site: the cookie must be sent cross-site then.
    cross_site = provider == "apple" and settings.cookie_secure
    response.set_cookie(
        OAUTH_COOKIE,
        started.state_cookie,
        max_age=int(oauth.STATE_TTL.total_seconds()),
        path=f"{API_PREFIX}/auth/oauth",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="none" if cross_site else "lax",
    )
    return response


async def _oauth_finish(
    provider: str,
    request: Request,
    session: AsyncSession,
    settings: Settings,
    meta: ClientMeta,
    *,
    state: str | None,
    code: str | None,
    error: str | None,
    apple_user: str | None = None,
) -> RedirectResponse:
    app_url = settings.app_base_url
    try:
        if error:
            raise oauth.OAuthError("Signing in was cancelled", code="OAUTH_CANCELLED")
        done = await oauth.finish(
            session,
            settings,
            request.app.state.http,
            provider,
            state_cookie=request.cookies.get(OAUTH_COOKIE),
            state=state,
            code=code,
            apple_user=apple_user,
        )
        if not done.user.is_active:
            raise PermissionDeniedError("This account has been disabled", code="ACCOUNT_DISABLED")
        if done.user.mfa_enabled:
            # The code from the authenticator app is still needed: finish on the sign-in page.
            await session.commit()
            token = mfa.challenge(settings, done.user)
            response = RedirectResponse(f"{app_url}/login#mfa={token}", status_code=303)
        else:
            result = await auth_service.signed_in(session, settings, done.user, meta)
            response = RedirectResponse(f"{app_url}{done.next_path}", status_code=303)
            _set_refresh_cookie(response, settings, result.refresh_token)
    except AppError as exc:
        await session.rollback()
        response = RedirectResponse(f"{app_url}/login?oauth_error={exc.code}", status_code=303)
    response.delete_cookie(OAUTH_COOKIE, path=f"{API_PREFIX}/auth/oauth")
    return response


@router.get("/oauth/{provider}/callback", response_class=RedirectResponse, include_in_schema=False)
async def oauth_callback(
    provider: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    meta: ClientMetaDep,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    return await _oauth_finish(
        provider, request, session, settings, meta, state=state, code=code, error=error
    )


@router.post("/oauth/{provider}/callback", response_class=RedirectResponse, include_in_schema=False)
async def oauth_callback_post(
    provider: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    meta: ClientMetaDep,
    state: Annotated[str | None, Form()] = None,
    code: Annotated[str | None, Form()] = None,
    error: Annotated[str | None, Form()] = None,
    user: Annotated[str | None, Form(max_length=2000)] = None,
) -> RedirectResponse:
    """Apple answers with a form POST (response_mode=form_post)."""
    return await _oauth_finish(
        provider,
        request,
        session,
        settings,
        meta,
        state=state,
        code=code,
        error=error,
        apple_user=user,
    )
