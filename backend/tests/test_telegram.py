from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import select, update

from app.api.routes.telegram import get_telegram_bot
from app.core.config import Settings
from app.models import Notification, User
from app.models.enums import NotificationKind, NotificationStatus
from app.services import telegram
from app.services.notifications import deliver_pending
from tests.conftest import API, ApiUser, SetBatch, SwapSettings, fill_cart, place_order
from tests.test_holds import FakeSender


@pytest.fixture(autouse=True)
def _forget_seen_updates() -> None:
    telegram._recent_updates.clear()  # update ids are reused across tests


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


WEBHOOK = f"{API}/telegram/webhook"
SECRET = "webhook-secret-" + "w" * 30


async def test_the_webhook_needs_its_secret_and_links_a_chat(
    app: FastAPI, client: AsyncClient, customer: ApiUser, swap_settings: SwapSettings
) -> None:
    assert (await client.post(WEBHOOK, json={"update_id": 1})).status_code == 404  # not set up

    settings = _with_bot(app).model_copy(update={"telegram_webhook_secret": SecretStr(SECRET)})
    assert telegram.polls_updates(_with_bot(app))
    assert not telegram.polls_updates(settings)  # the notifier stops polling
    swap_settings(settings)
    bot = FakeBot()
    app.dependency_overrides[get_telegram_bot] = lambda: bot
    try:
        for headers in ({}, {"X-Telegram-Bot-Api-Secret-Token": "w" * 40}):
            refused = await client.post(WEBHOOK, json={"update_id": 1}, headers=headers)
            assert refused.status_code == 403
            assert refused.json()["error"]["code"] == "TELEGRAM_WEBHOOK_SECRET"

        async with app.state.db.sessionmaker() as session:
            user = await session.get(User, uuid.UUID(customer.id))
            assert user is not None
            url, _ = await telegram.start_link(session, settings, user)
        start = {
            "update_id": 9001,
            "message": {
                "chat": {"id": 888, "type": "private"},
                "text": url.split("?")[1].replace("start=", "/start "),
            },
        }
        signed = {"X-Telegram-Bot-Api-Secret-Token": SECRET}
        accepted = await client.post(WEBHOOK, json=start, headers=signed)
        assert (accepted.status_code, accepted.json()) == (200, {"ok": True})
        assert (await customer.get(f"{API}/users/me")).json()["telegram_connected"] is True
        assert [chat for chat, _ in bot.sent] == [888]

        # Telegram sends it again (no answer in time): acknowledged, not answered twice.
        again = await client.post(WEBHOOK, json=start, headers=signed)
        assert again.status_code == 200
        assert len(bot.sent) == 1
        # Updates that are not chat messages are acknowledged and ignored.
        for odd in ({"update_id": 9002, "message": {"chat": "nope"}}, {"update_id": 9003}):
            assert (await client.post(WEBHOOK, json=odd, headers=signed)).status_code == 200
        assert len(bot.sent) == 1
    finally:
        app.dependency_overrides.pop(get_telegram_bot, None)


async def test_the_webhook_is_registered_with_its_secret() -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        result: Any = {"url": "https://lib.example/api/v1/telegram/webhook"}
        return httpx.Response(200, json={"ok": True, "result": result})

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        bot = telegram.TelegramBot(http, "123:abc")
        await bot.set_webhook("https://lib.example/api/v1/telegram/webhook", SECRET)
        info = await bot.webhook_info()
        await bot.delete_webhook()
    assert [r.url.path for r in seen] == [
        "/bot123:abc/setWebhook",
        "/bot123:abc/getWebhookInfo",
        "/bot123:abc/deleteWebhook",
    ]
    assert json.loads(seen[0].content) == {
        "url": "https://lib.example/api/v1/telegram/webhook",
        "secret_token": SECRET,
        "allowed_updates": ["message"],
    }
    assert info["url"].endswith("/telegram/webhook")


def test_the_webhook_secret_is_checked() -> None:
    with pytest.raises(ValidationError, match="TELEGRAM_WEBHOOK_SECRET must be"):
        Settings(
            _env_file=None,
            telegram_bot_token=SecretStr("123:abc"),
            telegram_webhook_secret=SecretStr("short"),
        )
    with pytest.raises(ValidationError, match="needs TELEGRAM_BOT_TOKEN"):
        Settings(_env_file=None, telegram_webhook_secret=SecretStr(SECRET))
