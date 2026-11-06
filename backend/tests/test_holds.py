from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select, update

from app.models import BookHold, Notification
from app.models.enums import NotificationKind
from app.services import holds
from app.services.notifications import deliver_pending
from tests.conftest import API, ApiUser, RegisterUser, SetBatch, fill_cart, place_order


class FakeSender:
    def __init__(self) -> None:
        self.messages: list[Any] = []

    async def __call__(self, message: Any) -> None:
        self.messages.append(message)


async def _held_emails(app: FastAPI) -> list[Notification]:
    async with app.state.db.sessionmaker() as session:
        rows = await session.scalars(
            select(Notification).where(Notification.kind == NotificationKind.BOOK_HELD)
        )
        return list(rows.all())


async def _lend(admin: ApiUser, reader: ApiUser, book_id: str) -> str:
    await fill_cart(reader, [book_id])
    order = (await place_order(reader)).json()
    await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})
    order_id: str = order["id"]
    return order_id


async def test_a_returned_book_is_held_for_the_reader_who_waited_longest(
    app: FastAPI, admin: ApiUser, register_user: RegisterUser, set_batch: SetBatch
) -> None:
    await set_batch(1)
    created = await admin.post(
        f"{API}/admin/books", json={"title": "Dune", "author": "F", "category": "fiction"}
    )
    dune = created.json()["id"]
    borrower, first, second = [await register_user() for _ in range(3)]
    order_id = await _lend(admin, borrower, dune)
    assert (await first.post(f"{API}/waitlist/{dune}")).status_code == 201
    assert (await second.post(f"{API}/waitlist/{dune}")).status_code == 201

    await admin.patch(f"{API}/admin/orders/{order_id}/status", json={"status": "returned"})

    # Only the first reader is told; the second keeps waiting.
    emails = await _held_emails(app)
    assert [str(n.user_id) for n in emails] == [first.id]
    assert [e["book"]["title"] for e in (await second.get(f"{API}/waitlist")).json()] == ["Dune"]
    held = (await first.get(f"{API}/users/me/holds")).json()
    assert [h["book"]["title"] for h in held] == ["Dune"]
    held_until = datetime.fromisoformat(held[0]["held_until"])
    assert timedelta(hours=47) < held_until - datetime.now(UTC) <= timedelta(hours=48)

    # Nobody else can take it; the catalogue shows it as not available.
    refused = await second.post(f"{API}/cart/items", json={"book_id": dune})
    assert refused.status_code == 409
    listed = (await second.get(f"{API}/books", params={"q": "Dune"})).json()["items"][0]
    assert listed["is_available"] is False
    # The email goes out with the deadline.
    send = FakeSender()
    async with app.state.db.sessionmaker() as session:
        await deliver_pending(session, app.state.settings, send)
    (message,) = [m for m in send.messages if "held for you" in m["Subject"]]
    assert "/profile" in message.get_content()

    # The holder takes it: the hold ends with the order.
    await fill_cart(first, [dune])
    assert (await place_order(first)).status_code == 201
    assert (await first.get(f"{API}/users/me/holds")).json() == []


async def test_an_expired_or_released_hold_goes_to_the_next_reader(
    app: FastAPI, admin: ApiUser, register_user: RegisterUser, set_batch: SetBatch
) -> None:
    await set_batch(1)
    created = await admin.post(
        f"{API}/admin/books", json={"title": "Emma", "author": "J", "category": "fiction"}
    )
    emma = created.json()["id"]
    borrower, first, second, third = [await register_user() for _ in range(4)]
    order_id = await _lend(admin, borrower, emma)
    for reader in (first, second, third):
        await reader.post(f"{API}/waitlist/{emma}")
    await admin.patch(f"{API}/admin/orders/{order_id}/status", json={"status": "returned"})

    # The first reader lets the hold run out.
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(BookHold).values(held_until=datetime.now(UTC) - timedelta(minutes=1))
        )
        await session.commit()
    async with app.state.db.sessionmaker() as session:
        assert await holds.expire(session, datetime.now(UTC)) == 1
    assert [h["book"]["title"] for h in (await second.get(f"{API}/users/me/holds")).json()] == [
        "Emma"
    ]
    assert (await first.get(f"{API}/users/me/holds")).json() == []

    # The second gives it up: the third gets it.
    assert (await second.delete(f"{API}/users/me/holds/{emma}")).status_code == 204
    assert [h["book"]["title"] for h in (await third.get(f"{API}/users/me/holds")).json()] == [
        "Emma"
    ]
    assert [str(n.user_id) for n in await _held_emails(app)] == [first.id, second.id, third.id]
