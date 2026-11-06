from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, update

from app.models import Notification, Order
from app.models.enums import NotificationKind
from app.services import notifications
from tests.conftest import API, ApiUser, CreateBook, SetBatch, fill_cart, place_order


async def _borrowed_order(
    customer: ApiUser, admin: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> dict[str, Any]:
    await set_batch(1)
    await fill_cart(customer, [await create_book()])
    order: dict[str, Any] = (await place_order(customer)).json()
    response = await admin.patch(
        f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"}
    )
    assert response.status_code == 200, response.text
    confirmed: dict[str, Any] = response.json()
    return confirmed


async def _renew(customer: ApiUser, order_id: str) -> Any:
    return await customer.post(f"{API}/orders/{order_id}/renew")


async def test_a_borrowed_order_can_be_extended_once(
    customer: ApiUser, admin: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    order = await _borrowed_order(customer, admin, create_book, set_batch)
    assert order["renewal_count"] == 0

    response = await _renew(customer, order["id"])
    assert response.status_code == 200, response.text
    renewed = response.json()
    assert renewed["renewal_count"] == 1
    assert date.fromisoformat(renewed["due_date"]) == date.fromisoformat(
        order["due_date"]
    ) + timedelta(days=30)

    response = await _renew(customer, order["id"])
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "RENEWAL_NOT_ALLOWED"
    assert error["details"] == {"reason": "limit_reached"}


async def test_only_borrowed_and_not_overdue_orders_can_be_extended(
    app: FastAPI, customer: ApiUser, admin: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    await fill_cart(customer, [await create_book()])
    pending = (await place_order(customer)).json()
    response = await _renew(customer, pending["id"])
    assert response.json()["error"]["details"] == {"reason": "not_borrowed"}

    order = await _borrowed_order(customer, admin, create_book, set_batch)
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(Order)
            .where(Order.id == uuid.UUID(order["id"]))
            .values(due_date=datetime.now(UTC).date() - timedelta(days=1))
        )
        await session.commit()
    response = await _renew(customer, order["id"])
    assert response.json()["error"]["details"] == {"reason": "overdue"}


async def test_other_customers_cannot_extend_an_order(
    customer: ApiUser,
    other_customer: ApiUser,
    admin: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    order = await _borrowed_order(customer, admin, create_book, set_batch)
    response = await _renew(other_customer, order["id"])
    assert response.status_code == 404


async def test_the_library_sets_how_often_loans_can_be_extended(
    client: AsyncClient,
    customer: ApiUser,
    admin: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    rules = (await client.get(f"{API}/library/rules")).json()  # public, no sign-in
    assert rules["max_renewals"] == 1
    assert rules["loan_period_days"] == 30

    response = await admin.patch(f"{API}/admin/settings", json={"max_renewals": 0})
    assert response.status_code == 200
    order = await _borrowed_order(customer, admin, create_book, set_batch)
    assert (await _renew(customer, order["id"])).status_code == 409

    await admin.patch(f"{API}/admin/settings", json={"max_renewals": 2, "loan_period_days": 14})
    first = (await _renew(customer, order["id"])).json()
    second = (await _renew(customer, order["id"])).json()
    assert second["renewal_count"] == 2
    assert date.fromisoformat(second["due_date"]) == date.fromisoformat(
        first["due_date"]
    ) + timedelta(days=14)

    response = await admin.patch(f"{API}/admin/settings", json={"max_renewals": 11})
    assert response.status_code == 422


async def test_extending_a_loan_resets_its_due_date_reminders(
    app: FastAPI, customer: ApiUser, admin: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    order = await _borrowed_order(customer, admin, create_book, set_batch)
    order_id = uuid.UUID(order["id"])
    async with app.state.db.sessionmaker() as session:
        await notifications.enqueue(
            session,
            order_id=order_id,
            user_id=uuid.UUID(customer.id),
            kind=NotificationKind.DUE_SOON,
        )
        await session.commit()

    assert (await _renew(customer, order["id"])).status_code == 200
    async with app.state.db.sessionmaker() as session:
        kinds = (
            await session.scalars(
                select(Notification.kind).where(Notification.order_id == order_id)
            )
        ).all()
    assert NotificationKind.DUE_SOON not in kinds
    assert NotificationKind.ORDER_CONFIRMED in kinds  # other emails are kept
