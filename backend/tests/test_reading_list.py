from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import API, ApiUser


async def _book(admin: ApiUser, title: str) -> dict[str, Any]:
    response = await admin.post(
        f"{API}/admin/books", json={"title": title, "author": "Ann Author", "category": "fiction"}
    )
    assert response.status_code == 201, response.text
    book: dict[str, Any] = response.json()
    return book


async def test_reading_list_keeps_titles_for_later(
    admin: ApiUser, customer: ApiUser, client: AsyncClient
) -> None:
    dune = await _book(admin, "Dune")
    emma = await _book(admin, "Emma")
    copies = (await admin.post(f"{API}/admin/books/{dune['id']}/copies", json={"count": 1})).json()

    for book_id in (dune["id"], emma["id"], copies[0]["id"]):  # the copy is the same title
        response = await customer.post(f"{API}/reading-list/{book_id}")
        assert response.status_code == 204, response.text
    items = (await customer.get(f"{API}/reading-list")).json()
    assert [item["book"]["title"] for item in items] == ["Emma", "Dune"]  # newest first
    assert items[1]["book"]["copies"] == 2

    # The list shows a copy that can be borrowed now.
    await customer.post(f"{API}/cart/items", json={"book_id": dune["id"]})
    assert (await customer.get(f"{API}/reading-list")).json()[1]["book"]["is_available"] is True

    # Removing any copy removes the title; others' lists are separate.
    assert (await customer.delete(f"{API}/reading-list/{copies[0]['id']}")).status_code == 204
    assert [i["book"]["title"] for i in (await customer.get(f"{API}/reading-list")).json()] == [
        "Emma"
    ]
    assert (await admin.get(f"{API}/reading-list")).json() == []
    assert (await client.get(f"{API}/reading-list")).status_code == 401
    missing = await customer.post(f"{API}/reading-list/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
