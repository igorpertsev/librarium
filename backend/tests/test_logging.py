from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Environment
from app.core.logging import JsonFormatter, RequestIdFilter, new_request_id, request_id_var
from app.main import create_app
from tests.conftest import API, make_settings


async def test_every_response_carries_a_request_id(client: AsyncClient) -> None:
    response = await client.get(f"{API}/books")
    generated = response.headers["X-Request-ID"]
    assert len(generated) == 16

    response = await client.get(f"{API}/books", headers={"X-Request-ID": "proxy-id-12345"})
    assert response.headers["X-Request-ID"] == "proxy-id-12345"  # a proxy's id is kept

    response = await client.get(f"{API}/books", headers={"X-Request-ID": "bad id\n<script>"})
    assert response.headers["X-Request-ID"] != "bad id\n<script>"


def test_new_request_id_rejects_malformed_values() -> None:
    assert new_request_id("abc") != "abc"  # too short
    assert new_request_id("x" * 65) != "x" * 65  # too long
    assert new_request_id("ok-id_1.2345") == "ok-id_1.2345"


async def test_requests_are_logged_with_id_status_and_duration(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.request"):
        response = await client.get(f"{API}/books", params={"search": "secret query"})
    (record,) = [r for r in caplog.records if r.name == "app.request"]
    assert record.getMessage() == "GET /api/v1/books 200"
    assert record.status == 200  # type: ignore[attr-defined]
    assert record.duration_ms >= 0  # type: ignore[attr-defined]
    assert "secret query" not in record.path  # type: ignore[attr-defined]
    assert record.request_id == response.headers["X-Request-ID"]  # type: ignore[attr-defined]


def test_json_formatter_writes_one_object_per_line() -> None:
    token = request_id_var.set("abcdef0123456789")
    try:
        record = logging.makeLogRecord(
            {"name": "app.request", "levelno": logging.INFO, "levelname": "INFO",
             "msg": "GET %s", "args": ("/x",), "status": 200}
        )  # fmt: skip
        RequestIdFilter().filter(record)
        line = JsonFormatter().format(record)
    finally:
        request_id_var.reset(token)
    entry = json.loads(line)
    assert entry["message"] == "GET /x"
    assert entry["request_id"] == "abcdef0123456789"
    assert entry["status"] == 200
    assert entry["level"] == "INFO"


def test_log_format_defaults_to_json_in_production(database_url: str) -> None:
    assert make_settings(database_url).log_format == "text"
    production = make_settings(
        database_url,
        environment=Environment.PRODUCTION,
        cookie_secure=True,
        frontend_origins="https://library.example.com",
    )
    assert production.log_format == "json"


async def test_unhandled_errors_return_the_request_id(
    database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    app: FastAPI = create_app(make_settings(database_url))

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("database exploded")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with caplog.at_level(logging.ERROR):
            response = await client.get("/boom")
    await app.state.db.dispose()

    assert response.status_code == 500
    body = response.json()["error"]
    assert body["code"] == "INTERNAL_ERROR"
    assert "exploded" not in body["message"]
    request_id = body["details"]["request_id"]
    assert response.headers["X-Request-ID"] == request_id
    error_logs = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any(getattr(r, "request_id", None) == request_id for r in error_logs)
