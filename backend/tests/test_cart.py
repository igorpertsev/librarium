from __future__ import annotations

import uuid

from app.models.enums import BookStatus
from tests.conftest import API, ApiUser, CreateBook, SetBatch, fill_cart, place_order

CART = f"{API}/cart"


async def test_cart_requires_authentication(customer: ApiUser) -> None:
    response = await customer.client.get(CART)
    assert response.status_code == 401


async def test_empty_cart_has_pricing(customer: ApiUser) -> None:
    response = await customer.get(CART)
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["books_per_batch"] == 5
    assert body["price_per_batch"] == "15.99"
    assert body["currency"] == "USD"
    assert body["total_amount"] == "0.00"


async def test_add_available_book_and_readd_is_idempotent(
    customer: ApiUser, create_book: CreateBook
) -> None:
    book = await create_book("Dune")
    first = await customer.post(f"{CART}/items", json={"book_id": book})
    assert first.status_code == 200, first.text
    again = await customer.post(f"{CART}/items", json={"book_id": book})
    assert again.status_code == 200

    body = again.json()
    assert body["item_count"] == 1
    assert body["items"][0]["book"]["id"] == book
    assert body["items"][0]["batch_number"] == 1
    assert body["items"][0]["in_complete_batch"] is False


async def test_batches_and_total(
    customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(2, "10.00")
    books = [await create_book() for _ in range(5)]
    body = await fill_cart(customer, books)
    assert body["item_count"] == 5
    assert body["complete_batches"] == 2
    assert body["orderable_item_count"] == 4
    assert body["total_amount"] == "20.00"
    assert [i["batch_number"] for i in body["items"]] == [1, 1, 2, 2, 3]
    assert [i["in_complete_batch"] for i in body["items"]] == [True, True, True, True, False]


async def test_remove_and_clear(customer: ApiUser, create_book: CreateBook) -> None:
    a, b = await create_book(), await create_book()
    await fill_cart(customer, [a, b])

    removed = await customer.delete(f"{CART}/items/{a}")
    assert removed.status_code == 200
    assert [i["book"]["id"] for i in removed.json()["items"]] == [b]

    # Removing something that is not in the cart is a no-op.
    assert (await customer.delete(f"{CART}/items/{uuid.uuid4()}")).status_code == 200

    cleared = await customer.delete(CART)
    assert cleared.status_code == 200
    assert cleared.json()["items"] == []


async def test_cannot_add_book_reserved_by_active_order(
    customer: ApiUser,
    other_customer: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    book = await create_book("Taken")
    await fill_cart(other_customer, [book])
    assert (await place_order(other_customer)).status_code == 201

    response = await customer.post(f"{CART}/items", json={"book_id": book})
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "BOOK_UNAVAILABLE"
    assert error["details"]["book_ids"] == [book]
    assert error["details"]["books"] == [{"id": book, "title": "Taken"}]

    # The same physical copy cannot be re-added by its own borrower either.
    own = await other_customer.post(f"{CART}/items", json={"book_id": book})
    assert own.status_code == 409


async def test_cannot_add_unavailable_or_inactive_books(
    customer: ApiUser, create_book: CreateBook
) -> None:
    soon = await create_book(status=BookStatus.AVAILABLE_SOON)
    lost = await create_book(status=BookStatus.NOT_AVAILABLE)
    inactive = await create_book(is_active=False)

    for book in (soon, lost):
        response = await customer.post(f"{CART}/items", json={"book_id": book})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "BOOK_UNAVAILABLE"

    gone = await customer.post(f"{CART}/items", json={"book_id": inactive})
    assert gone.status_code == 404
    missing = await customer.post(f"{CART}/items", json={"book_id": str(uuid.uuid4())})
    assert missing.status_code == 404


async def test_carts_are_private(
    customer: ApiUser, other_customer: ApiUser, create_book: CreateBook
) -> None:
    book = await create_book()
    await fill_cart(customer, [book])
    other = await other_customer.get(CART)
    assert other.json()["items"] == []
    # A book in someone's cart is not reserved: carts are not reservations.
    assert (await other_customer.post(f"{CART}/items", json={"book_id": book})).status_code == 200
