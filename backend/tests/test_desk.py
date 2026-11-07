"""The scan desk: where a scanned copy stands."""

from __future__ import annotations

import uuid

from tests.conftest import API, ApiUser, CreateBook, SetBatch, fill_cart, place_order


async def test_a_scanned_copy_shows_its_order(
    admin: ApiUser, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    copy = await create_book("Dune")
    desk = f"{API}/admin/copies/{copy}/desk"

    free = (await admin.get(desk)).json()
    assert (free["book"]["title"], free["order"], free["held_for"]) == ("Dune", None, None)

    await fill_cart(customer, [copy])
    placed = (await place_order(customer)).json()
    waiting = (await admin.get(desk)).json()["order"]
    assert (waiting["id"], waiting["status"], waiting["book_count"]) == (placed["id"], "pending", 1)
    assert waiting["reader_name"] == customer.data["full_name"]

    await admin.patch(f"{API}/admin/orders/{placed['id']}/status", json={"status": "confirmed"})
    assert (await admin.get(desk)).json()["order"]["status"] == "confirmed"
    await admin.patch(f"{API}/admin/orders/{placed['id']}/status", json={"status": "returned"})
    assert (await admin.get(desk)).json()["order"] is None  # back on the shelf

    assert (await admin.get(f"{API}/admin/copies/{uuid.uuid4()}/desk")).status_code == 404
    assert (await customer.get(desk)).status_code == 403
