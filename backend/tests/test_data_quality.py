from __future__ import annotations

from typing import Any

from tests.conftest import API, ApiUser


async def _book(admin: ApiUser, title: str, **extra: Any) -> str:
    response = await admin.post(
        f"{API}/admin/books",
        json={"title": title, "author": "Ann Author", "category": "fiction", **extra},
    )
    assert response.status_code == 201, response.text
    book_id: str = response.json()["id"]
    return book_id


async def test_the_quality_page_counts_and_lists_gaps(admin: ApiUser, customer: ApiUser) -> None:
    complete = await _book(
        admin,
        "Complete",
        description="All there.",
        cover_url="https://covers.example.com/c.jpg",
        isbn="9780000000002",
        translations=[{"language": "ru", "title": "Полная"}],
    )
    await admin.post(f"{API}/admin/books/{complete}/copies", json={"count": 2})
    await _book(
        admin,
        "Machine",
        description="Some text.",
        translations=[{"language": "ru", "title": "Машина", "title_source": "machine"}],
    )
    await _book(admin, "Bare")

    summary = (await admin.get(f"{API}/admin/books/quality")).json()
    assert summary["titles"] == 3  # copies count once
    assert summary["issues"] == {
        "no_cover": 2,
        "no_description": 1,
        "no_tags": 3,
        "no_isbn": 2,
        "no_translation": 1,
        "machine_translation": 1,
    }

    async def titles(issue: str) -> list[str]:
        body = (await admin.get(f"{API}/admin/books", params={"quality": issue})).json()
        return sorted(book["title"] for book in body["items"])

    assert await titles("no_cover") == ["Bare", "Machine"]
    assert await titles("machine_translation") == ["Machine"]
    assert await titles("no_tags") == ["Bare", "Complete", "Machine"]  # one entry per title
    assert (await customer.get(f"{API}/admin/books/quality")).status_code == 403
