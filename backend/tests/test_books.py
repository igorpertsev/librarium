from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.models.enums import BookCategory, BookStatus
from tests.conftest import API, ApiUser, CreateBook, SetBatch, fill_cart, place_order


async def test_list_books_paginates_and_hides_inactive(
    client: AsyncClient, create_book: CreateBook
) -> None:
    for title in ("Alpha", "Bravo", "Charlie"):
        await create_book(title)
    await create_book("Deleted", is_active=False)

    first = await client.get(f"{API}/books", params={"page_size": 2})
    assert first.status_code == 200
    body = first.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert [b["title"] for b in body["items"]] == ["Alpha", "Bravo"]

    second = await client.get(f"{API}/books", params={"page_size": 2, "page": 2})
    assert [b["title"] for b in second.json()["items"]] == ["Charlie"]

    book = body["items"][0]
    assert book["is_available"] is True
    assert book["is_reserved"] is False
    assert set(book) >= {"cover_url", "image_urls", "publication_year", "age_range", "isbn"}


async def test_search_category_age_and_sort(client: AsyncClient, create_book: CreateBook) -> None:
    await create_book("The Hobbit", author="J.R.R. Tolkien", age_range="10+")
    await create_book("Cosmos", author="Carl Sagan", category=BookCategory.SCIENCE)
    await create_book("100% Pure_Title")

    by_author = await client.get(f"{API}/books", params={"q": "tolkien"})
    assert [b["title"] for b in by_author.json()["items"]] == ["The Hobbit"]

    # LIKE wildcards in user input are escaped, not interpreted.
    literal = await client.get(f"{API}/books", params={"q": "0% P"})
    assert [b["title"] for b in literal.json()["items"]] == ["100% Pure_Title"]
    wildcard = await client.get(f"{API}/books", params={"q": "_"})
    assert [b["title"] for b in wildcard.json()["items"]] == ["100% Pure_Title"]

    science = await client.get(f"{API}/books", params={"category": "science"})
    assert [b["title"] for b in science.json()["items"]] == ["Cosmos"]

    ages = await client.get(f"{API}/books", params={"age_range": "10+"})
    assert [b["title"] for b in ages.json()["items"]] == ["The Hobbit"]

    descending = await client.get(f"{API}/books", params={"sort": "-title"})
    assert [b["title"] for b in descending.json()["items"]] == [
        "The Hobbit",
        "Cosmos",
        "100% Pure_Title",
    ]

    age_ranges = await client.get(f"{API}/books/age-ranges")
    assert age_ranges.json() == ["10+", "12+"]


async def test_sort_and_filters_are_allow_listed(client: AsyncClient) -> None:
    for params in (
        {"sort": "password_hash"},
        {"sort": "title; DROP TABLE books"},
        {"category": "cooking"},
        {"page_size": 1000},
        {"page": 0},
    ):
        response = await client.get(f"{API}/books", params=params)
        assert response.status_code == 422, params
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_availability_filter_reflects_status_and_reservations(
    client: AsyncClient, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    free = await create_book("Free")
    await create_book("Soon", status=BookStatus.AVAILABLE_SOON)
    reserved = await create_book("Reserved")
    await set_batch(1)
    await fill_cart(customer, [reserved])
    assert (await place_order(customer)).status_code == 201

    available = await client.get(f"{API}/books", params={"available": "true"})
    assert [b["id"] for b in available.json()["items"]] == [free]

    unavailable = await client.get(f"{API}/books", params={"available": "false", "sort": "title"})
    assert [b["title"] for b in unavailable.json()["items"]] == ["Reserved", "Soon"]

    detail = await client.get(f"{API}/books/{reserved}")
    assert detail.json()["is_reserved"] is True
    assert detail.json()["is_available"] is False


async def test_get_book_404s(client: AsyncClient, create_book: CreateBook) -> None:
    inactive = await create_book("Gone", is_active=False)
    missing = await client.get(f"{API}/books/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "BOOK_NOT_FOUND"
    assert (await client.get(f"{API}/books/{inactive}")).status_code == 404
    assert (await client.get(f"{API}/books/not-a-uuid")).status_code == 422


async def test_reserved_books_report_when_they_are_expected_back(
    client: AsyncClient, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    reserved, free = await create_book("Reserved"), await create_book("Free")
    await fill_cart(customer, [reserved])
    order = (await place_order(customer)).json()

    detail = (await client.get(f"{API}/books/{reserved}")).json()
    assert detail["is_reserved"] is True
    assert detail["available_from"] == order["due_date"]
    listed = {b["id"]: b for b in (await client.get(f"{API}/books")).json()["items"]}
    assert listed[reserved]["available_from"] == order["due_date"]
    assert listed[free]["available_from"] is None

    await customer.post(f"{API}/orders/{order['id']}/cancel")
    assert (await client.get(f"{API}/books/{reserved}")).json()["available_from"] is None
