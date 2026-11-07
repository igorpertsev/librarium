"""Covers in S3-compatible storage (S3_BUCKET). Needs an S3 test server: TEST_S3_ENDPOINT (the
dev compose file and CI run RustFS); skipped without one."""

from __future__ import annotations

import asyncio
import io
import os
import re
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from minio.error import S3Error
from PIL import Image
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from app.services.media_storage import IMMUTABLE, S3Storage, copy_local_to_s3
from tests.conftest import API, ApiUser, make_settings

ENDPOINT = os.environ.get("TEST_S3_ENDPOINT")
pytestmark = pytest.mark.skipif(not ENDPOINT, reason="TEST_S3_ENDPOINT is not set")


def _s3_values(**extra: Any) -> dict[str, Any]:
    return {
        "s3_endpoint": ENDPOINT,
        "s3_bucket": f"covers-{uuid.uuid4().hex[:12]}",
        "s3_access_key_id": os.environ.get("TEST_S3_ACCESS_KEY", ""),
        "s3_secret_access_key": os.environ.get("TEST_S3_SECRET_KEY", ""),
        "s3_prefix": "library",
        **extra,
    }


async def _ready(storage: S3Storage) -> S3Storage:
    for _ in range(40):  # the server may still be starting
        try:
            await storage.ensure_bucket()
            return storage
        except (S3Error, OSError, ValueError):
            await asyncio.sleep(0.5)
    await storage.ensure_bucket()  # raise the real error
    return storage


MakeS3App = Callable[..., Any]


@pytest.fixture
async def s3_app(database_url: str) -> AsyncIterator[MakeS3App]:
    """An app (and a client for it) that keeps covers in a fresh bucket."""
    made: list[tuple[FastAPI, AsyncClient]] = []

    async def make(**extra: Any) -> tuple[FastAPI, AsyncClient, S3Storage]:
        application = create_app(make_settings(database_url, **_s3_values(**extra)))
        storage = await _ready(application.state.media)
        client = AsyncClient(transport=ASGITransport(app=application), base_url="http://test")
        made.append((application, client))
        return application, client, storage

    yield make
    for application, client in made:
        await client.aclose()
        await application.state.db.dispose()


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (600, 900), (30, 90, 160)).save(buffer, "PNG")
    return buffer.getvalue()


async def _upload(client: AsyncClient, admin: ApiUser, book_id: str) -> str:
    response = await client.post(
        f"{API}/admin/books/{book_id}/cover",
        headers=admin.headers,
        files={"file": ("cover.png", _png(), "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    url: str = response.json()["cover_url"]
    assert re.fullmatch(r"/media/covers/[0-9a-f]{32}-L\.webp", url)
    return url


async def test_covers_go_to_the_bucket_and_are_served_from_it(
    s3_app: MakeS3App, admin: ApiUser
) -> None:
    _, client, storage = await s3_app()
    book = await admin.post(
        f"{API}/admin/books", json={"title": "Dune", "author": "F", "category": "fiction"}
    )
    book_id = book.json()["id"]
    url = await _upload(client, admin, book_id)
    name = url.removeprefix("/media/covers/").removesuffix("-L.webp")
    for size in "SML":  # stored under the prefix, in three sizes
        assert await storage.exists(f"covers/{name}-{size}.webp")
        stat = await asyncio.to_thread(
            storage.client.stat_object, storage.bucket, f"library/covers/{name}-{size}.webp"
        )
        assert stat.content_type == "image/webp"

    served = await client.get(f"/media/covers/{name}-M.webp")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/webp"
    assert served.headers["cache-control"] == IMMUTABLE
    assert Image.open(io.BytesIO(served.content)).size[1] == 400

    # A new cover replaces the old files in the bucket.
    newer = await _upload(client, admin, book_id)
    assert newer != url
    assert not await storage.exists(f"covers/{name}-L.webp")

    assert (await client.get(f"/media/covers/{'0' * 32}-L.webp")).status_code == 404
    assert (await client.get("/media/covers/..%2Fsecret.webp")).status_code == 404
    assert (await client.get("/media/covers/notacover.txt")).status_code == 404


async def test_a_public_bucket_gets_a_permanent_redirect(s3_app: MakeS3App, admin: ApiUser) -> None:
    _, client, _ = await s3_app(media_public_url="https://cdn.example.com/books/")
    book = await admin.post(
        f"{API}/admin/books", json={"title": "Emma", "author": "J", "category": "fiction"}
    )
    url = await _upload(client, admin, book.json()["id"])
    name = url.removeprefix("/media/covers/")
    redirect = await client.get(url)
    assert redirect.status_code == 301
    assert redirect.headers["location"] == f"https://cdn.example.com/books/library/covers/{name}"
    assert redirect.headers["cache-control"] == IMMUTABLE


async def test_covers_on_disk_can_be_copied_to_the_bucket(
    s3_app: MakeS3App, tmp_path: Path
) -> None:
    _, _, storage = await s3_app()
    folder = tmp_path / "covers"
    folder.mkdir()
    for size in "SML":
        (folder / f"{'a' * 32}-{size}.webp").write_bytes(b"webp-" + size.encode())
    (folder / "notes.txt").write_text("not a cover")

    assert await copy_local_to_s3(str(tmp_path), storage) == (3, 0)
    assert await copy_local_to_s3(str(tmp_path), storage) == (0, 3)  # nothing twice
    assert await storage.get(f"covers/{'a' * 32}-M.webp") == b"webp-M"


def test_a_bucket_needs_an_endpoint_and_keys() -> None:
    with pytest.raises(ValidationError, match="S3_BUCKET needs"):
        Settings(_env_file=None, s3_bucket="covers")
    with pytest.raises(ValidationError, match="MEDIA_PUBLIC_URL must start"):
        Settings(_env_file=None, media_public_url="cdn.example.com")
