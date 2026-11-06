from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import API, ApiUser, SetBatch, fill_cart, place_order


async def _volume(admin: ApiUser, title: str, position: float | None, series: str) -> str:
    payload: dict[str, Any] = {
        "title": title,
        "author": "J.K. Rowling",
        "category": "fiction",
        "series_name": series,
    }
    if position is not None:
        payload["series_position"] = position
    response = await admin.post(f"{API}/admin/books", json=payload)
    assert response.status_code == 201, response.text
    book_id: str = response.json()["id"]
    return book_id


async def test_the_dialog_can_step_through_a_series(admin: ApiUser, client: AsyncClient) -> None:
    one = await _volume(admin, "Stone", 1, "Potter")
    two = await _volume(admin, "Chamber", 2, "Potter")
    await _volume(admin, "Azkaban", 3, "Potter")
    await _volume(admin, "Companion", None, "Potter")
    await admin.post(f"{API}/admin/books/{two}/copies", json={"count": 1})

    middle = (await client.get(f"{API}/books/{two}/series-neighbours")).json()
    assert (middle["previous"]["title"], middle["next"]["title"]) == ("Stone", "Azkaban")
    first = (await client.get(f"{API}/books/{one}/series-neighbours")).json()
    assert (first["previous"], first["next"]["title"]) == (None, "Chamber")
    alone = await admin.post(
        f"{API}/admin/books", json={"title": "Solo", "author": "A", "category": "fiction"}
    )
    solo = (await client.get(f"{API}/books/{alone.json()['id']}/series-neighbours")).json()
    assert solo == {"previous": None, "next": None}


async def test_readers_are_offered_the_next_volume(
    admin: ApiUser, customer: ApiUser, set_batch: SetBatch
) -> None:
    await set_batch(1)
    one = await _volume(admin, "Stone", 1, "Potter")
    await _volume(admin, "Chamber", 2, "Potter")
    three = await _volume(admin, "Azkaban", 3, "Potter")
    games = await _volume(admin, "Hunger Games", 1, "Panem")
    await _volume(admin, "Catching Fire", 2, "Panem")

    assert (await customer.get(f"{API}/users/me/next-in-series")).json() == []
    for book_id in (one, three, games):
        await fill_cart(customer, [book_id])
        assert (await place_order(customer)).status_code == 201
    # Volume 3 was borrowed, so Potter continues after it (none left); Panem continues with 2.
    titles = [b["title"] for b in (await customer.get(f"{API}/users/me/next-in-series")).json()]
    assert titles == ["Catching Fire"]
