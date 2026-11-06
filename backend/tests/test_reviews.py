from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import API, ApiUser, RegisterUser, SetBatch, fill_cart, place_order


async def _borrow(admin: ApiUser, reader: ApiUser, book_id: str) -> None:
    await fill_cart(reader, [book_id])
    order = (await place_order(reader)).json()
    await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})


async def test_readers_rate_books_they_borrowed(
    client: AsyncClient, admin: ApiUser, register_user: RegisterUser, set_batch: SetBatch
) -> None:
    await set_batch(1)
    created = await admin.post(
        f"{API}/admin/books", json={"title": "Dune", "author": "F", "category": "fiction"}
    )
    dune = created.json()["id"]
    copy = (await admin.post(f"{API}/admin/books/{dune}/copies", json={})).json()[0]["id"]
    dana = await register_user(full_name="Dana Reader")
    other = await register_user(full_name="Max Power")

    # Only after borrowing (any copy of the title).
    assert (await other.get(f"{API}/books/{dune}/my-review")).json() == {
        "can_review": False,
        "review": None,
    }
    refused = await other.put(f"{API}/books/{dune}/my-review", json={"rating": 5})
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "NOT_BORROWED"

    await _borrow(admin, dana, copy)
    await _borrow(admin, other, dune)
    rating_only = await other.put(f"{API}/books/{dune}/my-review", json={"rating": 3})
    assert rating_only.json()["status"] == "published"  # no text: no moderation
    written = await dana.put(
        f"{API}/books/{copy}/my-review", json={"rating": 5, "text": " Spice! "}
    )
    assert (written.json()["status"], written.json()["text"]) == ("pending", "Spice!")

    summary = (await client.get(f"{API}/books/{dune}/reviews")).json()
    assert (summary["average"], summary["count"], summary["reviews"]) == (3.0, 1, [])

    # The librarian publishes the written review.
    queue = (await admin.get(f"{API}/admin/reviews")).json()
    assert [(i["book_title"], i["reader_name"], i["text"]) for i in queue["items"]] == [
        ("Dune", "Dana Reader", "Spice!")
    ]
    review_id = queue["items"][0]["id"]
    assert (
        await admin.patch(f"{API}/admin/reviews/{review_id}", json={"status": "published"})
    ).status_code == 200
    summary = (await client.get(f"{API}/books/{copy}/reviews")).json()
    assert (summary["average"], summary["count"]) == (4.0, 2)
    assert [(r["author_name"], r["text"]) for r in summary["reviews"]] == [("Dana R.", "Spice!")]

    # Editing sends it back to moderation; deleting removes it.
    edited = await dana.put(f"{API}/books/{dune}/my-review", json={"rating": 4, "text": "Good"})
    assert edited.json()["status"] == "pending"
    assert (await dana.delete(f"{API}/books/{dune}/my-review")).status_code == 204
    assert (await dana.get(f"{API}/books/{dune}/my-review")).json()["review"] is None
    assert (await other.get(f"{API}/admin/reviews")).status_code == 403
