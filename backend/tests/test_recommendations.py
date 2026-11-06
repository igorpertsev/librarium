from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import API, ApiUser, RegisterUser, SetBatch, fill_cart, place_order


async def _lend(admin: ApiUser, reader: ApiUser, *book_ids: str) -> None:
    await fill_cart(reader, list(book_ids))
    order = (await place_order(reader)).json()
    await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})
    await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "returned"})


async def test_readers_of_a_book_also_borrowed(
    client: AsyncClient, admin: ApiUser, register_user: RegisterUser, set_batch: SetBatch
) -> None:
    await set_batch(1)

    async def book(title: str) -> str:
        response = await admin.post(
            f"{API}/admin/books", json={"title": title, "author": "A", "category": "fiction"}
        )
        book_id: str = response.json()["id"]
        return book_id

    dune, emma, hobbit, solo = [await book(t) for t in ("Dune", "Emma", "Hobbit", "Solo")]
    first, second, third = [await register_user() for _ in range(3)]
    for reader in (first, second, third):
        await _lend(admin, reader, dune)
    for reader in (first, second):
        await _lend(admin, reader, emma)
    await _lend(admin, third, hobbit)
    await _lend(admin, first, solo)  # one reader only: never suggested

    titles = [b["title"] for b in (await client.get(f"{API}/books/{dune}/also-borrowed")).json()]
    assert titles == ["Emma"]  # Hobbit and Solo were borrowed by one reader each
    assert (await client.get(f"{API}/books/{solo}/also-borrowed")).json() == []


async def test_readers_get_suggestions_from_the_tags_they_like(
    admin: ApiUser, customer: ApiUser, set_batch: SetBatch
) -> None:
    await set_batch(1)
    for slug in ("fantasy", "magic", "romance"):
        await admin.post(f"{API}/admin/tags", json={"slug": slug, "name_en": slug, "name_ru": slug})

    async def book(title: str, tags: list[str]) -> str:
        response = await admin.post(
            f"{API}/admin/books",
            json={"title": title, "author": "A", "category": "fiction", "tags": tags},
        )
        book_id: str = response.json()["id"]
        return book_id

    hobbit = await book("Hobbit", ["fantasy"])
    potter = await book("Potter", ["fantasy", "magic"])
    await book("Earthsea", ["fantasy", "magic"])
    await book("Narnia", ["fantasy"])
    await book("Emma", ["romance"])

    assert (await customer.get(f"{API}/users/me/recommendations")).json() == []
    await _lend(admin, customer, hobbit)
    await customer.post(f"{API}/reading-list/{potter}")
    titles = [b["title"] for b in (await customer.get(f"{API}/users/me/recommendations")).json()]
    # fantasy weighs 2 (Hobbit, Potter), magic 1 (Potter): Earthsea 3 > Narnia 2; no romance.
    assert titles == ["Earthsea", "Narnia"]
