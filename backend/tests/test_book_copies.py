from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import API, ApiUser, CreateBook, SetBatch, fill_cart, place_order


async def _catalogue(client: AsyncClient, **params: Any) -> dict[str, Any]:
    body: dict[str, Any] = (await client.get(f"{API}/books", params=params)).json()
    return body


async def _add_copies(admin: ApiUser, book_id: str, count: int) -> list[dict[str, Any]]:
    response = await admin.post(f"{API}/admin/books/{book_id}/copies", json={"count": count})
    assert response.status_code == 201, response.text
    copies: list[dict[str, Any]] = response.json()
    return copies


async def test_copies_are_listed_once_with_counts(
    client: AsyncClient, admin: ApiUser, create_book: CreateBook
) -> None:
    dune = await create_book("Dune")
    await create_book("Emma")
    copies = await _add_copies(admin, dune, 2)
    assert {c["title"] for c in copies} == {"Dune"}
    assert copies[0]["copies"] == 3

    catalogue = await _catalogue(client, sort="title")
    assert catalogue["total"] == 2
    entry = catalogue["items"][0]
    assert (entry["title"], entry["copies"], entry["copies_available"]) == ("Dune", 3, 3)

    admin_list = (await admin.get(f"{API}/admin/books", params={"q": "Dune"})).json()
    assert admin_list["total"] == 3  # librarians manage each copy
    assert {b["copies"] for b in admin_list["items"]} == {3}

    detail = (await client.get(f"{API}/books/{copies[1]['id']}")).json()
    assert (detail["copies"], detail["copies_available"]) == (3, 3)


async def test_the_catalogue_offers_a_free_copy_while_one_is_out(
    client: AsyncClient,
    customer: ApiUser,
    other_customer: ApiUser,
    admin: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    first = await create_book("Dune")
    second = (await _add_copies(admin, first, 1))[0]["id"]

    await fill_cart(customer, [first])
    assert (await place_order(customer)).status_code == 201

    entry = (await _catalogue(client))["items"][0]
    assert entry["id"] == second  # the copy that can be borrowed
    assert entry["is_available"] is True
    assert (entry["copies"], entry["copies_available"]) == (2, 1)

    # The other reader borrows the second copy: now every copy is out.
    await fill_cart(other_customer, [entry["id"]])
    assert (await place_order(other_customer)).status_code == 201
    entry = (await _catalogue(client))["items"][0]
    assert entry["is_available"] is False
    assert entry["copies_available"] == 0
    assert entry["available_from"] is not None

    assert (await _catalogue(client, available="true"))["total"] == 0
    unavailable = await _catalogue(client, available="false")
    assert unavailable["total"] == 1


async def test_catalogue_edits_apply_to_every_copy_but_status_does_not(
    admin: ApiUser, create_book: CreateBook
) -> None:
    first = await create_book("Dune")
    second = (await _add_copies(admin, first, 1))[0]["id"]

    response = await admin.patch(
        f"{API}/admin/books/{second}",
        json={"title": "Dune (Deluxe)", "status": "not-available"},
    )
    assert response.status_code == 200
    books = {b["id"]: b for b in (await admin.get(f"{API}/admin/books")).json()["items"]}
    assert books[first]["title"] == "Dune (Deluxe)"
    assert books[first]["status"] == "available"
    assert books[second]["status"] == "not-available"


async def test_adding_copies_needs_an_existing_book(admin: ApiUser, customer: ApiUser) -> None:
    missing = await admin.post(
        f"{API}/admin/books/00000000-0000-0000-0000-000000000000/copies", json={"count": 1}
    )
    assert missing.status_code == 404
    too_many = await admin.post(
        f"{API}/admin/books/00000000-0000-0000-0000-000000000000/copies", json={"count": 21}
    )
    assert too_many.status_code == 422
    forbidden = await customer.post(
        f"{API}/admin/books/00000000-0000-0000-0000-000000000000/copies", json={"count": 1}
    )
    assert forbidden.status_code == 403
