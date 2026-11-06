"""The HTTP client for calls to other services (Open Library, Wikidata, Wikipedia), and pings
to an uptime monitor."""

from __future__ import annotations

import logging

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


def make_http_client(settings: Settings) -> httpx.AsyncClient:
    # Wikimedia and Open Library ask clients to say who they are and how to reach them.
    return httpx.AsyncClient(
        timeout=10,
        follow_redirects=True,  # e.g. Open Library: /isbn/<isbn>.json -> /books/<id>.json
        headers={"User-Agent": f"LittleDragonLibrary/1.0 (+{settings.app_base_url})"},
    )


async def ping_monitor(http: httpx.AsyncClient, url: str | None) -> bool:
    """Tell a "dead man's switch" monitor (e.g. healthchecks.io) that a job is alive. A monitor
    that cannot be reached never stops the job; returns whether the ping went through."""
    if not url:
        return False
    try:
        response = await http.get(url, timeout=10)
    except httpx.HTTPError as exc:
        logger.warning("Could not reach the uptime monitor: %s", exc)
        return False
    if response.status_code >= 400:
        logger.warning("The uptime monitor answered %s", response.status_code)
        return False
    return True
