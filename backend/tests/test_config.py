from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings

STRONG_SECRET = "s" * 64


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)


def test_production_requires_strong_secret_and_secure_cookies() -> None:
    base: dict[str, Any] = {
        "environment": Environment.PRODUCTION,
        "cookie_secure": True,
        "frontend_origins": "https://library.example",
    }
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY is required"):
        _settings(**base)
    with pytest.raises(ValidationError, match="too weak"):
        _settings(**base, jwt_secret_key="replace-with-a-long-random-secret")
    with pytest.raises(ValidationError, match="too weak"):
        _settings(**base, jwt_secret_key="short")
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        _settings(**{**base, "cookie_secure": False}, jwt_secret_key=STRONG_SECRET)
    with pytest.raises(ValidationError, match="https"):
        _settings(
            **{**base, "frontend_origins": "http://library.example"}, jwt_secret_key=STRONG_SECRET
        )
    ok = _settings(**base, jwt_secret_key=STRONG_SECRET)
    assert ok.jwt_secret == STRONG_SECRET
    assert not ok.jwt_secret_is_ephemeral


def test_development_without_secret_uses_ephemeral_random_secret() -> None:
    first, second = _settings(), _settings()
    assert first.jwt_secret_is_ephemeral
    assert len(first.jwt_secret) >= 64
    assert first.jwt_secret != second.jwt_secret


def test_cors_and_cookie_rules() -> None:
    with pytest.raises(ValidationError, match="explicit origins"):
        _settings(frontend_origins="*")
    with pytest.raises(ValidationError, match="Invalid origin"):
        _settings(frontend_origins="http://localhost:5173/")
    with pytest.raises(ValidationError, match="COOKIE_SECURE=true"):
        _settings(cookie_samesite="none", cookie_secure=False)
    assert _settings(frontend_origins="http://a.test, http://b.test").cors_origins == [
        "http://a.test",
        "http://b.test",
    ]


def test_database_url_is_normalised_to_asyncpg() -> None:
    assert _settings(database_url="postgres://u:p@h/db").database_url == (
        "postgresql+asyncpg://u:p@h/db"
    )
    with pytest.raises(ValidationError, match="PostgreSQL"):
        _settings(database_url="sqlite:///db.sqlite3")
