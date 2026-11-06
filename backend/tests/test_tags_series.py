from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.services.openlibrary import OpenLibraryClient
from tests.conftest import API, ApiUser, make_settings

TAGS = [
    ("fantasy", "Fantasy", "Фэнтези"),
    ("adventure", "Adventure", "Приключения"),
    ("magic", "Magic", "Волшебство"),
    ("school", "School", "Школа"),
]


@pytest.fixture
async def tags(admin: ApiUser) -> None:
    for slug, en, ru in TAGS:
        response = await admin.post(
            f"{API}/admin/tags", json={"slug": slug, "name_en": en, "name_ru": ru}
        )
        assert response.status_code == 201, response.text


async def _book(admin: ApiUser, title: str, **extra: Any) -> dict[str, Any]:
    response = await admin.post(
        f"{API}/admin/books",
        json={"title": title, "author": "Ann Author", "category": "fiction", **extra},
    )
    assert response.status_code == 201, response.text
    book: dict[str, Any] = response.json()
    return book


async def _titles(client: AsyncClient, **params: Any) -> list[str]:
    response = await client.get(f"{API}/books", params={"sort": "title", **params})
    assert response.status_code == 200, response.text
    return [book["title"] for book in response.json()["items"]]


# --- Tags -------------------------------------------------------------------------------


async def test_librarians_keep_the_tag_list(
    client: AsyncClient, admin: ApiUser, customer: ApiUser
) -> None:
    created = await admin.post(
        f"{API}/admin/tags", json={"name_en": "Science Fiction", "name_ru": "Фантастика"}
    )
    assert created.status_code == 201
    tag = created.json()
    assert tag["slug"] == "science-fiction"  # made from the English name

    duplicate = await admin.post(
        f"{API}/admin/tags", json={"slug": "science-fiction", "name_en": "SF", "name_ru": "НФ"}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "TAG_EXISTS"

    renamed = await admin.patch(f"{API}/admin/tags/{tag['id']}", json={"name_ru": "НФ"})
    assert renamed.json()["name_ru"] == "НФ"

    listed = (await client.get(f"{API}/tags")).json()  # public
    assert [(t["slug"], t["book_count"]) for t in listed] == [("science-fiction", 0)]

    assert (
        await customer.post(f"{API}/admin/tags", json={"name_en": "X", "name_ru": "X"})
    ).status_code == 403
    assert (await admin.delete(f"{API}/admin/tags/{tag['id']}")).status_code == 204
    assert (await client.get(f"{API}/tags")).json() == []


async def test_books_are_found_by_their_tags(
    client: AsyncClient, admin: ApiUser, tags: None
) -> None:
    await _book(admin, "The Hobbit", tags=["fantasy", "adventure"])
    await _book(admin, "Harry Potter", tags=["fantasy", "magic", "school"])
    await _book(admin, "Treasure Island", tags=["adventure"])

    assert await _titles(client, tags="fantasy") == ["Harry Potter", "The Hobbit"]
    assert await _titles(client, tags="fantasy,adventure") == ["The Hobbit"]  # all of them
    assert await _titles(client, q="волшебство") == ["Harry Potter"]  # Russian tag name
    assert await _titles(client, q="adventure") == ["The Hobbit", "Treasure Island"]

    book = (await client.get(f"{API}/books", params={"q": "Treasure"})).json()["items"][0]
    assert book["tags"] == [{"slug": "adventure", "name_en": "Adventure", "name_ru": "Приключения"}]

    counts = {t["slug"]: t["book_count"] for t in (await client.get(f"{API}/tags")).json()}
    assert counts == {"adventure": 2, "fantasy": 2, "magic": 1, "school": 1}

    unknown = await admin.post(
        f"{API}/admin/books",
        json={"title": "X", "author": "Y", "category": "fiction", "tags": ["no-such-tag"]},
    )
    assert unknown.status_code == 400
    assert unknown.json()["error"]["details"] == {"tags": ["no-such-tag"]}

    bad = await client.get(f"{API}/books", params={"tags": "Not A Slug"})
    assert bad.status_code == 422


async def test_tags_belong_to_the_title_and_can_be_merged(
    client: AsyncClient, admin: ApiUser, tags: None
) -> None:
    book = await _book(admin, "Dune", tags=["adventure"])
    copy = (await admin.post(f"{API}/admin/books/{book['id']}/copies", json={"count": 1})).json()[0]
    assert [t["slug"] for t in copy["tags"]] == ["adventure"]  # copies inherit tags

    await admin.patch(f"{API}/admin/books/{copy['id']}", json={"tags": ["fantasy"]})
    first = (await admin.get(f"{API}/admin/books/{book['id']}")).json()
    assert [t["slug"] for t in first["tags"]] == ["fantasy"]  # every copy changes

    ids = {t["slug"]: t["id"] for t in (await client.get(f"{API}/tags")).json()}
    merged = await admin.post(
        f"{API}/admin/tags/{ids['fantasy']}/merge", json={"into_id": ids["magic"]}
    )
    assert merged.status_code == 204
    assert await _titles(client, tags="magic") == ["Dune"]
    assert "fantasy" not in {t["slug"] for t in (await client.get(f"{API}/tags")).json()}


# --- Series -----------------------------------------------------------------------------


async def test_series_are_created_by_name_and_listed_in_order(
    client: AsyncClient, admin: ApiUser
) -> None:
    third = await _book(admin, "Prisoner of Azkaban", series_name="Harry Potter", series_position=3)
    first = await _book(admin, "Philosopher's Stone", series_name="harry potter", series_position=1)
    await _book(admin, "Unnumbered Companion", series_name="Harry Potter")
    await _book(admin, "Something Else")
    assert first["series"]["id"] == third["series"]["id"]  # matched by name, any case
    assert first["series"]["name"] == "Harry Potter"
    series_id = first["series"]["id"]

    in_order = (
        await client.get(f"{API}/books", params={"series": series_id, "sort": "series"})
    ).json()["items"]
    assert [(b["title"], b["series_position"]) for b in in_order] == [
        ("Philosopher's Stone", 1.0),
        ("Prisoner of Azkaban", 3.0),
        ("Unnumbered Companion", None),
    ]
    assert await _titles(client, q="hary poter") == [  # misspelt series name
        "Philosopher's Stone",
        "Prisoner of Azkaban",
        "Unnumbered Companion",
    ]
    listed = (await client.get(f"{API}/series", params={"q": "potter"})).json()
    assert [(s["name"], s["book_count"]) for s in listed] == [("Harry Potter", 3)]
    assert (await client.get(f"{API}/series/{series_id}")).json()["book_count"] == 3


async def test_editing_merging_and_deleting_series(client: AsyncClient, admin: ApiUser) -> None:
    book = await _book(admin, "Volume One", series_name="Detective Ivanov", series_position=1)
    other = await _book(admin, "Volume Two", series_name="Ivanov Detective", series_position=2)
    assert book["series"]["id"] != other["series"]["id"]

    merged = await admin.post(
        f"{API}/admin/series/{other['series']['id']}/merge",
        json={"into_id": book["series"]["id"]},
    )
    assert merged.status_code == 204
    assert await _titles(client, series=book["series"]["id"]) == ["Volume One", "Volume Two"]

    renamed = await admin.patch(
        f"{API}/admin/series/{book['series']['id']}", json={"name": "Inspector Ivanov"}
    )
    assert renamed.json()["name"] == "Inspector Ivanov"

    moved = await admin.patch(f"{API}/admin/books/{book['id']}", json={"series_id": None})
    assert moved.json()["series"] is None
    assert moved.json()["series_position"] is None

    assert (await admin.delete(f"{API}/admin/series/{book['series']['id']}")).status_code == 204
    remaining = (await admin.get(f"{API}/admin/books/{other['id']}")).json()
    assert remaining["series"] is None  # the book stays, without a series

    missing = await admin.patch(
        f"{API}/admin/books/{other['id']}",
        json={"series_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert missing.status_code == 404
    both = await admin.patch(
        f"{API}/admin/books/{other['id']}",
        json={"series_id": book["id"], "series_name": "X"},
    )
    assert both.status_code == 422


async def test_csv_import_with_tags_and_series(
    client: AsyncClient, admin: ApiUser, tags: None
) -> None:
    csv_text = (
        "title,author,category,tags,series,volume\n"
        "Book One,Ann,fiction,Фэнтези|adventure,Saga,1\n"
        "Book Two,Ann,fiction,fantasy,Saga,2\n"
    )
    body = (await admin.post(f"{API}/admin/books/import", json={"csv": csv_text})).json()
    assert body["created"] == 2, body
    assert await _titles(client, tags="fantasy") == ["Book One", "Book Two"]
    series = (await client.get(f"{API}/series")).json()
    assert [(s["name"], s["book_count"]) for s in series] == [("Saga", 2)]

    bad = "title,author,category,tags\nX,Y,fiction,no such tag\n"
    body = (await admin.post(f"{API}/admin/books/import", json={"csv": bad})).json()
    assert body["created"] == 0
    assert "unknown tag(s) no such tag" in body["errors"][0]["message"]


# --- ISBN lookup: series and tag suggestions ---------------------------------------------

POTTER: dict[str, object] = {
    "/books/OL1M.json": {
        "title": "Garri Potter i uznik Azkabana",
        "works": [{"key": "/works/OL82548W"}],
        "subjects": ["Школа"],
    },
    "/works/OL82548W.json": {
        "authors": [{"author": {"key": "/authors/OL23919A"}}],
        "series": [{"series": {"key": "/series/OL326110L"}, "position": "3"}],
        "subjects": ["series:Harry_Potter", "Fantasy fiction", "Wizards", "Magic", "Ghosts"],
    },
    "/authors/OL23919A.json": {"name": "J. K. Rowling"},
    "/series/OL326110L.json": {"name": "Harry Potter"},
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


def _potter(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/isbn/9785389077881.json":
        return httpx.Response(302, headers={"Location": "/books/OL1M.json"})
    data = POTTER.get(request.url.path)
    return httpx.Response(200, json=data) if data else httpx.Response(404, json={})


async def test_isbn_lookup_finds_the_series_and_suggests_tags(
    admin: ApiUser, tags: None, openlibrary: Callable[[httpx.MockTransport], None]
) -> None:
    openlibrary(httpx.MockTransport(_potter))
    body = (await admin.get(f"{API}/admin/isbn/9785389077881")).json()
    assert body["series"] == {
        "id": None,  # not in the library yet
        "name": "Harry Potter",
        "openlibrary_key": "OL326110L",
        "position": 3.0,
    }
    # "magic" matches two subjects (Wizards, Magic), so it ranks first.
    assert [t["slug"] for t in body["suggested_tags"]] == ["magic", "fantasy", "school"]

    # Saving the book with the suggestion creates the series with its Open Library key...
    book = await _book(
        admin,
        "Гарри Поттер и узник Азкабана",
        series_name="Harry Potter",
        series_openlibrary_key="OL326110L",
        series_position=3,
    )
    # ...so the next lookup (any edition, any language) points to it.
    again = (await admin.get(f"{API}/admin/isbn/9785389077881")).json()
    assert again["series"]["id"] == book["series"]["id"]


# --- Demo data --------------------------------------------------------------------------


async def test_demo_books_come_with_tags_and_series(
    database_url: str, client: AsyncClient, admin: ApiUser
) -> None:
    from app.cli import _seed  # noqa: PLC0415 - the CLI module builds the app on import

    # Only this starter tag exists here: the demo books' other tags are skipped, not an error.
    created = await admin.post(
        f"{API}/admin/tags", json={"name_en": "Dystopia", "name_ru": "Антиутопия"}
    )
    assert created.status_code == 201, created.text
    settings = make_settings(database_url, seed_admin_email=None, seed_admin_password=None)
    await _seed(settings, demo_books=True, reset_admin_password=False)
    await _seed(settings, demo_books=True, reset_admin_password=False)  # idempotent

    listed = (await client.get(f"{API}/series", params={"q": "harry"})).json()
    assert [(s["name"], s["book_count"]) for s in listed] == [("Harry Potter", 3)]
    in_order = (
        await client.get(f"{API}/books", params={"series": listed[0]["id"], "sort": "series"})
    ).json()["items"]
    assert [b["series_position"] for b in in_order] == [1.0, 2.0, 3.0]
    assert await _titles(client, tags="dystopia") == ["1984", "Catching Fire", "The Hunger Games"]
    # Demo books come with Russian titles, which search finds.
    assert await _titles(client, q="пересмешника") == ["To Kill a Mockingbird"]
