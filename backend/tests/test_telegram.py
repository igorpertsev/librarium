from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select, update

from app.models import Notification, User
from app.models.enums import NotificationKind, NotificationStatus
from app.services import telegram
from app.services.notifications import deliver_pending
from tests.conftest import API, ApiUser, SetBatch, fill_cart, place_order
from tests.test_holds import FakeSender


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.pending: list[dict[str, Any]] = []
        self.offsets: list[int | None] = []
        self.fail = False

    async def send(self, chat_id: int, text: str) -> None:
        if self.fail:
            raise telegram.TelegramError("sendMessage: blocked")
        self.sent.append((chat_id, text))

    async def updates(self, offset: int | None) -> list[dict[str, Any]]:
        self.offsets.append(offset)
        if offset is not None:
            self.pending = [u for u in self.pending if u["update_id"] >= offset]
            return []
        return list(self.pending)

    def message(self, update_id: int, chat_id: int, text: str) -> None:
        self.pending.append(
            {
                "update_id": update_id,
                "message": {"chat": {"id": chat_id, "type": "private"}, "text": text},
            }
        )


def _with_bot(app: FastAPI) -> Any:
    return app.state.settings.model_copy(
        update={"telegram_bot_token": SecretStr("123:abc"), "telegram_bot_username": "dragon_bot"}
    )


async def _user(app: FastAPI, reader: ApiUser) -> User:
    async with app.state.db.sessionmaker() as session:
        user: User | None = await session.get(User, uuid.UUID(reader.id))
        assert user is not None
        return user


async def test_readers_link_their_chat_with_a_one_time_code(
    app: FastAPI, customer: ApiUser
) -> None:
    refused = await customer.post(f"{API}/users/me/telegram/link")
    assert refused.json()["error"]["code"] == "TELEGRAM_NOT_CONFIGURED"
    assert (await customer.get(f"{API}/library/rules")).json()["telegram_bot"] is None

    bot = FakeBot()
    async with app.state.db.sessionmaker() as session:
        user = await session.get(User, uuid.UUID(customer.id))
        assert user is not None
        url, _ = await telegram.start_link(session, _with_bot(app), user)
    code = url.rsplit("=", 1)[1]
    assert url == f"https://t.me/dragon_bot?start={code}"

    bot.message(1, 777, "/start wrong-code")
    bot.message(2, 777, f"/start {code}")
    async with app.state.db.sessionmaker() as session:
        assert await telegram.process_updates(session, bot) == 2
    assert bot.offsets == [None, 3]  # the updates were confirmed
    assert "expired" in bot.sent[0][1]
    assert bot.sent[1][0] == 777
    assert "Little Dragon" in bot.sent[1][1]
    me = (await customer.get(f"{API}/users/me")).json()
    assert me["telegram_connected"] is True
    linked = await _user(app, customer)
    assert linked.telegram_link_code is None  # used once

    bot.message(3, 777, "/stop")
    async with app.state.db.sessionmaker() as session:
        await telegram.process_updates(session, bot)
    assert (await customer.get(f"{API}/users/me")).json()["telegram_connected"] is False


async def test_notifications_go_to_telegram_once_even_without_email(
    app: FastAPI,
    admin: ApiUser,
    customer: ApiUser,
    other_customer: ApiUser,
    create_book: Any,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(User).where(User.id == uuid.UUID(customer.id)).values(telegram_chat_id=555)
        )
        await session.commit()
    for reader in (customer, other_customer):
        await fill_cart(reader, [await create_book()])
        assert (await place_order(reader)).status_code == 201

    # No SMTP: only the reader with Telegram is served; the other email waits.
    bot = FakeBot()
    async with app.state.db.sessionmaker() as session:
        report = await deliver_pending(session, app.state.settings, None, telegram=bot)
    assert report.sent == 1
    assert [chat for chat, _ in bot.sent] == [555]
    assert "We received your request" in bot.sent[0][1]
    async with app.state.db.sessionmaker() as session:
        rows = (await session.execute(select(Notification.user_id, Notification.status))).all()
    statuses = {str(user_id): status for user_id, status in rows}
    assert statuses[customer.id] is NotificationStatus.SENT
    assert statuses[other_customer.id] is NotificationStatus.PENDING

    # With email too: a failed email is retried later, but Telegram is not sent twice.
    order_id = (await customer.get(f"{API}/orders")).json()["items"][0]["id"]
    await admin.patch(f"{API}/admin/orders/{order_id}/status", json={"status": "confirmed"})

    async def broken(_: Any) -> None:
        raise OSError("SMTP down")

    async with app.state.db.sessionmaker() as session:
        await deliver_pending(session, app.state.settings, broken, telegram=bot)
    confirmed = [text for _, text in bot.sent if "handed over" in text]
    assert len(confirmed) == 1
    later = datetime.now(UTC) + timedelta(hours=1)
    send = FakeSender()
    async with app.state.db.sessionmaker() as session:
        await deliver_pending(session, app.state.settings, send, telegram=bot, now=later)
    assert len([text for _, text in bot.sent if "handed over" in text]) == 1
    assert any("handed over" in m.get_content() for m in send.messages)
    kinds = [n for n in bot.sent if NotificationKind.ORDER_CONFIRMED.value in n[1]]
    assert kinds == []  # messages are human text, not kind names
