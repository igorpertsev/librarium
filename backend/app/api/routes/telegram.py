"""Telegram webhook: with TELEGRAM_WEBHOOK_SECRET set, Telegram posts the bot's updates here."""

from __future__ import annotations

import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, Request

from app.api.dependencies import SessionDep, SettingsDep
from app.core.config import Settings
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.schemas.common import ApiModel, error_responses
from app.services import telegram

router = APIRouter(prefix="/telegram", tags=["telegram"])


class WebhookAck(ApiModel):
    ok: bool


def get_telegram_bot(request: Request, settings: SettingsDep) -> telegram.Bot | None:
    return telegram.make_bot(settings, request.app.state.http)


def _check_secret(settings: Settings, given: str | None) -> None:
    expected = settings.telegram_webhook_secret
    if expected is None or not settings.telegram_bot_token:
        raise NotFoundError("The Telegram webhook is not set up", code="TELEGRAM_WEBHOOK_OFF")
    if given is None or not secrets.compare_digest(given, expected.get_secret_value()):
        raise PermissionDeniedError("Wrong webhook secret", code="TELEGRAM_WEBHOOK_SECRET")


@router.post(
    "/webhook",
    response_model=WebhookAck,
    responses=error_responses(403, 404),
    description="Called by Telegram (setWebhook with secret_token). An update seen already "
    "is acknowledged without being handled again.",
)
async def telegram_webhook(
    update: Annotated[dict[str, Any], Body(description="A Telegram Update object")],
    session: SessionDep,
    settings: SettingsDep,
    bot: Annotated[telegram.Bot | None, Depends(get_telegram_bot)],
    secret: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
) -> WebhookAck:
    _check_secret(settings, secret)
    if bot is not None:
        await telegram.handle_update(session, bot, update)
    return WebhookAck(ok=True)
