from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import API, PASSWORD, ApiUser, CreateBook, SetBatch, fill_cart

KIDS = f"{API}/users/me/children"
LOG = f"{API}/users/me/reading-log"


async def test_a_family_keeps_a_reading_log_for_each_child(
    customer: ApiUser, other_customer: ApiUser, create_book: CreateBook
) -> None:
    mia = (await customer.post(KIDS, json={"name": " Mia ", "birth_year": 2018})).json()
    leo = (await customer.post(KIDS, json={"name": "Leo"})).json()
    assert (mia["name"], mia["birth_year"]) == ("Mia", 2018)
    assert [c["name"] for c in (await customer.get(KIDS)).json()] == ["Mia", "Leo"]

    gruffalo = await create_book("The Gruffalo")
    dune = await create_book("Dune")
    await customer.put(f"{LOG}/{gruffalo}", params={"child": mia["id"]})
    await customer.put(f"{LOG}/{dune}")  # the parent's own reading

    mine = (await customer.get(LOG)).json()
    hers = (await customer.get(LOG, params={"child": mia["id"]})).json()
    his = (await customer.get(LOG, params={"child": leo["id"]})).json()
    assert [e["book"]["title"] for e in mine["entries"]] == ["Dune"]
    assert [e["book"]["title"] for e in hers["entries"]] == ["The Gruffalo"]
    assert his["total"] == 0
    assert {b["key"]: b["earned"] for b in hers["badges"]}["first_book"] is True

    # The same book can be in two profiles' logs; taking it off one leaves the other.
    await customer.put(f"{LOG}/{gruffalo}")
    await customer.delete(f"{LOG}/{gruffalo}", params={"child": mia["id"]})
    assert (await customer.get(LOG, params={"child": mia["id"]})).json()["total"] == 0
    assert (await customer.get(LOG)).json()["total"] == 2

    # Other people's children are not reachable.
    stranger = await other_customer.get(LOG, params={"child": mia["id"]})
    assert stranger.json()["error"]["code"] == "CHILD_NOT_FOUND"
    renamed = await customer.patch(f"{KIDS}/{leo['id']}", json={"name": "Leonard"})
    assert renamed.json()["name"] == "Leonard"
    assert (await customer.delete(f"{KIDS}/{leo['id']}")).status_code == 204
    assert [c["name"] for c in (await customer.get(KIDS)).json()] == ["Mia"]


async def test_orders_say_which_child_they_are_for(
    admin: ApiUser, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    mia = (await customer.post(KIDS, json={"name": "Mia"})).json()
    await fill_cart(customer, [await create_book()])
    placed = await customer.post(f"{API}/orders", json={"child_id": mia["id"]})
    assert placed.status_code == 201, placed.text
    assert placed.json()["child_name"] == "Mia"
    admin_view = (await admin.get(f"{API}/admin/orders/{placed.json()['id']}")).json()
    assert admin_view["child_name"] == "Mia"
    # Removing the profile keeps the name on the order.
    await customer.delete(f"{KIDS}/{mia['id']}")
    assert (await customer.get(f"{API}/orders/{placed.json()['id']}")).json()["child_name"] == "Mia"


async def test_up_to_six_children_and_they_go_with_the_account(
    customer: ApiUser, client: AsyncClient
) -> None:
    for n in range(6):
        assert (await customer.post(KIDS, json={"name": f"Kid {n}"})).status_code == 201
    seventh = await customer.post(KIDS, json={"name": "One more"})
    assert seventh.json()["error"]["code"] == "TOO_MANY_CHILDREN"
    exported = (await customer.get(f"{API}/users/me/export")).json()
    assert len(exported["children"]) == 6
    deleted = await client.request(
        "DELETE", f"{API}/users/me", headers=customer.headers, json={"password": PASSWORD}
    )
    assert deleted.status_code == 204
