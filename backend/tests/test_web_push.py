"""Web Push: subscriptions, and delivery checked end to end with real encryption and signing."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import http_ece
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from py_vapid import Vapid02
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select

from app.core.config import Settings
from app.models import Notification, PushSubscription
from app.models.enums import NotificationStatus
from app.services import web_push
from app.services.notifications import deliver_pending
from tests.conftest import (
    API,
    ApiUser,
    SetBatch,
    SwapSettings,
    fill_cart,
    place_order,
)

URL = f"{API}/users/me/push-subscriptions"
PUBLIC, PRIVATE = web_push.generate_keys()
CONTACT = "mailto:library@example.com"


class Browser:
    """What a browser keeps for one subscription: its key pair and auth secret."""

    def __init__(self, endpoint: str) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)
        self.endpoint = endpoint

    def subscription(self) -> dict[str, Any]:
        public = self.key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        return {
            "endpoint": self.endpoint,
            "keys": {
                "p256dh": web_push.b64url_encode(public),
                "auth": web_push.b64url_encode(self.auth),
            },
        }

    def read(self, body: bytes) -> dict[str, Any]:
        plain = http_ece.decrypt(
            body, private_key=self.key, auth_secret=self.auth, version="aes128gcm"
        )
        message: dict[str, Any] = json.loads(plain)
        return message


def _push_settings(app: FastAPI) -> Settings:
    settings: Settings = app.state.settings.model_copy(
        update={
            "web_push_public_key": PUBLIC,
            "web_push_private_key": SecretStr(PRIVATE),
            "web_push_contact": CONTACT,
        }
    )
    return settings


def test_only_browser_push_services_are_accepted() -> None:
    for good in (
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://web.push.apple.com/abc",
        "https://db5p.notify.windows.com/w/?token=abc",
    ):
        assert web_push.allowed_endpoint(good), good
    for bad in (
        "http://fcm.googleapis.com/fcm/send/abc",  # not https
        "https://localhost/abc",
        "https://169.254.169.254/latest/meta-data",
        "https://fcm.googleapis.com.evil.example/abc",
        "https://evilnotify.windows.com/abc",
        "https://user:pw@fcm.googleapis.com/abc",
    ):
        assert not web_push.allowed_endpoint(bad), bad


def test_push_settings_come_together() -> None:
    with pytest.raises(ValidationError, match="Web Push needs"):
        Settings(_env_file=None, web_push_public_key=PUBLIC)
    with pytest.raises(ValidationError, match="mailto: or https://"):
        Settings(
            _env_file=None,
            web_push_public_key=PUBLIC,
            web_push_private_key=SecretStr(PRIVATE),
            web_push_contact="library@example.com",
        )


async def test_readers_subscribe_and_unsubscribe_their_devices(
    app: FastAPI, customer: ApiUser, other_customer: ApiUser, swap_settings: SwapSettings
) -> None:
    browser = Browser("https://fcm.googleapis.com/fcm/send/device-1")
    off = await customer.post(URL, json=browser.subscription())
    assert off.json()["error"]["code"] == "PUSH_NOT_CONFIGURED"
    assert (await customer.get(f"{API}/library/rules")).json()["web_push_key"] is None

    swap_settings(_push_settings(app))
    assert (await customer.get(f"{API}/library/rules")).json()["web_push_key"] == PUBLIC
    assert (await customer.post(URL, json=browser.subscription())).status_code == 204
    again = await customer.post(URL, json=browser.subscription())  # idempotent
    assert again.status_code == 204

    bad = browser.subscription()
    for change in (
        {"endpoint": "https://intranet.example/hook"},
        {"keys": {"p256dh": "AAAA", "auth": bad["keys"]["auth"]}},
        {"keys": {"p256dh": bad["keys"]["p256dh"], "auth": "not-16-bytes"}},
    ):
        response = await customer.post(URL, json={**bad, **change})
        assert response.status_code == 422, (change, response.text)

    # The same browser signed in as someone else now notifies them.
    assert (await other_customer.post(URL, json=browser.subscription())).status_code == 204
    async with app.state.db.sessionmaker() as session:
        owners = (await session.scalars(select(PushSubscription.user_id))).all()
    assert [str(o) for o in owners] == [other_customer.id]

    gone = await other_customer.delete(URL, params={"endpoint": browser.endpoint})
    assert gone.status_code == 204
    async with app.state.db.sessionmaker() as session:
        assert await session.scalar(select(func.count(PushSubscription.id))) == 0


async def test_notifications_reach_subscribed_browsers_encrypted_and_signed(
    app: FastAPI,
    admin: ApiUser,
    customer: ApiUser,
    other_customer: ApiUser,
    create_book: Any,
    set_batch: SetBatch,
    swap_settings: SwapSettings,
) -> None:
    settings = _push_settings(app)
    swap_settings(settings)
    phone = Browser("https://fcm.googleapis.com/fcm/send/phone")
    laptop = Browser("https://updates.push.services.mozilla.com/wpush/v2/laptop")
    for browser in (phone, laptop):
        assert (await customer.post(URL, json=browser.subscription())).status_code == 204
    await set_batch(1)
    for reader in (customer, other_customer):
        await fill_cart(reader, [await create_book()])
        assert (await place_order(reader)).status_code == 201

    received: list[httpx.Request] = []
    answers = {phone.endpoint: 503, laptop.endpoint: 503}  # both push services are down

    def push_service(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(answers[str(request.url)])

    async with httpx.AsyncClient(transport=httpx.MockTransport(push_service)) as http:
        sender = web_push.PushSender(http, PRIVATE, CONTACT)
        # No SMTP: readers with push are served, the other one waits for email.
        async with app.state.db.sessionmaker() as session:
            report = await deliver_pending(session, settings, None, push=sender)
        assert (report.sent, report.retried) == (0, 1)  # nobody got it: tried again later
        assert len(received) == 2

        # Later the phone's service is back: it counts as delivered, even with the laptop down.
        answers[phone.endpoint] = 201
        received.clear()
        later = datetime.now(UTC) + timedelta(hours=1)
        async with app.state.db.sessionmaker() as session:
            report = await deliver_pending(session, settings, None, push=sender, now=later)
        assert report.sent == 1
        to_phone = next(r for r in received if str(r.url) == phone.endpoint)
        message = phone.read(to_phone.content)
        assert "We received your request" in message["title"] + message["body"]
        assert message["url"] == f"{settings.app_base_url}/profile"
        assert to_phone.headers["content-encoding"] == "aes128gcm"
        assert to_phone.headers["ttl"] == str(web_push.TTL_SECONDS)

        # The VAPID header is a token signed with the library's key, for that push service.
        scheme, _, params = to_phone.headers["authorization"].partition(" ")
        fields = dict(part.split("=", 1) for part in params.split(","))
        assert scheme == "vapid"
        assert fields["k"] == PUBLIC
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), web_push.b64url_decode(PUBLIC)
        )
        claims = jwt.decode(
            fields["t"], public_key, algorithms=["ES256"], audience="https://fcm.googleapis.com"
        )
        assert claims["sub"] == CONTACT

        # The next news: the laptop is gone (410) and forgotten; the phone gets it once.
        order_id = (await customer.get(f"{API}/orders")).json()["items"][0]["id"]
        confirm = await admin.patch(
            f"{API}/admin/orders/{order_id}/status", json={"status": "confirmed"}
        )
        assert confirm.status_code == 200, confirm.text
        answers[laptop.endpoint] = 410
        received.clear()
        async with app.state.db.sessionmaker() as session:
            report = await deliver_pending(session, settings, None, push=sender, now=later)
        assert report.sent == 1
        assert sorted(str(r.url) for r in received) == sorted([phone.endpoint, laptop.endpoint])
        assert (
            "handed over"
            in phone.read(next(r for r in received if str(r.url) == phone.endpoint).content)["body"]
        )

    async with app.state.db.sessionmaker() as session:
        endpoints = (await session.scalars(select(PushSubscription.endpoint))).all()
        mine = (
            await session.scalars(
                select(Notification).where(Notification.user_id == uuid.UUID(customer.id))
            )
        ).all()
    assert endpoints == [phone.endpoint]
    assert all(n.status is NotificationStatus.SENT and n.push_sent_at for n in mine)


def test_generated_keys_sign_tokens() -> None:
    public, private = web_push.generate_keys()
    assert len(web_push.b64url_decode(public)) == 65
    assert len(web_push.b64url_decode(private)) == 32
    sender_headers = Vapid02.from_raw(private.encode()).sign(
        {"aud": "https://fcm.googleapis.com", "sub": CONTACT}
    )
    assert sender_headers["Authorization"].startswith("vapid t=")
