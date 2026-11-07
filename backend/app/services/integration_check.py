"""Live checks of the configured integrations (``python -m app.cli check-integrations``).

Run it on a server (staging first) after setting up ``.env``: every configured service is
contacted for real - without sending email, posting messages or keeping files - and each check
says OK, FAIL (with the reason) or SKIP (not configured). Secrets are never printed.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import smtplib
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

import httpx
from alembic.config import Config
from alembic.script import ScriptDirectory
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import text

from app.core.config import Settings
from app.core.database import Database
from app.services import telegram
from app.services.media_storage import S3Storage
from app.services.oauth import _apple_client_secret
from app.services.web_push import b64url_decode, b64url_encode

Status = Literal["ok", "fail", "skip"]


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: Status
    detail: str


Check = Callable[[Settings, httpx.AsyncClient], Awaitable[CheckResult]]


def _ok(name: str, detail: str) -> CheckResult:
    return CheckResult(name, "ok", detail)


def _fail(name: str, detail: str) -> CheckResult:
    return CheckResult(name, "fail", detail)


def _skip(name: str, detail: str = "not configured") -> CheckResult:
    return CheckResult(name, "skip", detail)


async def check_database(settings: Settings, http: httpx.AsyncClient) -> CheckResult:
    db = Database(settings)
    try:
        async with db.engine.connect() as conn:
            current = await conn.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        return _fail("Database", f"cannot read it: {type(exc).__name__}")
    finally:
        await db.dispose()
    logging.getLogger("alembic").setLevel(logging.WARNING)  # no plugin chatter in the report
    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    if current != head:
        return _fail("Database", f"migration {current}, expected {head}: run the migrate service")
    return _ok("Database", f"reachable, migrations up to date ({head})")


async def check_public_site(settings: Settings, http: httpx.AsyncClient) -> CheckResult:
    """The public addresses answer from the outside (DNS, TLS, Caddy, backend)."""
    try:
        api = await http.get(f"{settings.public_api_url}/health", timeout=15)
        app = await http.get(settings.app_base_url, timeout=15)
    except httpx.HTTPError as exc:
        return _fail("Public site", f"not reachable: {type(exc).__name__}")
    if api.status_code != 200 or app.status_code != 200:
        return _fail(
            "Public site",
            f"API_PUBLIC_URL/health {api.status_code}, APP_BASE_URL {app.status_code}",
        )
    return _ok("Public site", f"{settings.app_base_url} and the API answer")


def _smtp_probe(settings: Settings) -> str:
    host = settings.smtp_host or ""
    context = ssl.create_default_context()
    smtp: smtplib.SMTP
    if settings.smtp_ssl:
        smtp = smtplib.SMTP_SSL(host, settings.smtp_port, timeout=15, context=context)
    else:
        smtp = smtplib.SMTP(host, settings.smtp_port, timeout=15)
    with smtp:
        smtp.ehlo()
        if settings.smtp_starttls and not settings.smtp_ssl:
            smtp.starttls(context=context)
            smtp.ehlo()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            return "connected and signed in (nothing sent)"
    return "connected (nothing sent)"


async def check_smtp(settings: Settings, http: httpx.AsyncClient) -> CheckResult:
    if not settings.smtp_host:
        return _skip("Email (SMTP)")
    try:
        return _ok("Email (SMTP)", await asyncio.to_thread(_smtp_probe, settings))
    except (OSError, smtplib.SMTPException) as exc:
        return _fail("Email (SMTP)", f"{type(exc).__name__}: {str(exc)[:120]}")


async def check_telegram(settings: Settings, http: httpx.AsyncClient) -> CheckResult:
    bot = telegram.make_bot(settings, http)
    if bot is None:
        return _skip("Telegram")
    try:
        me = await bot._call("getMe", {})
        info = await bot.webhook_info()
    except telegram.TelegramError as exc:
        return _fail("Telegram", f"the bot token does not work: {exc}")
    username = str(me.get("username", ""))
    if (
        settings.telegram_bot_username
        and username.lower() != settings.telegram_bot_username.lower()
    ):
        return _fail(
            "Telegram", f"the token belongs to @{username}, not @{settings.telegram_bot_username}"
        )
    problem, mode = _webhook_state(settings, info)
    if problem:
        return _fail("Telegram", problem)
    return _ok("Telegram", f"@{username}, {mode}")


def _webhook_state(settings: Settings, info: dict[str, object]) -> tuple[str | None, str]:
    """A problem with how updates arrive (if any), and how they arrive."""
    expected = f"{settings.public_api_url}/telegram/webhook"
    if settings.telegram_webhook_secret is not None:
        if info.get("url") != expected:
            return "webhook mode, but the webhook is not registered: run telegram-webhook set", ""
        if info.get("last_error_message"):
            return f"Telegram reports: {info['last_error_message']}", ""
        return None, f"webhook at {expected}"
    if info.get("url"):
        return "a webhook is set but polling is configured: run telegram-webhook delete", ""
    return None, "polling"


async def check_google(settings: Settings, http: httpx.AsyncClient) -> CheckResult:
    if not (settings.google_client_id and settings.google_client_secret):
        return _skip("Google sign-in")
    if not settings.google_client_id.endswith(".apps.googleusercontent.com"):
        return _fail("Google sign-in", "GOOGLE_CLIENT_ID does not look like a Google client id")
    try:
        keys = await http.get("https://www.googleapis.com/oauth2/v3/certs", timeout=15)
        keys.raise_for_status()
    except httpx.HTTPError as exc:
        return _fail("Google sign-in", f"Google's keys cannot be fetched: {type(exc).__name__}")
    callback = f"{settings.public_api_url}/auth/oauth/google/callback"
    return _ok("Google sign-in", f"keys reachable; register this callback: {callback}")


async def check_apple(settings: Settings, http: httpx.AsyncClient) -> CheckResult:
    if not (
        settings.apple_client_id
        and settings.apple_team_id
        and settings.apple_key_id
        and settings.apple_private_key
    ):
        return _skip("Apple sign-in")
    try:
        _apple_client_secret(settings)
    except Exception as exc:  # noqa: BLE001 - a bad key shows up as any of several errors
        return _fail("Apple sign-in", f"APPLE_PRIVATE_KEY cannot sign: {type(exc).__name__}")
    try:
        keys = await http.get("https://appleid.apple.com/auth/keys", timeout=15)
        keys.raise_for_status()
    except httpx.HTTPError as exc:
        return _fail("Apple sign-in", f"Apple's keys cannot be fetched: {type(exc).__name__}")
    callback = f"{settings.public_api_url}/auth/oauth/apple/callback"
    return _ok("Apple sign-in", f"key signs, Apple reachable; register this callback: {callback}")


async def check_s3(settings: Settings, http: httpx.AsyncClient) -> CheckResult:
    if not settings.s3_bucket:
        return _skip("Covers in S3")
    storage = S3Storage(settings)
    key = f"healthcheck/{secrets.token_hex(8)}.txt"
    try:
        await storage.put(key, b"ok", "text/plain")
        read = await storage.get(key)
        public = storage.public_url(key)
        public_ok = None
        if public:
            response = await http.get(public, timeout=15)
            public_ok = response.status_code == 200 and response.content == b"ok"
        await storage.delete(key)
    except Exception as exc:  # noqa: BLE001 - the S3 client raises many kinds
        return _fail("Covers in S3", f"{type(exc).__name__}: {str(exc)[:120]}")
    if read != b"ok":
        return _fail("Covers in S3", "a file written could not be read back")
    if public_ok is False:
        return _fail("Covers in S3", "MEDIA_PUBLIC_URL does not serve the bucket's files")
    where = "public address works" if public_ok else "served by the backend"
    return _ok("Covers in S3", f"bucket {settings.s3_bucket}: write, read, delete; {where}")


async def check_web_push(settings: Settings, http: httpx.AsyncClient) -> CheckResult:
    if not settings.web_push_private_key:
        return _skip("Web Push")
    try:
        raw = b64url_decode(settings.web_push_private_key.get_secret_value())
        key = ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())
        public = b64url_encode(
            key.public_key().public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
            )
        )
    except (ValueError, TypeError) as exc:
        return _fail("Web Push", f"WEB_PUSH_PRIVATE_KEY is not a key: {type(exc).__name__}")
    if public != settings.web_push_public_key:
        return _fail("Web Push", "WEB_PUSH_PUBLIC_KEY does not belong to WEB_PUSH_PRIVATE_KEY")
    return _ok("Web Push", "the key pair matches")


async def check_secrets(settings: Settings, http: httpx.AsyncClient) -> CheckResult:
    if not settings.is_production:
        return _skip("Production secrets", "not production")
    if not settings.mfa_keys:
        return _fail("Production secrets", "set MFA_ENCRYPTION_KEYS (see deploy/README.md)")
    return _ok("Production secrets", "JWT_SECRET_KEY and MFA_ENCRYPTION_KEYS are set")


async def check_sentry(settings: Settings, http: httpx.AsyncClient) -> CheckResult:
    if not settings.sentry_dsn:
        return _skip("Error reporting (Sentry)")
    dsn = urlsplit(settings.sentry_dsn.get_secret_value())
    if dsn.scheme not in ("http", "https") or not dsn.username or not dsn.path.strip("/"):
        return _fail("Error reporting (Sentry)", "SENTRY_DSN does not look like a DSN")
    return _ok("Error reporting (Sentry)", f"reports go to {dsn.hostname}")


CHECKS: tuple[Check, ...] = (
    check_database,
    check_public_site,
    check_secrets,
    check_smtp,
    check_telegram,
    check_google,
    check_apple,
    check_s3,
    check_web_push,
    check_sentry,
)


async def run_checks(
    settings: Settings, http: httpx.AsyncClient, checks: tuple[Check, ...] = CHECKS
) -> list[CheckResult]:
    return [await check(settings, http) for check in checks]
