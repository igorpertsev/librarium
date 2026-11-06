from __future__ import annotations

import uuid
from email.message import EmailMessage
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select

from app.models import Notification
from app.models.enums import BookStatus, NotificationKind, NotificationStatus
from app.services.notifications import deliver_pending
from tests.conftest import API, ApiUser, CreateBook, SetBatch, fill_cart, place_order


class FakeSender:
    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    async def __call__(self, message: EmailMessage) -> None:
        self.messages.append(message)


async def _order(user: ApiUser, book_id: str) -> dict[str, Any]:
    await fill_cart(user, [book_id])
    response = await place_order(user)
    assert response.status_code == 201, response.text
    order: dict[str, Any] = response.json()
    return order


async def _set_status(admin: ApiUser, order_id: str, status: str) -> None:
    response = await admin.patch(f"{API}/admin/orders/{order_id}/status", json={"status": status})
    assert response.status_code == 200, response.text


async def _book_available_notifications(app: FastAPI) -> list[Notification]:
    async with app.state.db.sessionmaker() as session:
        return list(
            (
                await session.scalars(
                    select(Notification).where(Notification.kind == NotificationKind.BOOK_AVAILABLE)
                )
            ).all()
        )


async def _deliver(app: FastAPI) -> FakeSender:
    send = FakeSender()
    async with app.state.db.sessionmaker() as session:
        await deliver_pending(session, app.state.settings, send)
    return send


async def test_join_and_leave_the_waiting_list(
    customer: ApiUser, other_customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    book_id = await create_book("Dune")

    response = await other_customer.client.post(
        f"{API}/waitlist/{book_id}", headers=other_customer.headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BOOK_AVAILABLE"

    await _order(customer, book_id)
    url = f"{API}/waitlist/{book_id}"
    first = await other_customer.client.post(url, headers=other_customer.headers)
    assert first.status_code == 201
    assert first.json()["book"]["title"] == "Dune"
    again = await other_customer.client.post(url, headers=other_customer.headers)
    assert again.status_code == 200

    listed = (await other_customer.get(f"{API}/waitlist")).json()
    assert [entry["book"]["id"] for entry in listed] == [book_id]

    assert (await other_customer.delete(url)).status_code == 204
    assert (await other_customer.get(f"{API}/waitlist")).json() == []

    missing = await other_customer.client.post(
        f"{API}/waitlist/{uuid.uuid4()}", headers=other_customer.headers
    )
    assert missing.status_code == 404


async def test_waiting_readers_are_emailed_when_the_book_comes_back(
    app: FastAPI,
    customer: ApiUser,
    other_customer: ApiUser,
    admin: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    book_id = await create_book("The Name of the Wind")
    order = await _order(customer, book_id)
    await other_customer.client.post(f"{API}/waitlist/{book_id}", headers=other_customer.headers)

    await _set_status(admin, order["id"], "confirmed")
    assert await _book_available_notifications(app) == []  # still out

    await _set_status(admin, order["id"], "returned")
    (notification,) = await _book_available_notifications(app)
    assert str(notification.user_id) == other_customer.id
    assert str(notification.book_id) == book_id
    assert (await other_customer.get(f"{API}/waitlist")).json() == []  # one email only

    send = await _deliver(app)
    mail = next(m for m in send.messages if "available again" in m["Subject"])
    assert other_customer.email in mail["To"]
    assert "“The Name of the Wind” is available again" in mail["Subject"]
    assert "снова" in mail.get_content()


async def test_a_cancelled_request_also_frees_the_book_for_waiting_readers(
    app: FastAPI,
    customer: ApiUser,
    other_customer: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    book_id = await create_book()
    order = await _order(customer, book_id)
    await other_customer.client.post(f"{API}/waitlist/{book_id}", headers=other_customer.headers)
    response = await customer.post(f"{API}/orders/{order['id']}/cancel")
    assert response.status_code == 200
    assert len(await _book_available_notifications(app)) == 1


async def test_the_email_is_dropped_if_the_book_is_taken_again_first(
    app: FastAPI,
    customer: ApiUser,
    other_customer: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    book_id = await create_book()
    order = await _order(customer, book_id)
    await other_customer.client.post(f"{API}/waitlist/{book_id}", headers=other_customer.headers)
    await customer.post(f"{API}/orders/{order['id']}/cancel")
    await _order(customer, book_id)  # ordered again before the email went out

    send = await _deliver(app)
    assert not any("available again" in m["Subject"] for m in send.messages)
    (notification,) = await _book_available_notifications(app)
    async with app.state.db.sessionmaker() as session:
        refreshed = await session.get(Notification, notification.id)
        assert refreshed is not None
        assert refreshed.status is NotificationStatus.EXPIRED


async def test_making_a_book_available_in_the_admin_portal_notifies(
    app: FastAPI, other_customer: ApiUser, admin: ApiUser, create_book: CreateBook
) -> None:
    book_id = await create_book(status=BookStatus.NOT_AVAILABLE)
    response = await other_customer.client.post(
        f"{API}/waitlist/{book_id}", headers=other_customer.headers
    )
    assert response.status_code == 201
    await admin.patch(f"{API}/admin/books/{book_id}", json={"description": "New edition"})
    assert await _book_available_notifications(app) == []
    await admin.patch(f"{API}/admin/books/{book_id}", json={"status": "available"})
    assert len(await _book_available_notifications(app)) == 1


async def test_a_loan_cannot_be_extended_while_others_wait(
    customer: ApiUser,
    other_customer: ApiUser,
    admin: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    book_id = await create_book()
    order = await _order(customer, book_id)
    await _set_status(admin, order["id"], "confirmed")
    await other_customer.client.post(f"{API}/waitlist/{book_id}", headers=other_customer.headers)

    response = await customer.post(f"{API}/orders/{order['id']}/renew")
    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"reason": "requested_by_others"}

    await other_customer.delete(f"{API}/waitlist/{book_id}")
    assert (await customer.post(f"{API}/orders/{order['id']}/renew")).status_code == 200
