"""NUL characters and broken Unicode get a 422, not a database error (found by API fuzzing)."""

from __future__ import annotations

import json

from httpx import AsyncClient

from tests.conftest import API, ApiUser


async def test_bodies_with_nul_or_lone_surrogates_are_refused(admin: ApiUser) -> None:
    for name in ("Fan\u0000tasy", "Fan\ud957tasy"):
        # Sent as escaped JSON ("\\ud957"), as a client would; httpx cannot encode it itself.
        body = json.dumps({"slug": "fantasy", "name_en": "Fantasy", "name_ru": name})
        response = await admin.client.post(
            f"{API}/admin/tags",
            content=body,
            headers={**admin.headers, "content-type": "application/json"},
        )
        assert response.status_code == 422, (repr(name), response.text)
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    # Nested values are checked too.
    response = await admin.post(
        f"{API}/admin/books",
        json={"title": "T", "author": "A", "category": "fiction", "image_urls": ["x\u0000"]},
    )
    assert response.status_code == 422, response.text

    ok = await admin.post(
        f"{API}/admin/tags", json={"slug": "fantasy", "name_en": "Fantasy 🐉", "name_ru": "Фэнтези"}
    )
    assert ok.status_code == 201, ok.text


async def test_parameters_with_nul_are_refused(client: AsyncClient) -> None:
    for path in ("/books?q=%00", "/books?q=a%00b", "/series?q=%00"):
        response = await client.get(f"{API}{path}")
        assert response.status_code == 422, (path, response.text)
        assert response.json()["error"]["code"] == "INVALID_CHARACTERS"
    assert (await client.get(f"{API}/books", params={"q": "дракон"})).status_code == 200
