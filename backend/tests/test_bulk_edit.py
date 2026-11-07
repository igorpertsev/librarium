from __future__ import annotations

from typing import Any

from tests.conftest import API, ApiUser

BULK = f"{API}/admin/books/bulk"


async def _book(admin: ApiUser, title: str, **extra: Any) -> str:
    body = {"title": title, "author": "A", "category": "fiction", **extra}
    created = await admin.post(f"{API}/admin/books", json=body)
    assert created.status_code == 201, created.text
    book_id: str = created.json()["id"]
    return book_id


async def _get(admin: ApiUser, book_id: str) -> dict[str, Any]:
    book: dict[str, Any] = (await admin.get(f"{API}/admin/books/{book_id}")).json()
    return book


async def test_one_change_for_every_copy_of_the_chosen_titles(
    admin: ApiUser, customer: ApiUser
) -> None:
    for slug, en in (("space", "Space"), ("classic", "Classic")):
        await admin.post(f"{API}/admin/tags", json={"slug": slug, "name_en": en, "name_ru": en})
    dune = await _book(admin, "Dune", tags=["classic"])
    copy_id = (await admin.post(f"{API}/admin/books/{dune}/copies", json={"count": 1})).json()[0][
        "id"
    ]
    emma = await _book(admin, "Emma")
    untouched = await _book(admin, "Hamlet")

    done = await admin.post(
        BULK,
        json={
            "book_ids": [dune, emma],
            "status": "not-available",
            "category": "science",
            "condition": "worn",
            "add_tags": ["space"],
            "remove_tags": ["classic"],
        },
    )
    assert done.status_code == 200, done.text
    assert done.json() == {"titles": 2, "copies": 3}
    for book_id in (dune, copy_id, emma):
        book = await _get(admin, book_id)
        assert (book["status"], book["category"], book["condition"]) == (
            "not-available",
            "science",
            "worn",
        )
        assert [t["slug"] for t in book["tags"]] == ["space"]
    assert (await _get(admin, untouched))["status"] == "available"

    # All or nothing: an unknown tag changes nothing.
    refused = await admin.post(
        BULK, json={"book_ids": [untouched], "status": "not-available", "add_tags": ["nope"]}
    )
    assert refused.json()["error"]["code"] == "UNKNOWN_TAGS"
    assert (await _get(admin, untouched))["status"] == "available"
    nothing = await admin.post(BULK, json={"book_ids": [untouched]})
    assert nothing.status_code == 422

    # Removing titles takes them out of the catalogue and out of carts.
    assert (
        await customer.post(f"{API}/cart/items", json={"book_id": untouched})
    ).status_code == 200
    removed = await admin.post(BULK, json={"book_ids": [untouched], "deactivate": True})
    assert removed.json() == {"titles": 1, "copies": 1}
    assert (await customer.get(f"{API}/cart")).json()["items"] == []
    listed = (await customer.get(f"{API}/books", params={"q": "Hamlet"})).json()
    assert listed["items"] == []
    log = (await admin.get(f"{API}/admin/audit")).json()["items"]
    assert log[0]["action"] == "admin_bulk_update_books"
