from __future__ import annotations

import uuid

from fastapi import FastAPI
from sqlalchemy import update

from app.models import Notification
from app.models.enums import NotificationKind, NotificationStatus
from tests.conftest import API, ApiUser, CreateBook, SetBatch, fill_cart, place_order

INBOX = f"{API}/users/me/notifications"


async def test_readers_see_their_news_newest_first_and_mark_it_read(
    app: FastAPI,
    admin: ApiUser,
    customer: ApiUser,
    other_customer: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    dune = await create_book("Dune")
    await fill_cart(customer, [dune])
    order = (await place_order(customer)).json()
    await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})
    me = (await customer.get(f"{API}/users/me")).json()
    async with app.state.db.sessionmaker() as session:
        session.add(
            Notification(
                id=uuid.uuid4(),
                user_id=uuid.UUID(me["id"]),
                book_id=uuid.UUID(dune),
                kind=NotificationKind.BOOK_HELD,
            )
        )
        await session.commit()

    news = (await customer.get(INBOX)).json()
    assert news["unread"] == 3
    assert [item["kind"] for item in news["items"]] == [
        "book_held",
        "order_confirmed",
        "order_received",
    ]
    assert news["items"][0]["book"]["title"] == "Dune"
    assert news["items"][1]["order_number"] == order["number"]
    assert (await other_customer.get(INBOX)).json() == {"items": [], "unread": 0}

    # Someone else cannot mark them; the reader marks one, then all.
    first = news["items"][0]["id"]
    await other_customer.post(f"{INBOX}/read", json={"ids": [first]})
    assert (await customer.get(INBOX)).json()["unread"] == 3
    assert (await customer.post(f"{INBOX}/read", json={"ids": [first]})).status_code == 204
    news = (await customer.get(INBOX)).json()
    assert (news["unread"], news["items"][0]["read"]) == (2, True)
    assert (await customer.post(f"{INBOX}/read")).status_code == 204
    assert (await customer.get(INBOX)).json()["unread"] == 0

    # News that went stale before it was sent is not shown.
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(Notification)
            .where(Notification.kind == NotificationKind.BOOK_HELD)
            .values(status=NotificationStatus.EXPIRED)
        )
        await session.commit()
    assert len((await customer.get(INBOX)).json()["items"]) == 2
