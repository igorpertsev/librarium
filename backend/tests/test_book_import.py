from __future__ import annotations

from collections.abc import Callable, Iterator

import httpx
import pytest
from fastapi import FastAPI

from app.services.book_import import TEMPLATE
from app.services.openlibrary import OpenLibraryClient
from tests.conftest import API, ApiUser

CSV = """Title,Author,Category,Age,ISBN,Year,Status,Images
Dune,Frank Herbert,Fiction,14+,9780441172719,1965,available,https://img.example.com/a.jpg | https://img.example.com/b.jpg
Cosmos,Carl Sagan,science,12+,,1980,not available,
"""


async def _import(admin: ApiUser, text: str, *, dry_run: bool = False) -> httpx.Response:
    return await admin.post(
        f"{API}/admin/books/import", params={"dry_run": dry_run}, json={"csv": text}
    )


async def test_csv_import_creates_books(admin: ApiUser) -> None:
    preview = await _import(admin, CSV, dry_run=True)
    assert preview.json() == {"rows": 2, "created": 0, "errors": [], "warnings": []}
    assert (await admin.get(f"{API}/admin/books")).json()["total"] == 0

    response = await _import(admin, CSV)
    assert response.status_code == 200
    assert response.json() == {"rows": 2, "created": 2, "errors": [], "warnings": []}
    books = {b["title"]: b for b in (await admin.get(f"{API}/admin/books")).json()["items"]}
    assert books["Dune"]["category"] == "fiction"
    assert books["Dune"]["publication_year"] == 1965
    assert books["Dune"]["image_urls"] == [
        "https://img.example.com/a.jpg",
        "https://img.example.com/b.jpg",
    ]
    assert books["Cosmos"]["status"] == "not-available"


async def test_any_invalid_row_rejects_the_whole_file(admin: ApiUser) -> None:
    text = CSV + "No author,,fiction,,,,,\nBad,Someone,cookbooks,,,,,\n"
    body = (await _import(admin, text)).json()
    assert body["created"] == 0
    assert [e["row"] for e in body["errors"]] == [4, 5]
    assert "author" in body["errors"][0]["message"]
    assert (await admin.get(f"{API}/admin/books")).json()["total"] == 0


async def test_unusual_files_are_reported_not_crashed_on(admin: ApiUser) -> None:
    # Found by the API fuzzer: these used to answer 500.
    lone_cr = (await _import(admin, "title,author,category\rA,B,fiction\r", dry_run=True)).json()
    assert (lone_cr["rows"], lone_cr["errors"]) == (1, [])  # old Mac line ends are fine
    garbage = await _import(admin, "\U000ed877\r\x7f\xa9<", dry_run=True)
    assert garbage.status_code == 200
    assert garbage.json()["errors"][0]["message"].startswith("Missing column(s)")
    huge = "title,author,category\n" + "A" * 140_000 + ",B,fiction\n"  # over the csv field limit
    body = (await _import(admin, huge, dry_run=True)).json()
    assert body["created"] == 0
    assert body["errors"][0]["message"].startswith("Not a readable CSV file")


async def test_missing_columns_and_template(admin: ApiUser) -> None:
    body = (await _import(admin, "title,author\nA,B\n")).json()
    assert body["errors"] == [{"row": 1, "message": "Missing column(s): category"}]
    for slug, en, ru in [
        ("fantasy", "Fantasy", "Фэнтези"),
        ("adventure", "Adventure", "Приключения"),
    ]:
        await admin.post(f"{API}/admin/tags", json={"slug": slug, "name_en": en, "name_ru": ru})
    assert (await _import(admin, TEMPLATE)).json()["created"] == 1


async def test_customers_cannot_import(customer: ApiUser) -> None:
    assert (await _import(customer, CSV)).status_code == 403


ROUTES: dict[str, object] = {
    "/books/OL33891995M.json": {
        "title": "The Hobbit",
        "authors": [{"key": "/authors/OL26320A"}],
        "works": [{"key": "/works/OL262758W"}],
        "covers": [12645114],
        "publish_date": "September 18, 2012",
        "languages": [{"key": "/languages/eng"}],
    },
    "/authors/OL26320A.json": {"name": "J.R.R. Tolkien"},
    "/works/OL262758W.json": {"description": {"type": "/type/text", "value": "There and back."}},
}


@pytest.fixture
def openlibrary(app: FastAPI) -> Iterator[Callable[[httpx.MockTransport], None]]:
    original = app.state.openlibrary

    def use(transport: httpx.MockTransport) -> None:
        app.state.openlibrary = OpenLibraryClient(
            httpx.AsyncClient(transport=transport, follow_redirects=True),
            base_url="https://ol.test",
        )

    yield use
    app.state.openlibrary = original


def _fake_openlibrary(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/isbn/9780547928227.json":  # like the real service
        return httpx.Response(302, headers={"Location": "/books/OL33891995M.json"})
    data = ROUTES.get(request.url.path)
    return httpx.Response(200, json=data) if data else httpx.Response(404, json={})


async def test_isbn_lookup_fills_in_the_details(
    admin: ApiUser, openlibrary: Callable[[httpx.MockTransport], None]
) -> None:
    openlibrary(httpx.MockTransport(_fake_openlibrary))
    response = await admin.get(f"{API}/admin/isbn/978-0-547-92822-7")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "isbn": "9780547928227",
        "title": "The Hobbit",
        "author": "J.R.R. Tolkien",
        "description": "There and back.",
        "publication_year": 2012,
        "cover_url": "https://covers.openlibrary.org/b/id/12645114-L.jpg",
        "language": "en",
        "series": None,
        "suggested_tags": [],
    }
    missing = await admin.get(f"{API}/admin/isbn/9780000000002")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ISBN_NOT_FOUND"
    assert (await admin.get(f"{API}/admin/isbn/not-an-isbn")).status_code == 404


async def test_authors_can_come_from_the_work_record(
    admin: ApiUser, openlibrary: Callable[[httpx.MockTransport], None]
) -> None:
    routes = {
        "/isbn/9780141439518.json": {
            "title": "Pride and Prejudice",
            "works": [{"key": "/works/W1"}],
        },
        "/works/W1.json": {"authors": [{"author": {"key": "/authors/A1"}}]},
        "/authors/A1.json": {"name": "Jane Austen"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        data = routes.get(request.url.path)
        return httpx.Response(200, json=data) if data else httpx.Response(404, json={})

    openlibrary(httpx.MockTransport(handler))
    body = (await admin.get(f"{API}/admin/isbn/9780141439518")).json()
    assert body["author"] == "Jane Austen"
    assert body["description"] is None
    assert body["cover_url"] is None


async def test_isbn_lookup_survives_a_non_json_answer(
    admin: ApiUser, openlibrary: Callable[[httpx.MockTransport], None]
) -> None:
    openlibrary(httpx.MockTransport(lambda request: httpx.Response(200, text="<html>busy</html>")))
    response = await admin.get(f"{API}/admin/isbn/9780547928227")
    assert response.status_code == 502


async def test_isbn_lookup_reports_an_unreachable_service(
    admin: ApiUser, openlibrary: Callable[[httpx.MockTransport], None]
) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    openlibrary(httpx.MockTransport(broken))
    response = await admin.get(f"{API}/admin/isbn/9780547928227")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "LOOKUP_UNAVAILABLE"
