from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from sqlalchemy import select

from app.models import Order, User
from tests.conftest import API, PASSWORD, ApiUser, CreateBook, SetBatch, fill_cart, place_order


async def _ordered(customer: ApiUser, create_book: CreateBook, title: str) -> dict[str, Any]:
    await fill_cart(customer, [await create_book(title)])
    response = await place_order(customer)
    assert response.status_code == 201, response.text
    order: dict[str, Any] = response.json()
    return order


async def test_readers_can_download_their_data(
    customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    await _ordered(customer, create_book, "Dune")
    saved = await create_book("Emma")
    await customer.post(f"{API}/reading-list/{saved}")

    response = await customer.get(f"{API}/users/me/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    data = response.json()
    assert data["profile"]["email"] == customer.email
    assert [book["title"] for book in data["orders"][0]["books"]] == ["Dune"]
    assert [item["title"] for item in data["want_to_read"]] == ["Emma"]
    assert data["sessions"], "the current sign-in is listed"


async def test_deleting_an_account_keeps_orders_without_personal_data(
    app: FastAPI, admin: ApiUser, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    order = await _ordered(customer, create_book, "Dune")

    wrong = await customer.client.request(
        "DELETE", f"{API}/users/me", headers=customer.headers, json={"password": "nope"}
    )
    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "INVALID_CURRENT_PASSWORD"
    busy = await customer.client.request(
        "DELETE", f"{API}/users/me", headers=customer.headers, json={"password": PASSWORD}
    )
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "ACTIVE_ORDERS"

    await customer.post(f"{API}/orders/{order['id']}/cancel")
    deleted = await customer.client.request(
        "DELETE", f"{API}/users/me", headers=customer.headers, json={"password": PASSWORD}
    )
    assert deleted.status_code == 204, deleted.text

    async with app.state.db.sessionmaker() as session:
        user = await session.scalar(select(User).where(User.id == customer.data["id"]))
        assert user is not None
        assert (user.is_active, user.full_name, user.telegram) == (False, "Deleted user", None)
        assert user.email.endswith("@deleted.invalid")
        kept = await session.scalar(select(Order).where(Order.user_id == user.id))
        assert kept is not None
        assert (kept.contact_name, kept.contact_telegram) == ("Deleted user", None)

    # The old session no longer works and the email can register again.
    assert (await customer.get(f"{API}/auth/me")).status_code == 401
    login = await customer.client.post(
        f"{API}/auth/login", json={"email": customer.email, "password": PASSWORD}
    )
    assert login.status_code == 401
    again = await customer.client.post(
        f"{API}/auth/register",
        json={
            "email": customer.email,
            "password": PASSWORD,
            "full_name": "Back Again",
            "telegram": "@back",
            "preferred_contact_method": "telegram",
        },
    )
    assert again.status_code == 201, again.text

    refused = await admin.client.request(
        "DELETE", f"{API}/users/me", headers=admin.headers, json={"password": PASSWORD}
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "ADMIN_ACCOUNT"
