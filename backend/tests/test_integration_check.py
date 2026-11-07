"""check-integrations: each configured service is checked live; here against fakes and RustFS."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

from app.core.config import Settings
from app.services import integration_check as checks
from app.services.web_push import generate_keys


def _settings(app: FastAPI, **values: Any) -> Settings:
    settings: Settings = app.state.settings.model_copy(update=values)
    return settings


def _http(answer: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(answer))


def _telegram(username: str, webhook: str = "", error: str = "") -> httpx.AsyncClient:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getMe"):
            return httpx.Response(200, json={"ok": True, "result": {"username": username}})
        info = {"url": webhook, "last_error_message": error} if webhook else {"url": ""}
        return httpx.Response(200, json={"ok": True, "result": info})

    return _http(answer)


async def test_telegram_token_username_and_webhook(app: FastAPI) -> None:
    unset = await checks.check_telegram(_settings(app), _telegram("x"))
    assert unset.status == "skip"
    bot = _settings(app, telegram_bot_token=SecretStr("1:a"), telegram_bot_username="dragon_bot")
    assert (await checks.check_telegram(bot, _telegram("dragon_bot"))).status == "ok"
    wrong = await checks.check_telegram(bot, _telegram("other_bot"))
    assert (wrong.status, "@other_bot" in wrong.detail) == ("fail", True)

    hooked = bot.model_copy(update={"telegram_webhook_secret": SecretStr("s" * 40)})
    expected = f"{hooked.public_api_url}/telegram/webhook"
    missing = await checks.check_telegram(hooked, _telegram("dragon_bot"))
    assert (missing.status, "telegram-webhook set" in missing.detail) == ("fail", True)
    assert (await checks.check_telegram(hooked, _telegram("dragon_bot", expected))).status == "ok"
    failing = await checks.check_telegram(
        hooked, _telegram("dragon_bot", expected, "Wrong response")
    )
    assert failing.status == "fail"
    stale = await checks.check_telegram(bot, _telegram("dragon_bot", expected))
    assert (stale.status, "telegram-webhook delete" in stale.detail) == ("fail", True)


async def test_web_push_keys_must_match(app: FastAPI) -> None:
    public, private = generate_keys()
    other, _ = generate_keys()
    good = _settings(
        app,
        web_push_public_key=public,
        web_push_private_key=SecretStr(private),
        web_push_contact="mailto:a@b.c",
    )
    assert (await checks.check_web_push(good, _http(lambda r: httpx.Response(200)))).status == "ok"
    mixed = good.model_copy(update={"web_push_public_key": other})
    assert (
        await checks.check_web_push(mixed, _http(lambda r: httpx.Response(200)))
    ).status == "fail"


async def test_sign_in_providers_and_public_site(app: FastAPI) -> None:
    ok = _http(lambda r: httpx.Response(200, json={"keys": []}))
    down = _http(lambda r: httpx.Response(502))
    google = _settings(
        app,
        google_client_id="123-abc.apps.googleusercontent.com",
        google_client_secret=SecretStr("x"),
    )
    assert (await checks.check_google(google, ok)).status == "ok"
    assert (await checks.check_google(google, down)).status == "fail"
    odd = google.model_copy(update={"google_client_id": "not-a-google-id"})
    assert (await checks.check_google(odd, ok)).status == "fail"
    assert (await checks.check_apple(_settings(app), ok)).status == "skip"

    assert (await checks.check_public_site(_settings(app), ok)).status == "ok"
    assert (await checks.check_public_site(_settings(app), down)).status == "fail"


async def test_smtp_database_and_secrets(app: FastAPI) -> None:
    http = _http(lambda r: httpx.Response(200))
    assert (await checks.check_smtp(_settings(app, smtp_host=None), http)).status == "skip"
    closed = _settings(app, smtp_host="127.0.0.1", smtp_port=1, smtp_starttls=False)
    assert (await checks.check_smtp(closed, http)).status == "fail"
    database = await checks.check_database(_settings(app), http)
    assert (database.status, "up to date" in database.detail) == ("ok", True)
    assert (await checks.check_secrets(_settings(app), http)).status == "skip"  # not production


@pytest.mark.skipif(not os.environ.get("TEST_S3_ENDPOINT"), reason="TEST_S3_ENDPOINT is not set")
async def test_s3_write_read_delete(app: FastAPI) -> None:
    from app.services.media_storage import S3Storage  # noqa: PLC0415 - only with an S3 server

    values = {
        "s3_endpoint": os.environ["TEST_S3_ENDPOINT"],
        "s3_bucket": "integration-check",
        "s3_access_key_id": os.environ.get("TEST_S3_ACCESS_KEY", ""),
        "s3_secret_access_key": SecretStr(os.environ.get("TEST_S3_SECRET_KEY", "")),
    }
    settings = _settings(app, **values)
    await S3Storage(settings).ensure_bucket()
    http = _http(lambda r: httpx.Response(200))
    result = await checks.check_s3(settings, http)
    assert (result.status, result.detail.startswith("bucket integration-check")) == ("ok", True)
    wrong = settings.model_copy(update={"s3_secret_access_key": SecretStr("wrong-secret-key")})
    assert (await checks.check_s3(wrong, http)).status == "fail"
