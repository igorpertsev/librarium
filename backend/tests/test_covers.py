from __future__ import annotations

import io
import re
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from PIL import Image

from tests.conftest import API, ApiUser


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (200, 120, 40)).save(buffer, "PNG")
    return buffer.getvalue()


async def _upload(admin: ApiUser, book_id: str, data: bytes, name: str = "cover.png") -> Any:
    return await admin.client.post(
        f"{API}/admin/books/{book_id}/cover",
        headers=admin.headers,
        files={"file": (name, data, "application/octet-stream")},
    )


async def test_an_uploaded_cover_is_stored_in_three_sizes_for_every_copy(
    app: FastAPI, admin: ApiUser, client: AsyncClient
) -> None:
    created = await admin.post(
        f"{API}/admin/books", json={"title": "Dune", "author": "F", "category": "fiction"}
    )
    dune = created.json()["id"]
    copy_id = (await admin.post(f"{API}/admin/books/{dune}/copies", json={"count": 1})).json()[0][
        "id"
    ]

    uploaded = await _upload(admin, dune, _png(1200, 1800))
    assert uploaded.status_code == 200, uploaded.text
    cover = uploaded.json()["cover_url"]
    assert re.fullmatch(r"/media/covers/[0-9a-f]{32}-L\.webp", cover)
    assert uploaded.json()["image_urls"][0] == cover
    assert (await admin.get(f"{API}/admin/books/{copy_id}")).json()["cover_url"] == cover

    large = await client.get(cover)
    assert large.status_code == 200
    assert large.headers["content-type"] == "image/webp"
    assert "immutable" in large.headers["cache-control"]
    small = await client.get(cover.replace("-L.webp", "-S.webp"))
    with Image.open(io.BytesIO(small.content)) as image:
        assert image.size == (107, 160)  # aspect ratio kept

    # A new cover replaces the old files.
    again = (await _upload(admin, dune, _png(600, 900))).json()["cover_url"]
    assert again != cover
    assert (await client.get(cover)).status_code == 404

    # The stored path is accepted when the book form is saved again; other paths are not.
    kept = await admin.patch(f"{API}/admin/books/{dune}", json={"cover_url": again})
    assert kept.status_code == 200
    odd = await admin.patch(f"{API}/admin/books/{dune}", json={"cover_url": "/etc/passwd"})
    assert odd.status_code == 422

    share = await client.get(f"{API}/share/books/{dune}")
    assert f'content="http://localhost:5173{again}"' in share.text


async def test_files_that_are_not_images_or_too_large_are_refused(admin: ApiUser) -> None:
    created = await admin.post(
        f"{API}/admin/books", json={"title": "Emma", "author": "J", "category": "fiction"}
    )
    emma = created.json()["id"]
    text = await _upload(admin, emma, b"just some text", "notes.txt")
    assert (text.status_code, text.json()["error"]["code"]) == (400, "INVALID_IMAGE")
    huge = await _upload(admin, emma, b"\0" * (5 * 1024 * 1024 + 1))
    assert (huge.status_code, huge.json()["error"]["code"]) == (413, "IMAGE_TOO_LARGE")
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    refused = await _upload(admin, emma, gif.getvalue(), "x.gif")
    assert refused.json()["error"]["code"] == "INVALID_IMAGE"
