"""The HTTP client for calls to other services (Open Library, Wikidata, Wikipedia)."""

from __future__ import annotations

import httpx

from app.core.config import Settings


def make_http_client(settings: Settings) -> httpx.AsyncClient:
    # Wikimedia and Open Library ask clients to say who they are and how to reach them.
    return httpx.AsyncClient(
        timeout=10,
        follow_redirects=True,  # e.g. Open Library: /isbn/<isbn>.json -> /books/<id>.json
        headers={"User-Agent": f"LittleDragonLibrary/1.0 (+{settings.app_base_url})"},
    )
