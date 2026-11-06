from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import update

from app.models import Order
from tests.conftest import API, ApiUser, CreateBook, SetBatch, fill_cart, place_order


async def _borrowed(admin: ApiUser, customer: ApiUser, create_book: CreateBook, title: str) -> str:
    await fill_cart(customer, [await create_book(title)])
    order = (await place_order(customer)).json()
    await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})
    order_id: str = order["id"]
    return order_id


async def _make_overdue(app: FastAPI, order_id: str, days: int) -> None:
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(Order)
            .where(Order.id == uuid.UUID(order_id))
            .values(due_date=datetime.now(UTC).date() - timedelta(days=days))
        )
        await session.commit()


async def test_overdue_readers_cannot_order_and_pay_a_late_fee(
    app: FastAPI, admin: ApiUser, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    settings = await admin.patch(f"{API}/admin/settings", json={"late_fee_per_day": "0.50"})
    assert settings.status_code == 200, settings.text
    rules = (await customer.get(f"{API}/library/rules")).json()
    assert (rules["block_overdue"], rules["late_fee_per_day"]) == (True, "0.50")

    order_id = await _borrowed(admin, customer, create_book, "Dune")
    await _make_overdue(app, order_id, days=4)

    # No new orders while the loan is overdue.
    await fill_cart(customer, [await create_book("Emma")])
    blocked = await place_order(customer)
    assert blocked.status_code == 409
    body = blocked.json()["error"]
    assert body["code"] == "OVERDUE_LOANS"
    assert len(body["details"]["orders"]) == 1

    # Returned 4 days late: 4 x 0.50.
    returned = await admin.patch(
        f"{API}/admin/orders/{order_id}/status", json={"status": "returned"}
    )
    assert returned.json()["late_fee"] == "2.00"
    assert returned.json()["late_fee_settled_at"] is None
    assert (await place_order(customer)).status_code == 201  # unblocked once returned

    paid = await admin.patch(f"{API}/admin/orders/{order_id}/late-fee", json={"action": "paid"})
    assert paid.json()["late_fee"] == "2.00"
    assert paid.json()["late_fee_settled_at"] is not None
    twice = await admin.patch(f"{API}/admin/orders/{order_id}/late-fee", json={"action": "paid"})
    assert twice.status_code == 409


async def test_the_library_can_turn_blocking_off_and_waive_fees(
    app: FastAPI, admin: ApiUser, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    await admin.patch(
        f"{API}/admin/settings", json={"block_overdue": False, "late_fee_per_day": "1.00"}
    )
    order_id = await _borrowed(admin, customer, create_book, "Dune")
    await _make_overdue(app, order_id, days=2)
    await fill_cart(customer, [await create_book("Emma")])
    assert (await place_order(customer)).status_code == 201  # not blocked

    await admin.patch(f"{API}/admin/orders/{order_id}/status", json={"status": "returned"})
    waived = await admin.patch(f"{API}/admin/orders/{order_id}/late-fee", json={"action": "waived"})
    assert waived.json()["late_fee"] == "0.00"
    again = await admin.patch(f"{API}/admin/orders/{order_id}/late-fee", json={"action": "paid"})
    assert again.status_code == 409  # nothing left to settle


async def test_on_time_returns_have_no_fee(
    admin: ApiUser, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    await admin.patch(f"{API}/admin/settings", json={"late_fee_per_day": "1.00"})
    order_id = await _borrowed(admin, customer, create_book, "Dune")
    returned = await admin.patch(
        f"{API}/admin/orders/{order_id}/status", json={"status": "returned"}
    )
    assert returned.json()["late_fee"] is None
