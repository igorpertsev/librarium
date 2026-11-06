from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import API


async def test_api_responses_carry_security_headers(client: AsyncClient) -> None:
    response = await client.get(f"{API}/books")
    assert response.status_code == 200
    assert (
        response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    )
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"


async def test_docs_page_keeps_working_without_the_api_policy(client: AsyncClient) -> None:
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers
