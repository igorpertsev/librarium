"""Notifications through a Telegram bot (optional: ``TELEGRAM_BOT_TOKEN``).

Linking: the profile asks for a one-time link (``t.me/<bot>?start=<code>``, 15 minutes); when
the reader presses Start, the bot receives ``/start <code>`` and the reader's chat is linked.
``/stop`` unlinks it. The notifier reads the bot's updates every cycle (long polling is not
needed: ``getUpdates`` with an offset confirms what was read) and sends each notification
there too, once (``notifications.telegram_sent_at``).
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ConflictError
from app.models import User
from app.models.enums import UiLanguage

logger = logging.getLogger(__name__)

LINK_TTL = timedelta(minutes=15)
MAX_MESSAGE = 4000  # Telegram allows 4096 characters


class TelegramError(Exception):
    pass


class Bot(Protocol):
    async def send(self, chat_id: int, text: str) -> None: ...

    async def updates(self, offset: int | None) -> list[dict[str, Any]]: ...


class TelegramBot:
    """The few Bot API calls we need, over our shared HTTP client."""

    def __init__(self, http: httpx.AsyncClient, token: str) -> None:
        self._http = http
        self._base = f"https://api.telegram.org/bot{token}"

    async def _call(self, method: str, payload: dict[str, Any]) -> Any:
        try:
            response = await self._http.post(f"{self._base}/{method}", json=payload, timeout=15)
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramError(f"{method}: {type(exc).__name__}") from exc
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description', 'failed')}")
        return data.get("result")

    async def send(self, chat_id: int, text: str) -> None:
        await self._call(
            "sendMessage",
            {"chat_id": chat_id, "text": text[:MAX_MESSAGE], "disable_web_page_preview": True},
        )

    async def updates(self, offset: int | None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": 0, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        result = await self._call("getUpdates", payload)
        return list(result or [])


def make_bot(settings: Settings, http: httpx.AsyncClient) -> TelegramBot | None:
    token = settings.telegram_bot_token
    return TelegramBot(http, token.get_secret_value()) if token else None


# --- Linking --------------------------------------------------------------------------------


async def start_link(session: AsyncSession, settings: Settings, user: User) -> tuple[str, datetime]:
    if not (settings.telegram_bot_token and settings.telegram_bot_username):
        raise ConflictError(
            "Telegram is not set up for this library", code="TELEGRAM_NOT_CONFIGURED"
        )
    code = secrets.token_urlsafe(24)
    expires = datetime.now(UTC) + LINK_TTL
    user.telegram_link_code = code
    user.telegram_link_expires_at = expires
    await session.commit()
    return f"https://t.me/{settings.telegram_bot_username}?start={code}", expires


async def unlink(session: AsyncSession, user: User) -> None:
    user.telegram_chat_id = None
    user.telegram_link_code = None
    user.telegram_link_expires_at = None
    await session.commit()


def _say(user: User | None, english: str, russian: str) -> str:
    if user is not None and user.preferred_language is UiLanguage.RU:
        return russian
    if user is not None and user.preferred_language is UiLanguage.EN:
        return english
    return f"{english}\n\n{russian}"


async def _handle(session: AsyncSession, bot: Bot, message: dict[str, Any]) -> None:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = str(message.get("text") or "").strip()
    if not isinstance(chat_id, int) or chat.get("type") != "private":
        return
    linked = await session.scalar(select(User).where(User.telegram_chat_id == chat_id))
    if text.startswith("/start"):
        code = text.removeprefix("/start").strip()
        user = (
            await session.scalar(select(User).where(User.telegram_link_code == code))
            if code
            else None
        )
        expires = user.telegram_link_expires_at if user else None
        if user is None or expires is None or expires <= datetime.now(UTC) or not user.is_active:
            reply = _say(
                linked,
                "This link has expired. Open “Connect Telegram” on your profile again.",
                "Ссылка устарела. Нажмите «Подключить Telegram» в профиле ещё раз.",
            )
        else:
            if linked is not None and linked.id != user.id:
                linked.telegram_chat_id = None  # one chat follows one account
            user.telegram_chat_id = chat_id
            user.telegram_link_code = None
            user.telegram_link_expires_at = None
            await session.flush()
            reply = _say(
                user,
                f"Hello {user.full_name}! You will get Little Dragon library news here. "
                "Send /stop to turn it off.",
                f"Здравствуйте, {user.full_name}! Новости библиотеки Little Dragon будут "
                "приходить сюда. Отправьте /stop, чтобы отключить.",
            )
    elif text.startswith("/stop") and linked is not None:
        linked.telegram_chat_id = None
        reply = _say(
            linked,
            "Done: no more messages here. You can connect again from your profile.",
            "Готово: сообщений больше не будет. Подключиться снова можно в профиле.",
        )
    else:
        reply = _say(
            linked,
            "Connect this chat from your Little Dragon profile (“Connect Telegram”).",
            "Подключите этот чат в профиле Little Dragon («Подключить Telegram»).",
        )
    await session.commit()
    try:
        await bot.send(chat_id, reply)
    except TelegramError as exc:
        logger.warning("Telegram reply failed: %s", exc)


async def process_updates(session: AsyncSession, bot: Bot) -> int:
    """Read the bot's new messages (link and unlink requests); returns how many."""
    try:
        updates = await bot.updates(None)
    except TelegramError as exc:
        logger.warning("Telegram updates failed: %s", exc)
        return 0
    if not updates:
        return 0
    for update in updates:
        if isinstance(update.get("message"), dict):
            await _handle(session, bot, update["message"])
    # Asking from the next id confirms these updates, so they are not read again.
    last = max(int(u.get("update_id", 0)) for u in updates)
    try:
        await bot.updates(last + 1)
    except TelegramError as exc:  # pragma: no cover - read again next time, harmless
        logger.warning("Telegram confirm failed: %s", exc)
    return len(updates)
