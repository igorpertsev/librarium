from __future__ import annotations

import smtplib
import uuid
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select, update

from app.models import Notification, Order
from app.models.enums import NotificationKind, NotificationStatus
from app.services.notifications import MAX_ATTEMPTS, deliver_pending, queue_reminders
from tests.conftest import (
    API,
    ApiUser,
    CreateBook,
    RegisterUser,
    SetBatch,
    fill_cart,
    place_order,
)


async def _notifications(app: FastAPI) -> list[Notification]:
    async with app.state.db.sessionmaker() as session:
        return list(
            (await session.scalars(select(Notification).order_by(Notification.created_at))).all()
        )


async def _order(customer: ApiUser, create_book: CreateBook, title: str) -> dict[str, Any]:
    await fill_cart(customer, [await create_book(title)])
    response = await place_order(customer)
    assert response.status_code == 201
    order: dict[str, Any] = response.json()
    return order


class FakeSender:
    def __init__(self, error: Exception | None = None) -> None:
        self.messages: list[EmailMessage] = []
        self.error = error

    async def __call__(self, message: EmailMessage) -> None:
        if self.error:
            raise self.error
        self.messages.append(message)


async def _deliver(app: FastAPI, send: FakeSender, now: datetime | None = None) -> None:
    async with app.state.db.sessionmaker() as session:
        await deliver_pending(session, app.state.settings, send, now=now)


async def test_order_events_are_queued_with_the_change(
    app: FastAPI, customer: ApiUser, admin: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    confirmed = await _order(customer, create_book, "Confirmed")
    cancelled_by_library = await _order(customer, create_book, "Cancelled by library")
    cancelled_by_customer = await _order(customer, create_book, "Cancelled by customer")

    await admin.patch(f"{API}/admin/orders/{confirmed['id']}/status", json={"status": "confirmed"})
    await admin.patch(
        f"{API}/admin/orders/{cancelled_by_library['id']}/status", json={"status": "cancelled"}
    )
    await customer.post(f"{API}/orders/{cancelled_by_customer['id']}/cancel")

    queued = {(str(n.order_id), n.kind) for n in await _notifications(app)}
    assert queued == {
        (confirmed["id"], NotificationKind.ORDER_RECEIVED),
        (confirmed["id"], NotificationKind.ORDER_CONFIRMED),
        (cancelled_by_library["id"], NotificationKind.ORDER_RECEIVED),
        (cancelled_by_library["id"], NotificationKind.ORDER_CANCELLED),
        (cancelled_by_customer["id"], NotificationKind.ORDER_RECEIVED),
    }
    assert all(n.user_id == uuid.UUID(customer.id) for n in await _notifications(app))


async def test_reminders_are_queued_once(
    app: FastAPI, customer: ApiUser, admin: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    order = await _order(customer, create_book, "Due soon")
    await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})
    today = datetime.now(UTC).date()

    async def run_reminders(due_in_days: int) -> int:
        async with app.state.db.sessionmaker() as session:
            await session.execute(
                update(Order)
                .where(Order.id == uuid.UUID(order["id"]))
                .values(due_date=today + timedelta(days=due_in_days))
            )
            queued = await queue_reminders(session, today=today, due_soon_days=3)
            await session.commit()
            return queued

    assert await run_reminders(10) == 0  # not due soon yet
    assert await run_reminders(2) == 1  # due soon
    assert await run_reminders(2) == 0  # only once
    assert await run_reminders(-1) == 1  # overdue
    kinds = [n.kind for n in await _notifications(app) if str(n.order_id) == order["id"]]
    assert kinds.count(NotificationKind.DUE_SOON) == 1
    assert kinds.count(NotificationKind.OVERDUE) == 1


async def test_delivery_sends_a_bilingual_email(
    app: FastAPI, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    order = await _order(customer, create_book, "The Left Hand of Darkness")
    send = FakeSender()
    await _deliver(app, send)

    assert len(send.messages) == 1
    message = send.messages[0]
    assert customer.email in message["To"]
    number = order["number"]
    assert message["Subject"] == f"We received your request · Заявка получена (#{number})"
    body = message.get_content()
    assert f"Order #{number}: we have received" in body
    assert f"Заказ №{number}: мы получили" in body
    assert "Hello Charlie Customer" in body
    assert "Здравствуйте, Charlie Customer!" in body
    assert "The Left Hand of Darkness" in body
    assert "http://localhost:5173/profile" in body

    (notification,) = await _notifications(app)
    assert notification.status is NotificationStatus.SENT
    assert notification.recipient == customer.email
    assert notification.sent_at is not None

    await _deliver(app, send)
    assert len(send.messages) == 1  # never sent twice


async def test_failed_delivery_is_retried_with_backoff_then_given_up(
    app: FastAPI, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    await _order(customer, create_book, "Unlucky")
    failing = FakeSender(smtplib.SMTPServerDisconnected("connection lost"))
    now = datetime.now(UTC)

    await _deliver(app, failing, now)
    (notification,) = await _notifications(app)
    assert notification.status is NotificationStatus.PENDING
    assert notification.attempts == 1
    assert notification.next_attempt_at == now + timedelta(minutes=5)
    assert notification.last_error is not None
    assert "connection lost" in notification.last_error

    await _deliver(app, failing, now + timedelta(minutes=1))  # not due yet: untouched
    assert (await _notifications(app))[0].attempts == 1

    for step in range(2, MAX_ATTEMPTS + 1):
        await _deliver(app, failing, now + timedelta(days=step))
    (notification,) = await _notifications(app)
    assert notification.attempts == MAX_ATTEMPTS
    assert notification.status is NotificationStatus.FAILED


async def test_stale_notifications_and_disabled_users_are_not_emailed(
    app: FastAPI,
    customer: ApiUser,
    other_customer: ApiUser,
    admin: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    await _order(customer, create_book, "Old news")
    await _order(other_customer, create_book, "Disabled reader")
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(Notification)
            .where(Notification.user_id == uuid.UUID(customer.id))
            .values(created_at=datetime.now(UTC) - timedelta(days=8))
        )
        await session.commit()
    await admin.patch(f"{API}/admin/users/{other_customer.id}", json={"is_active": False})

    send = FakeSender()
    await _deliver(app, send)
    assert send.messages == []
    assert {n.status for n in await _notifications(app)} == {NotificationStatus.EXPIRED}


async def test_confirmation_email_has_the_due_date_in_both_languages(
    app: FastAPI, customer: ApiUser, admin: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    order = await _order(customer, create_book, "Dune")
    await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(Order)
            .where(Order.id == uuid.UUID(order["id"]))
            .values(due_date=date(2026, 12, 6))
        )
        await session.commit()
    send = FakeSender()
    await _deliver(app, send)

    confirmation = next(m for m in send.messages if "handed over" in m["Subject"])
    body = confirmation.get_content()
    assert "Please return them by 6 December 2026." in body
    assert "верните их до 6 декабря 2026 г.\n" in body
    assert "г.." not in body


async def test_emails_use_the_customers_language(
    app: FastAPI, register_user: RegisterUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    russian = await register_user(
        full_name="Ivan Reader", preferred_language="ru", telegram="@ivan"
    )
    english = await register_user(full_name="Emma Reader")
    response = await english.patch(f"{API}/users/me", json={"preferred_language": "en"})
    assert response.json()["preferred_language"] == "en"

    ru_order = await _order(russian, create_book, "Война и мир")
    en_order = await _order(english, create_book, "Emma")
    send = FakeSender()
    await _deliver(app, send)

    by_recipient = {m["To"]: m for m in send.messages}
    ru_mail = next(m for to, m in by_recipient.items() if russian.email in to)
    en_mail = next(m for to, m in by_recipient.items() if english.email in to)
    assert ru_mail["Subject"] == f"Заявка получена (№{ru_order['number']})"
    assert "Здравствуйте, Ivan Reader!" in ru_mail.get_content()
    assert "Hello" not in ru_mail.get_content()
    assert en_mail["Subject"] == f"We received your request (#{en_order['number']})"
    assert "Здравствуйте" not in en_mail.get_content()

    response = await english.patch(f"{API}/users/me", json={"preferred_language": "de"})
    assert response.status_code == 422


async def test_emails_use_the_title_in_the_readers_language(
    app: FastAPI, admin: ApiUser, register_user: RegisterUser, set_batch: SetBatch
) -> None:
    await set_batch(1)
    reader = await register_user()
    assert (
        await reader.patch(f"{API}/users/me", json={"preferred_language": "ru"})
    ).status_code == 200
    created = await admin.post(
        f"{API}/admin/books",
        json={
            "title": "The Catcher in the Rye",
            "author": "J. D. Salinger",
            "category": "fiction",
            "translations": [
                {"language": "ru", "title": "Над пропастью во ржи", "author": "Джером Сэлинджер"}
            ],
        },
    )
    await fill_cart(reader, [created.json()["id"]])
    assert (await place_order(reader)).status_code == 201

    send = FakeSender()
    await _deliver(app, send)
    (message,) = send.messages
    body = message.get_content()
    # The translated title, with the title of the copy on the shelf in brackets.
    assert "Над пропастью во ржи (The Catcher in the Rye) — Джером Сэлинджер" in body
