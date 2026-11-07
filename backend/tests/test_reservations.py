from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select, update

from app.models import AdvanceReservation, BookHold, Notification
from app.models.enums import NotificationKind
from app.services import reservations
from app.services.notifications import deliver_pending
from tests.conftest import (
    API,
    ApiUser,
    CreateBook,
    RegisterUser,
    SetBatch,
    fill_cart,
    place_order,
)
from tests.test_holds import FakeSender

MINE = f"{API}/users/me/reservations"


def _day(offset: int) -> str:
    return (datetime.now(UTC).date() + timedelta(days=offset)).isoformat()


async def _reserve(user: ApiUser, book_id: str, offset: int) -> Any:
    return await user.post(MINE, json={"book_id": book_id, "starts_on": _day(offset)})


async def _borrow(admin: ApiUser, reader: ApiUser, book_id: str) -> str:
    await fill_cart(reader, [book_id])
    placed = await place_order(reader)
    assert placed.status_code == 201, placed.text
    order_id: str = placed.json()["id"]
    await admin.patch(f"{API}/admin/orders/{order_id}/status", json={"status": "confirmed"})
    return order_id


async def test_a_reserved_copy_is_set_aside_a_loan_period_before_its_day(
    customer: ApiUser, other_customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    dune = await create_book("Dune")
    # Loans last 30 days, so a reservation 10 days ahead keeps the copy from now on.
    made = await _reserve(customer, dune, 10)
    assert made.status_code == 201, made.text
    assert (made.json()["book"]["title"], made.json()["status"]) == ("Dune", "active")
    assert [r["starts_on"] for r in (await customer.get(MINE)).json()] == [_day(10)]

    refused = await other_customer.post(f"{API}/cart/items", json={"book_id": dune})
    assert refused.status_code == 409
    listed = (await other_customer.get(f"{API}/books", params={"q": "Dune"})).json()["items"][0]
    assert listed["is_available"] is False
    assert listed["available_from"] == _day(40)  # back one loan after the reserved day

    again = await _reserve(customer, dune, 20)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "ALREADY_RESERVED")
    for offset in (0, 91):
        wrong = await _reserve(other_customer, dune, offset)
        assert wrong.json()["error"]["code"] == "INVALID_RESERVATION_DATE"


async def test_copies_out_too_long_or_reserved_nearby_are_not_offered(
    admin: ApiUser,
    customer: ApiUser,
    other_customer: ApiUser,
    register_user: RegisterUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    emma = await create_book("Emma")
    await _borrow(admin, other_customer, emma)  # due in 30 days
    busy = await _reserve(customer, emma, 20)
    assert (busy.status_code, busy.json()["error"]["code"]) == (409, "NO_COPY_FOR_DATE")
    assert (await _reserve(customer, emma, 45)).status_code == 201  # back by then

    # A second copy takes the next reservation for the earlier day.
    await admin.post(f"{API}/admin/books/{emma}/copies", json={"count": 1})
    third = await register_user()
    second_copy = await _reserve(third, emma, 20)
    assert second_copy.status_code == 201, second_copy.text
    assert second_copy.json()["book"]["id"] != emma


async def test_loans_cannot_be_extended_past_a_reserved_day(
    admin: ApiUser,
    customer: ApiUser,
    other_customer: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    await admin.patch(f"{API}/admin/settings", json={"max_renewals": 2})
    hamlet = await create_book("Hamlet")
    # 60 days ahead the copy is still free for a 30-day loan now...
    assert (await _reserve(customer, hamlet, 60)).status_code == 201
    order_id = await _borrow(admin, other_customer, hamlet)
    # ...but not for another 30 days after that.
    renewed = await other_customer.post(f"{API}/orders/{order_id}/renew")
    assert renewed.status_code == 409
    assert renewed.json()["error"]["details"]["reason"] == "requested_by_others"


async def test_on_its_day_the_copy_is_held_and_the_reader_emailed(
    app: FastAPI,
    admin: ApiUser,
    customer: ApiUser,
    other_customer: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    ivanhoe = await create_book("Ivanhoe")
    made = (await _reserve(customer, ivanhoe, 5)).json()
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(AdvanceReservation)
            .where(AdvanceReservation.id == uuid.UUID(made["id"]))
            .values(starts_on=datetime.now(UTC).date())
        )
        await session.commit()
        assert await reservations.activate(session) == 1
        hold = await session.get(BookHold, uuid.UUID(ivanhoe))
        assert hold is not None
        assert str(hold.user_id) == (await customer.get(f"{API}/users/me")).json()["id"]
        kinds = (await session.scalars(select(Notification.kind))).all()
        assert NotificationKind.RESERVATION_READY in kinds
        send = FakeSender()
        await deliver_pending(session, app.state.settings, send)
    (message,) = [m for m in send.messages if "held for you" in m["Subject"]]
    assert "which you reserved, is ready" in message.get_content()

    assert (await customer.get(MINE)).json() == []  # fulfilled
    held = (await customer.get(f"{API}/users/me/holds")).json()
    assert [h["book"]["title"] for h in held] == ["Ivanhoe"]
    refused = await other_customer.post(f"{API}/cart/items", json={"book_id": ivanhoe})
    assert refused.status_code == 409
    await fill_cart(customer, [ivanhoe])
    assert (await place_order(customer)).status_code == 201


async def test_a_late_copy_waits_and_cancelling_frees_it_for_waiting_readers(
    app: FastAPI,
    admin: ApiUser,
    customer: ApiUser,
    other_customer: ApiUser,
    register_user: RegisterUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    oliver = await create_book("Oliver Twist")
    made = (await _reserve(customer, oliver, 45)).json()
    await _borrow(admin, other_customer, oliver)
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(AdvanceReservation)
            .where(AdvanceReservation.id == uuid.UUID(made["id"]))
            .values(starts_on=datetime.now(UTC).date())
        )
        await session.commit()
        assert await reservations.activate(session) == 0  # still out on loan

    # Someone waits for the title; the reader gives the reservation up.
    waiting = await register_user()
    assert (await waiting.post(f"{API}/waitlist/{oliver}")).status_code == 201
    orders = (await other_customer.get(f"{API}/orders")).json()["items"]
    await admin.patch(f"{API}/admin/orders/{orders[0]['id']}/status", json={"status": "returned"})
    assert (await waiting.get(f"{API}/users/me/holds")).json() == []  # kept for the reservation
    cancelled = await customer.delete(f"{MINE}/{made['id']}")
    assert cancelled.status_code == 204
    held = (await waiting.get(f"{API}/users/me/holds")).json()
    assert [h["book"]["title"] for h in held] == ["Oliver Twist"]
    gone = await customer.delete(f"{MINE}/{made['id']}")
    assert gone.json()["error"]["code"] == "RESERVATION_NOT_FOUND"

    upcoming = (await admin.get(f"{API}/admin/reservations")).json()
    assert upcoming == []
