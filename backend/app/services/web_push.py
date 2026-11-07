"""Web Push notifications (optional: ``WEB_PUSH_*`` settings).

A reader turns notifications on in the installed app or browser: the browser subscribes with the
library's VAPID public key and sends us its push service endpoint and keys. Each notification is
then also sent there — encrypted for that browser (RFC 8291, aes128gcm) and signed with the
library's VAPID key (RFC 8292) — and shown by the service worker (public/sw.js). A subscription
the push service reports as gone (404/410) is deleted.

Only the browsers' own push services are accepted as endpoints, so a subscription cannot make the
server send requests anywhere else.
"""

from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

import http_ece
import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid02
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ConflictError
from app.models import PushSubscription, User

logger = logging.getLogger(__name__)

# Push services of Chrome/Edge/Android (FCM), Firefox, Safari and Windows.
PUSH_HOSTS = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "updates.push.services.mozilla.com",
    "push.services.mozilla.com",
    "web.push.apple.com",
    ".push.apple.com",
    ".notify.windows.com",
)
TTL_SECONDS = 24 * 3600
MAX_BODY = 300


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def allowed_endpoint(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        return False
    return any(
        host == h.lstrip(".") if not h.startswith(".") else host.endswith(h) for h in PUSH_HOSTS
    )


def generate_keys() -> tuple[str, str]:
    """A new VAPID key pair: (public key for browsers, private key), both base64url."""
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return b64url_encode(public), b64url_encode(private)


class PushError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class PushMessage:
    title: str
    body: str
    url: str

    def payload(self) -> bytes:
        body = " ".join(self.body.split())
        if len(body) > MAX_BODY:
            body = body[: MAX_BODY - 1].rstrip() + "…"
        return json.dumps({"title": self.title[:120], "body": body, "url": self.url}).encode()


class PushSender:
    def __init__(self, http: httpx.AsyncClient, private_key: str, contact: str) -> None:
        self._http = http
        self._vapid = Vapid02.from_raw(private_key.encode())
        self._contact = contact

    async def send(self, subscription: PushSubscription, message: PushMessage) -> bool:
        """Deliver one message; False when the push service says the subscription is gone."""
        try:
            body = http_ece.encrypt(
                message.payload(),
                private_key=ec.generate_private_key(ec.SECP256R1()),  # fresh for every message
                dh=b64url_decode(subscription.p256dh),
                auth_secret=b64url_decode(subscription.auth),
                version="aes128gcm",
            )
        except ValueError as exc:  # keys that do not decode or are not on the curve
            raise PushError(f"bad subscription keys: {exc}") from exc
        parts = urlsplit(subscription.endpoint)
        headers: dict[str, str] = self._vapid.sign(
            {
                "aud": f"{parts.scheme}://{parts.netloc}",
                "exp": int(time.time()) + 12 * 3600,
                "sub": self._contact,
            }
        )
        headers |= {
            "TTL": str(TTL_SECONDS),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "Urgency": "normal",
        }
        try:
            response = await self._http.post(
                subscription.endpoint, content=body, headers=headers, timeout=15
            )
        except httpx.HTTPError as exc:
            raise PushError(type(exc).__name__) from exc
        if response.status_code in (404, 410):
            return False
        if response.status_code >= 400:
            raise PushError(f"{response.status_code} {response.text[:200]}")
        return True


def make_push_sender(settings: Settings, http: httpx.AsyncClient) -> PushSender | None:
    if not (settings.web_push_private_key and settings.web_push_contact):
        return None
    return PushSender(
        http, settings.web_push_private_key.get_secret_value(), settings.web_push_contact
    )


# --- Subscriptions ---------------------------------------------------------------------------


async def subscribe(
    session: AsyncSession,
    settings: Settings,
    user: User,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None,
) -> None:
    """Remember this browser for the reader (a browser re-subscribing moves to them)."""
    if not settings.web_push_enabled:
        raise ConflictError("Push notifications are not set up", code="PUSH_NOT_CONFIGURED")
    existing = await session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    )
    if existing is None:
        session.add(
            PushSubscription(
                id=uuid.uuid4(),
                user_id=user.id,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                user_agent=(user_agent or "")[:300] or None,
            )
        )
    else:
        existing.user_id = user.id
        existing.p256dh = p256dh
        existing.auth = auth
        existing.user_agent = (user_agent or "")[:300] or None
    await session.commit()


async def unsubscribe(session: AsyncSession, user: User, endpoint: str) -> None:
    await session.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user.id, PushSubscription.endpoint == endpoint
        )
    )
    await session.commit()


async def has_subscriptions(session: AsyncSession, user_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(PushSubscription.id).where(PushSubscription.user_id == user_id).limit(1)
    )
    return found is not None


async def send_to_user(
    session: AsyncSession,
    sender: PushSender,
    user_id: uuid.UUID,
    message: PushMessage,
    now: datetime,
) -> str | None:
    """Send to every browser of the reader (in the caller's transaction). Once one of them has
    it, it counts as delivered (a retry would repeat it there); an error message only when none
    could be reached right now."""
    errors: list[str] = []
    delivered_any = False
    subscriptions = await session.scalars(
        select(PushSubscription).where(PushSubscription.user_id == user_id)
    )
    for subscription in subscriptions.all():
        try:
            delivered = await sender.send(subscription, message)
        except PushError as exc:
            errors.append(str(exc))
            logger.warning("Web Push failed: %s", exc)
            continue
        if delivered:
            subscription.last_sent_at = now
            delivered_any = True
        else:
            await session.delete(subscription)  # the browser unsubscribed or was reset
    return f"Push: {'; '.join(errors)}" if errors and not delivered_any else None
