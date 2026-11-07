"""Application configuration loaded from environment variables (and an optional ``.env``)."""

from __future__ import annotations

import re
import secrets
from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_JWT_SECRET_LENGTH = 32
MIN_MFA_KEY_LENGTH = 32
KNOWN_WEAK_SECRETS = frozenset(
    {
        "replace-with-a-long-random-secret",
        "secret",
        "changeme",
        "change-me",
        "jwt-secret",
        "your-secret-key",
        "supersecret",
    }
)


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Environment = Environment.DEVELOPMENT
    app_name: str = "Librarium API"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # "json" (one JSON object per line) or "text"; default: json in production, text otherwise.
    log_format: Literal["json", "text"] | None = None
    # Optional error reporting to Sentry (or a compatible service such as GlitchTip).
    sentry_dsn: SecretStr | None = None

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/bookstore"
    database_echo: bool = False
    database_pool_size: int = Field(default=10, ge=1, le=100)

    jwt_secret_key: SecretStr | None = None
    # Keys that encrypt the two-step sign-in secrets, comma-separated. The first one encrypts, all
    # of them decrypt: to rotate, put a new key first, run `python -m app.cli rotate-mfa-keys`,
    # then remove the old key. Unset, a key derived from JWT_SECRET_KEY is used (as before), so
    # changing JWT_SECRET_KEY would turn two-step sign-in off for everybody.
    mfa_encryption_keys: SecretStr | None = None
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "librarium-api"
    jwt_audience: str = "librarium-web"
    access_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_expire_days: int = Field(default=30, ge=1, le=180)

    refresh_cookie_name: str = "refresh_token"
    refresh_cookie_path: str = "/api/v1/auth"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None

    # Comma-separated list of exact origins allowed to call the API with credentials.
    frontend_origins: str = "http://localhost:5173"

    # Limits on login, registration, token refresh and password changes (app.core.rate_limit).
    rate_limit_enabled: bool = True

    # Customer email notifications (sent by `python -m app.cli notifications`).
    # Leave SMTP_HOST empty to disable sending; notifications then stay queued.
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    mail_from: str = "Little Dragon Library <no-reply@localhost>"
    # Public URL of the frontend, used for links in emails.
    app_base_url: str = "http://localhost:5173"
    # Uploaded book covers (served at /media); a volume in Docker.
    media_dir: str = "media"
    # Sign in with Google / Apple (optional, see app.services.oauth). The backend's public URL
    # (for the callback address the providers send people back to) defaults to
    # APP_BASE_URL + /api/v1, which fits a single domain behind Caddy.
    api_public_url: str | None = None
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    apple_client_id: str | None = None
    apple_team_id: str | None = None
    apple_key_id: str | None = None
    apple_private_key: SecretStr | None = None
    # Optional Telegram bot for notifications (see app.services.telegram).
    telegram_bot_token: SecretStr | None = None
    telegram_bot_username: str | None = None
    # Webhook mode (optional): Telegram posts updates to /api/v1/telegram/webhook with this secret
    # in X-Telegram-Bot-Api-Secret-Token, instead of the notifier polling getUpdates. Register it
    # with `python -m app.cli telegram-webhook set`.
    telegram_webhook_secret: SecretStr | None = None
    max_cover_bytes: int = 5 * 1024 * 1024
    # Lifetime of the link in password reset emails.
    password_reset_expire_minutes: int = Field(default=60, ge=5, le=24 * 60)
    due_soon_days: int = Field(default=3, ge=0, le=30)

    # Machine translation of book titles and descriptions (admin "Find translation" and
    # `python -m app.cli translate-books`) when Wikidata and Wikipedia have none. Optional:
    # without a key only Wikidata and Wikipedia are used.
    anthropic_api_key: SecretStr | None = None
    # Uptime monitoring (optional): the email worker calls this URL after every cycle, so a
    # "dead man's switch" check (e.g. healthchecks.io) alerts you when it stops.
    notifier_ping_url: str | None = None
    translation_model: str = "claude-opus-5-5"

    # Seed command inputs. Never hard-code production credentials.
    seed_admin_email: str | None = None
    seed_admin_password: SecretStr | None = None
    seed_admin_name: str = "Administrator"

    # Set when no secret was configured outside production; tokens die with the process.
    jwt_secret_is_ephemeral: bool = Field(default=False, exclude=True)

    @field_validator("database_url")
    @classmethod
    def _force_async_driver(cls, value: str) -> str:
        if value.startswith("postgres://"):
            value = "postgresql://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL (postgresql+asyncpg://...)")
        return value

    @field_validator("apple_private_key", mode="before")
    @classmethod
    def _real_line_breaks(cls, value: object) -> object:
        """A .p8 key written on one line in .env, with "\\n" for the line breaks."""
        if isinstance(value, str) and "\\n" in value and "\n" not in value:
            return value.replace("\\n", "\n")
        return value

    @field_validator("app_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator(
        "cookie_domain",
        "seed_admin_email",
        "smtp_host",
        "smtp_username",
        "notifier_ping_url",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "jwt_secret_key",
        "mfa_encryption_keys",
        "telegram_webhook_secret",
        "seed_admin_password",
        "smtp_password",
        "sentry_dsn",
        "anthropic_api_key",
        mode="before",
    )
    @classmethod
    def _empty_secret_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _validate_security(self) -> Settings:
        origins = self.cors_origins
        if "*" in origins:
            raise ValueError("FRONTEND_ORIGINS must list explicit origins; '*' is not allowed")
        for origin in origins:
            if not origin.startswith(("http://", "https://")) or origin.endswith("/"):
                raise ValueError(
                    f"Invalid origin {origin!r}: expected scheme://host[:port] without a path"
                )

        if self.smtp_ssl and self.smtp_starttls:
            raise ValueError("Use either SMTP_SSL (implicit TLS) or SMTP_STARTTLS, not both")

        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")

        secret = self.jwt_secret_key.get_secret_value() if self.jwt_secret_key else None
        if self.environment is Environment.PRODUCTION:
            if secret is None:
                raise ValueError("JWT_SECRET_KEY is required in production")
            if len(secret) < MIN_JWT_SECRET_LENGTH or secret.lower() in KNOWN_WEAK_SECRETS:
                raise ValueError(
                    f"JWT_SECRET_KEY is too weak: use at least {MIN_JWT_SECRET_LENGTH} random "
                    "characters, e.g. secrets.token_urlsafe(64)"
                )
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
            if any(o.startswith("http://") for o in origins):
                raise ValueError("FRONTEND_ORIGINS must use https:// in production")
        elif secret is None:
            self.jwt_secret_key = SecretStr(secrets.token_urlsafe(64))
            self.jwt_secret_is_ephemeral = True

        if self.log_format is None:
            self.log_format = "json" if self.environment is Environment.PRODUCTION else "text"
        return self

    @model_validator(mode="after")
    def _validate_telegram_webhook(self) -> Settings:
        secret = self.telegram_webhook_secret
        if secret is not None and not re.fullmatch(
            r"[A-Za-z0-9_-]{32,256}", secret.get_secret_value()
        ):
            raise ValueError(
                "TELEGRAM_WEBHOOK_SECRET must be 32 to 256 letters, digits, '_' or '-', "
                "e.g. secrets.token_urlsafe(32)"
            )
        if secret is not None and not self.telegram_bot_token:
            raise ValueError("TELEGRAM_WEBHOOK_SECRET needs TELEGRAM_BOT_TOKEN")
        return self

    @model_validator(mode="after")
    def _validate_mfa_keys(self) -> Settings:
        if any(len(key) < MIN_MFA_KEY_LENGTH for key in self.mfa_keys):
            raise ValueError(
                f"Every MFA_ENCRYPTION_KEYS key needs at least {MIN_MFA_KEY_LENGTH} random "
                "characters, e.g. secrets.token_urlsafe(32)"
            )
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]

    @property
    def public_api_url(self) -> str:
        return (self.api_public_url or f"{self.app_base_url}/api/v1").rstrip("/")

    @property
    def jwt_secret(self) -> str:
        if self.jwt_secret_key is None:  # pragma: no cover - guarded by the validator
            raise RuntimeError("JWT secret is not configured")
        return self.jwt_secret_key.get_secret_value()

    @property
    def mfa_keys(self) -> list[str]:
        """MFA_ENCRYPTION_KEYS as a list, the encrypting key first."""
        raw = self.mfa_encryption_keys.get_secret_value() if self.mfa_encryption_keys else ""
        return [key.strip() for key in raw.split(",") if key.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()
