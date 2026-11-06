from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import API, ApiUser, CreateBook


async def test_the_catalogue_answers_not_modified_until_it_changes(
    client: AsyncClient, admin: ApiUser, create_book: CreateBook
) -> None:
    await create_book("Dune")
    first = await client.get(f"{API}/books")
    etag = first.headers["etag"]
    assert first.headers["cache-control"] == "no-cache"

    same = await client.get(f"{API}/books", headers={"If-None-Match": etag})
    assert same.status_code == 304
    assert same.content == b""

    await create_book("Emma")
    changed = await client.get(f"{API}/books", headers={"If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.headers["etag"] != etag
    assert [b["title"] for b in changed.json()["items"]] == ["Dune", "Emma"]

    # Only the public catalogue: personal and admin data are not tagged.
    assert "etag" not in (await admin.get(f"{API}/admin/books")).headers
    assert "etag" not in (await admin.get(f"{API}/cart")).headers
    missing = await client.get(f"{API}/books/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
    assert "etag" not in missing.headers
