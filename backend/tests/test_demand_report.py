from __future__ import annotations

from tests.conftest import (
    API,
    ApiUser,
    RegisterUser,
    SetBatch,
    fill_cart,
    place_order,
)


async def test_the_demand_report_shows_what_to_buy_more_of(
    admin: ApiUser, register_user: RegisterUser, set_batch: SetBatch
) -> None:
    await set_batch(1)
    for slug, en, ru in [("fantasy", "Fantasy", "Фэнтези"), ("magic", "Magic", "Волшебство")]:
        await admin.post(f"{API}/admin/tags", json={"slug": slug, "name_en": en, "name_ru": ru})

    async def book(title: str, tags: list[str]) -> str:
        response = await admin.post(
            f"{API}/admin/books",
            json={"title": title, "author": "A", "category": "fiction", "tags": tags},
        )
        book_id: str = response.json()["id"]
        return book_id

    hobbit = await book("The Hobbit", ["fantasy"])
    potter = await book("Harry Potter", ["fantasy", "magic"])
    emma = await book("Emma", [])
    readers = [await register_user() for _ in range(3)]

    # The first reader borrows both fantasy books; the others wait for one of them.
    for book_id in (hobbit, potter):
        await fill_cart(readers[0], [book_id])
        order = (await place_order(readers[0])).json()
        await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})
    for reader in readers[1:]:
        assert (await reader.post(f"{API}/waitlist/{potter}")).status_code == 201
        await reader.post(f"{API}/reading-list/{emma}")
    await readers[1].post(f"{API}/waitlist/{hobbit}")

    body = (await admin.get(f"{API}/admin/reports/demand")).json()
    assert [(t["title"], t["readers"], t["copies"]) for t in body["waiting"]] == [
        ("Harry Potter", 2, 1),
        ("The Hobbit", 1, 1),
    ]
    assert [(t["title"], t["readers"]) for t in body["saved"]] == [("Emma", 2)]
    assert [(t["slug"], t["loans"]) for t in body["tags"]] == [("fantasy", 2), ("magic", 1)]
