"""ETags for the public catalogue: browsers revalidate and get "304 Not Modified" instead of
downloading the same JSON again.

Only successful GET responses under the given path prefixes are tagged. They carry
``Cache-Control: no-cache``, so a browser always asks, but it only gets the body back when
something changed.
"""

from __future__ import annotations

import hashlib

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class ETagMiddleware:
    def __init__(self, app: ASGIApp, prefixes: tuple[str, ...]) -> None:
        self.app = app
        self.prefixes = prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "GET"
            or not str(scope["path"]).startswith(self.prefixes)
        ):
            await self.app(scope, receive, send)
            return

        start: Message | None = None
        body = bytearray()

        async def capture(message: Message) -> None:
            nonlocal start
            if message["type"] == "http.response.start":
                start = message
                return
            if message["type"] != "http.response.body":
                await send(message)
                return
            body.extend(message.get("body", b""))
            if message.get("more_body"):
                return
            assert start is not None  # noqa: S101 - ASGI sends the start first
            await self._finish(scope, send, start, bytes(body))

        await self.app(scope, receive, capture)

    @staticmethod
    async def _finish(scope: Scope, send: Send, start: Message, body: bytes) -> None:
        headers = MutableHeaders(raw=list(start["headers"]))
        if start["status"] != 200:
            await send({**start, "headers": headers.raw})
            await send({"type": "http.response.body", "body": body})
            return
        etag = f'W/"{hashlib.sha256(body).hexdigest()[:32]}"'
        headers["ETag"] = etag
        headers["Cache-Control"] = "no-cache"
        wanted = Headers(scope=scope).get("if-none-match", "")
        if etag in (tag.strip() for tag in wanted.split(",")):
            del headers["content-length"]
            await send({**start, "status": 304, "headers": headers.raw})
            await send({"type": "http.response.body", "body": b""})
            return
        await send({**start, "headers": headers.raw})
        await send({"type": "http.response.body", "body": body})
