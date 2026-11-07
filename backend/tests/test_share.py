from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import API, ApiUser


async def test_link_previews_get_open_graph_tags(client: AsyncClient, admin: ApiUser) -> None:
    created = await admin.post(
        f"{API}/admin/books",
        json={
            "title": 'Dune <script>alert("x")</script>',
            "author": "Frank Herbert",
            "category": "fiction",
            "description": "Spice " * 100,
            "cover_url": "https://covers.example.com/dune.jpg",
        },
    )
    book_id = created.json()["id"]

    page = await client.get(f"{API}/share/books/{book_id}")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    html = page.text
    assert "<script>" not in html  # escaped
    assert (
        'content="Dune &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; — Frank Herbert"' in html
    )
    assert '<meta property="og:image" content="https://covers.example.com/dune.jpg">' in html
    assert f"url=http://localhost:5173/books/{book_id}" in html
    description = html.split('property="og:description" content="')[1].split('"')[0]
    assert len(description) <= 300
    assert description.endswith("…")

    missing = await client.get(f"{API}/share/books/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
