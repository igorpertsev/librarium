from __future__ import annotations

import binascii
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

from app.schemas.common import RequestModel
from app.services.web_push import allowed_endpoint, b64url_decode


def _push_endpoint(value: str) -> str:
    if not allowed_endpoint(value):
        raise ValueError("Not a browser push service address")
    return value


def _key(length: int, first: bytes = b"") -> AfterValidator:
    def check(value: str) -> str:
        try:
            raw = b64url_decode(value)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Not base64url") from exc
        if len(raw) != length or not raw.startswith(first):
            raise ValueError(f"Expected a {length}-byte key")
        return value

    return AfterValidator(check)


class PushKeys(RequestModel):
    # The browser's P-256 public key (uncompressed point) and its 16-byte auth secret.
    p256dh: Annotated[str, StringConstraints(max_length=200), _key(65, b"\x04")]
    auth: Annotated[str, StringConstraints(max_length=100), _key(16)]


class PushSubscriptionCreate(RequestModel):
    """``PushSubscription.toJSON()`` of the browser, without ``expirationTime``."""

    endpoint: Annotated[str, StringConstraints(max_length=2048), AfterValidator(_push_endpoint)]
    keys: PushKeys
