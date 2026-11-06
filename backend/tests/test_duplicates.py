from __future__ import annotations

from tests.conftest import API, ApiUser


async def _book(admin: ApiUser, title: str, author: str, isbn: str | None = None) -> str:
    payload = {"title": title, "author": author, "category": "fiction", "isbn": isbn}
    response = await admin.post(f"{API}/admin/books", json=payload)
    assert response.status_code == 201, response.text
    book_id: str = response.json()["id"]
    return book_id


async def test_similar_books_are_found_before_adding(admin: ApiUser, customer: ApiUser) -> None:
    dune = await _book(admin, "Dune", "Frank Herbert", "978-0-441-17271-9")
    await admin.post(f"{API}/admin/books/{dune}/copies", json={"count": 1})
    await _book(admin, "Emma", "Jane Austen")

    async def matches(**params: str) -> list[str]:
        response = await admin.get(f"{API}/admin/books/duplicates", params=params)
        assert response.status_code == 200, response.text
        return [f"{b['title']} x{b['copies']}" for b in response.json()]

    assert await matches(isbn="9780441172719") == ["Dune x2"]  # hyphens ignored, one per title
    assert await matches(title=" dune ", author="FRANK HERBERT") == ["Dune x2"]
    assert await matches(title="Dune", author="Someone Else") == []
    assert await matches(title="Dune") == []  # a title alone is not enough
    forbidden = await customer.get(f"{API}/admin/books/duplicates", params={"title": "x"})
    assert forbidden.status_code == 403


async def test_import_warns_about_duplicates_but_imports_them(admin: ApiUser) -> None:
    await _book(admin, "Dune", "Frank Herbert", "9780441172719")
    csv = (
        "title,author,category,isbn\n"
        "Dune,Frank Herbert,fiction,978-0441172719\n"
        "Emma,Jane Austen,fiction,\n"
        "emma,jane austen,fiction,\n"
    )
    preview = await admin.post(
        f"{API}/admin/books/import", params={"dry_run": True}, json={"csv": csv}
    )
    body = preview.json()
    assert body["errors"] == []
    assert [(w["row"], w["existing_book_id"] is not None) for w in body["warnings"]] == [
        (2, True),
        (4, False),
    ]
    assert body["warnings"][1]["message"] == "Same book as line 3"
    done = await admin.post(f"{API}/admin/books/import", json={"csv": csv})
    assert done.json()["created"] == 3
