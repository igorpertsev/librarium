"""Librarians' collections of titles and the book of the month."""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient

from tests.conftest import API, ApiUser, CreateBook

ADMIN = f"{API}/admin/collections"


async def _collection(admin: ApiUser, **values: Any) -> dict[str, Any]:
    response = await admin.post(ADMIN, json={"title_en": "Books about dragons", **values})
    assert response.status_code == 201, response.text
    made: dict[str, Any] = response.json()
    return made


async def test_collections_keep_titles_in_the_librarians_order(
    client: AsyncClient, admin: ApiUser, customer: ApiUser, create_book: CreateBook
) -> None:
    dragons = await _collection(admin, title_ru="Книги о драконах", featured=True)
    assert (dragons["slug"], dragons["book_count"], dragons["books"]) == (
        "books-about-dragons",
        0,
        [],
    )
    again = await _collection(admin)
    assert again["slug"] == "books-about-dragons-2"  # addresses stay unique
    assert (await customer.post(ADMIN, json={"title_en": "Mine"})).status_code == 403

    hobbit = await create_book("The Hobbit")
    eragon = await create_book("Eragon")
    temeraire = await create_book("Temeraire")
    copy = (await admin.post(f"{API}/admin/books/{hobbit}/copies", json={"count": 1})).json()[0]
    order = [eragon, copy["id"], hobbit, temeraire, str(uuid.uuid4())]
    saved = await admin.put(f"{ADMIN}/{dragons['id']}/books", json={"book_ids": order})
    assert saved.status_code == 200, saved.text
    # Each title once (any copy picks it), unknown books skipped, the order kept.
    assert [b["title"] for b in saved.json()["books"]] == ["Eragon", "The Hobbit", "Temeraire"]

    assert (await admin.delete(f"{API}/admin/books/{temeraire}")).status_code == 204  # removed
    page = (await client.get(f"{API}/collections/books-about-dragons")).json()
    assert [b["title"] for b in page["books"]] == ["Eragon", "The Hobbit"]  # hidden ones too
    assert page["title_ru"] == "Книги о драконах"
    listed = (await client.get(f"{API}/collections", params={"featured": True})).json()
    assert [(c["slug"], c["book_count"]) for c in listed] == [("books-about-dragons", 3)]
    assert len((await client.get(f"{API}/collections")).json()) == 2
    assert (await client.get(f"{API}/collections/nothing-here")).status_code == 404

    taken = await admin.patch(f"{ADMIN}/{again['id']}", json={"slug": "books-about-dragons"})
    assert (taken.status_code, taken.json()["error"]["code"]) == (409, "SLUG_TAKEN")
    renamed = await admin.patch(f"{ADMIN}/{again['id']}", json={"slug": "Winter Tales"})
    assert renamed.status_code == 422  # only letters, digits and dashes
    renamed = await admin.patch(f"{ADMIN}/{again['id']}", json={"slug": "winter-tales"})
    assert renamed.json()["slug"] == "winter-tales"

    assert (await admin.delete(f"{ADMIN}/{again['id']}")).status_code == 204
    assert (await client.get(f"{API}/collections/winter-tales")).status_code == 404


async def test_the_book_of_the_month(
    client: AsyncClient, admin: ApiUser, create_book: CreateBook
) -> None:
    assert (await client.get(f"{API}/library/pick")).json() is None
    assert (await client.get(f"{API}/library/rules")).json()["has_pick"] is False
    dune = await create_book("Dune")
    copy = (await admin.post(f"{API}/admin/books/{dune}/copies", json={"count": 1})).json()[0]

    chosen = await admin.put(
        f"{API}/admin/pick",
        json={"book_id": copy["id"], "note_en": "Sand and spice.", "note_ru": "Песок и пряность."},
    )
    assert chosen.status_code == 200, chosen.text
    assert (await client.get(f"{API}/library/rules")).json()["has_pick"] is True
    shown = (await client.get(f"{API}/library/pick")).json()
    assert (shown["book"]["title"], shown["book"]["group_id"]) == ("Dune", dune)
    assert (shown["note_en"], shown["note_ru"]) == ("Sand and spice.", "Песок и пряность.")

    missing = await admin.put(f"{API}/admin/pick", json={"book_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    assert (await admin.delete(f"{API}/admin/pick")).status_code == 204
    assert (await client.get(f"{API}/library/pick")).json() is None
