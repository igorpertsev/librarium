from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select, update

from app.models import Notification, Order
from app.models.enums import NotificationKind, NotificationStatus
from tests.conftest import API, ApiUser, CreateBook, SetBatch, fill_cart, place_order


async def _borrowed(
    customer: ApiUser, admin: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> dict[str, Any]:
    await set_batch(1)
    await fill_cart(customer, [await create_book()])
    order: dict[str, Any] = (await place_order(customer)).json()
    await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})
    return order


async def _make_overdue(app: FastAPI, order_id: str) -> None:
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(Order)
            .where(Order.id == uuid.UUID(order_id))
            .values(due_date=datetime.now(UTC).date() - timedelta(days=3))
        )
        await session.commit()


async def _reminders(app: FastAPI, order_id: str) -> list[Notification]:
    async with app.state.db.sessionmaker() as session:
        return list(
            (
                await session.scalars(
                    select(Notification).where(
                        Notification.order_id == uuid.UUID(order_id),
                        Notification.kind.in_(
                            [NotificationKind.OVERDUE, NotificationKind.DUE_SOON]
                        ),
                    )
                )
            ).all()
        )


async def test_librarian_reminds_an_overdue_customer_once_a_day(
    app: FastAPI, customer: ApiUser, admin: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    order = await _borrowed(customer, admin, create_book, set_batch)
    await _make_overdue(app, order["id"])

    response = await admin.post(f"{API}/admin/orders/{order['id']}/remind")
    assert response.status_code == 202, response.text
    assert response.json()["kind"] == "overdue"
    (reminder,) = await _reminders(app, order["id"])
    assert reminder.status is NotificationStatus.PENDING

    again = await admin.post(f"{API}/admin/orders/{order['id']}/remind")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "REMINDER_RECENTLY_SENT"

    # A day later the old reminder is replaced by a new one.
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(Notification)
            .where(Notification.id == reminder.id)
            .values(
                created_at=datetime.now(UTC) - timedelta(days=2), status=NotificationStatus.SENT
            )
        )
        await session.commit()
    assert (await admin.post(f"{API}/admin/orders/{order['id']}/remind")).status_code == 202
    (new_reminder,) = await _reminders(app, order["id"])
    assert new_reminder.id != reminder.id
    assert new_reminder.status is NotificationStatus.PENDING


async def test_a_loan_that_is_not_overdue_gets_a_due_soon_reminder(
    app: FastAPI, customer: ApiUser, admin: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    order = await _borrowed(customer, admin, create_book, set_batch)
    response = await admin.post(f"{API}/admin/orders/{order['id']}/remind")
    assert response.json()["kind"] == "due_soon"


async def test_only_borrowed_orders_and_only_librarians(
    customer: ApiUser, admin: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    await fill_cart(customer, [await create_book()])
    pending = (await place_order(customer)).json()
    response = await admin.post(f"{API}/admin/orders/{pending['id']}/remind")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ORDER_NOT_BORROWED"
    assert (await customer.post(f"{API}/admin/orders/{pending['id']}/remind")).status_code == 403
    assert (await admin.post(f"{API}/admin/orders/{uuid.uuid4()}/remind")).status_code == 404
