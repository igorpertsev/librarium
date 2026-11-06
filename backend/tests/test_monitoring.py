from __future__ import annotations

import httpx

from app.core.http import ping_monitor


async def test_the_monitor_is_pinged_and_failures_are_harmless() -> None:
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200 if request.url.path == "/ok" else 503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        assert await ping_monitor(http, "https://hc.test/ok") is True
        assert await ping_monitor(http, "https://hc.test/broken") is False
        assert await ping_monitor(http, None) is False  # not configured: nothing is sent
    assert seen == ["https://hc.test/ok", "https://hc.test/broken"]

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as http:
        assert await ping_monitor(http, "https://hc.test/ok") is False
