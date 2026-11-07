from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from tests.conftest import API, ApiUser, CreateBook, SetBatch, fill_cart, place_order

LOG = f"{API}/users/me/reading-log"


async def _book(admin: ApiUser, title: str, **extra: Any) -> str:
    body = {"title": title, "author": "A. Writer", "category": "fiction", **extra}
    created = await admin.post(f"{API}/admin/books", json=body)
    assert created.status_code == 201, created.text
    book_id: str = created.json()["id"]
    return book_id


def _badges(log: dict[str, Any]) -> dict[str, tuple[bool, int, int]]:
    return {b["key"]: (b["earned"], b["progress"], b["goal"]) for b in log["badges"]}


def _months_ago(months: int) -> date:
    today = datetime.now(UTC).date().replace(day=1)
    for _ in range(months):
        today = (today - timedelta(days=1)).replace(day=1)
    return today


async def test_finished_books_count_towards_badges(admin: ApiUser, customer: ApiUser) -> None:
    fiction = await _book(admin, "Fiction one", language="en")
    poems = await _book(admin, "Poems", category="history", language="ru")
    facts = await _book(admin, "Facts", category="non-fiction")
    empty = (await customer.get(LOG)).json()
    assert (empty["total"], _badges(empty)["first_book"]) == (0, (False, 0, 1))

    # Three titles in three months, three categories and two languages.
    for book_id, day in (
        (fiction, _months_ago(0)),
        (poems, _months_ago(1)),
        (facts, _months_ago(2)),
    ):
        marked = await customer.put(f"{LOG}/{book_id}", json={"finished_on": day.isoformat()})
        assert marked.status_code == 204, marked.text
    log = (await customer.get(LOG)).json()
    assert log["total"] == 3
    assert [e["book"]["title"] for e in log["entries"]] == ["Fiction one", "Poems", "Facts"]
    badges = _badges(log)
    assert badges["first_book"] == (True, 1, 1)
    assert badges["five_books"] == (False, 3, 5)
    assert badges["explorer"] == (True, 3, 3)
    assert badges["two_languages"] == (True, 2, 2)
    assert badges["three_months"] == (True, 3, 3)

    # Taking a title off the log takes its badges away again.
    assert (await customer.delete(f"{LOG}/{poems}")).status_code == 204
    badges = _badges((await customer.get(LOG)).json())
    assert badges["two_languages"] == (False, 1, 2)
    assert badges["explorer"][0] is False


async def test_a_title_is_logged_once_and_never_in_the_future(
    admin: ApiUser, customer: ApiUser
) -> None:
    dune = await _book(admin, "Dune")
    second_copy = (await admin.post(f"{API}/admin/books/{dune}/copies", json={"count": 1})).json()
    assert (await customer.put(f"{LOG}/{dune}")).status_code == 204
    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    await customer.put(f"{LOG}/{second_copy[0]['id']}", json={"finished_on": yesterday})
    log = (await customer.get(LOG)).json()
    assert log["total"] == 1
    assert log["entries"][0]["finished_on"] == yesterday
    tomorrow = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    future = await customer.put(f"{LOG}/{dune}", json={"finished_on": tomorrow})
    assert future.json()["error"]["code"] == "INVALID_FINISHED_ON"


async def test_finishing_a_series_and_borrowed_books_to_log(
    admin: ApiUser, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    first = await _book(admin, "Saga 1", series_name="Saga", series_position=1)
    second = await _book(admin, "Saga 2", series_name="Saga", series_position=2)
    await customer.put(f"{LOG}/{first}")
    assert _badges((await customer.get(LOG)).json())["series_finisher"][0] is False
    await customer.put(f"{LOG}/{second}")
    assert _badges((await customer.get(LOG)).json())["series_finisher"] == (True, 1, 1)

    # Borrowed titles are offered for the log until they are in it.
    await set_batch(1)
    emma = await create_book("Emma")
    await fill_cart(customer, [emma])
    order = (await place_order(customer)).json()
    await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})
    assert [b["title"] for b in (await customer.get(LOG)).json()["to_log"]] == ["Emma"]
    await customer.put(f"{LOG}/{emma}")
    log = (await customer.get(LOG)).json()
    assert log["to_log"] == []
    exported = (await customer.get(f"{API}/users/me/export")).json()
    assert sorted(item["title"] for item in exported["reading_log"]) == ["Emma", "Saga 1", "Saga 2"]
