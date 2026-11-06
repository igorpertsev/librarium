from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.rate_limit import FORGOT_PASSWORD_PER_EMAIL
from app.core.security import create_password_reset_token
from app.models import User
from tests.conftest import API, PASSWORD, ApiUser, MakeClient

NEW_PASSWORD = "a-brand-new-password"


class FakeSender:
    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    async def __call__(self, message: EmailMessage) -> None:
        self.messages.append(message)


@pytest.fixture
def outbox(app: FastAPI) -> Iterator[FakeSender]:
    original = app.state.mail_sender
    app.state.mail_sender = FakeSender()
    yield app.state.mail_sender
    app.state.mail_sender = original


def _token(message: EmailMessage) -> str:
    match = re.search(r"/reset-password#token=([\w.-]+)", message.get_content())
    assert match, message.get_content()
    return match.group(1)


async def _forgot(client: AsyncClient, email: str) -> int:
    return (await client.post(f"{API}/auth/forgot-password", json={"email": email})).status_code


async def _reset(client: AsyncClient, token: str, password: str = NEW_PASSWORD) -> int:
    response = await client.post(
        f"{API}/auth/reset-password", json={"token": token, "new_password": password}
    )
    return response.status_code


async def _login(client: AsyncClient, email: str, password: str) -> int:
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    return response.status_code


async def test_reset_link_sets_a_new_password_once(
    client: AsyncClient, customer: ApiUser, outbox: FakeSender
) -> None:
    assert await _forgot(client, customer.email.upper()) == 202
    (message,) = outbox.messages
    assert customer.email in message["To"]
    assert message["Subject"] == "Reset your password · Сброс пароля"
    body = message.get_content()
    assert "http://localhost:5173/reset-password#token=" in body
    assert "Здравствуйте, Charlie Customer!" in body
    token = _token(message)

    assert await _reset(client, token) == 204
    assert await _login(client, customer.email, PASSWORD) == 401
    assert await _login(client, customer.email, NEW_PASSWORD) == 200

    # The same link cannot be used twice.
    response = await client.post(
        f"{API}/auth/reset-password", json={"token": token, "new_password": "yet-another-pass"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_RESET_TOKEN"


async def test_reset_signs_out_every_session(
    client: AsyncClient, customer: ApiUser, outbox: FakeSender
) -> None:
    await _forgot(client, customer.email)
    assert await _reset(client, _token(outbox.messages[0])) == 204
    response = await customer.client.post(f"{API}/auth/refresh")
    assert response.status_code == 401


async def test_unknown_and_disabled_accounts_get_the_same_answer(
    client: AsyncClient, admin: ApiUser, customer: ApiUser, outbox: FakeSender
) -> None:
    assert await _forgot(client, "nobody@example.com") == 202
    response = await admin.patch(f"{API}/admin/users/{customer.id}", json={"is_active": False})
    assert response.status_code == 200
    assert await _forgot(client, customer.email) == 202
    assert outbox.messages == []


async def test_invalid_expired_and_foreign_tokens_are_rejected(
    app: FastAPI, client: AsyncClient, customer: ApiUser
) -> None:
    assert await _reset(client, "not-a-token") == 400
    # An access token is not a reset token.
    assert await _reset(client, customer.access_token) == 400

    async with app.state.db.sessionmaker() as session:
        user = await session.get(User, customer.data["id"])
        assert user is not None
        expired = create_password_reset_token(
            user_id=user.id,
            password_hash=user.password_hash,
            settings=app.state.settings,
            now=datetime.now(UTC) - timedelta(hours=2),
        )
    assert await _reset(client, expired) == 400

    response = await client.post(
        f"{API}/auth/reset-password", json={"token": "x", "new_password": "short"}
    )
    assert response.status_code == 422


async def test_reset_emails_per_address_are_limited(
    make_client: MakeClient, customer: ApiUser, outbox: FakeSender
) -> None:
    for _ in range(FORGOT_PASSWORD_PER_EMAIL.attempts):
        assert await _forgot(make_client(), customer.email) == 202
    assert await _forgot(make_client(), customer.email) == 429
    assert len(outbox.messages) == FORGOT_PASSWORD_PER_EMAIL.attempts
