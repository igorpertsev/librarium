from __future__ import annotations

import json
import urllib.parse
from collections.abc import Iterator
from typing import Any

import anthropic
import httpx
import httpx2
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.models.enums import UiLanguage
from app.services.openlibrary import OpenLibraryClient
from app.services.translation_lookup import (
    ClaudeTranslator,
    TranslationLookup,
    WikimediaClient,
)
from app.services.translations import translate_catalogue
from tests.conftest import API, ApiUser

HOBBIT_RU = {
    "language": "ru",
    "title": "Хоббит, или Туда и обратно",
    "author": "Дж. Р. Р. Толкин",
    "description": "Бильбо Бэггинс отправляется в путешествие с гномами.",
}


async def _book(admin: ApiUser, title: str, **extra: Any) -> dict[str, Any]:
    response = await admin.post(
        f"{API}/admin/books",
        json={"title": title, "author": "Ann Author", "category": "fiction", **extra},
    )
    assert response.status_code == 201, response.text
    book: dict[str, Any] = response.json()
    return book


async def _titles(client: AsyncClient, q: str) -> list[str]:
    response = await client.get(f"{API}/books", params={"q": q, "sort": "title"})
    assert response.status_code == 200, response.text
    return [book["title"] for book in response.json()["items"]]


# --- Saving and showing -----------------------------------------------------------------


async def test_translations_are_saved_with_the_title_and_all_its_copies(
    admin: ApiUser, client: AsyncClient
) -> None:
    book = await _book(
        admin,
        "The Hobbit",
        author="J.R.R. Tolkien",
        language="en",
        translations=[{**HOBBIT_RU, "title_source": "wikidata"}],
    )
    assert book["translations"] == [
        {
            **HOBBIT_RU,
            "title_source": "wikidata",
            "description_source": "manual",
            "source_url": None,
        }
    ]
    public = (await client.get(f"{API}/books/{book['id']}")).json()
    assert public["translations"][0]["title"] == HOBBIT_RU["title"]

    copies = (await admin.post(f"{API}/admin/books/{book['id']}/copies", json={"count": 1})).json()
    assert copies[0]["translations"][0]["title"] == HOBBIT_RU["title"]

    # Editing one copy changes every copy; an empty list removes the translations.
    edited = await admin.patch(
        f"{API}/admin/books/{copies[0]['id']}",
        json={"translations": [{**HOBBIT_RU, "title": "Хоббит"}]},
    )
    assert edited.status_code == 200, edited.text
    original = (await admin.get(f"{API}/admin/books/{book['id']}")).json()
    assert [t["title"] for t in original["translations"]] == ["Хоббит"]
    cleared = await admin.patch(f"{API}/admin/books/{book['id']}", json={"translations": []})
    assert cleared.json()["translations"] == []
    copy = (await admin.get(f"{API}/admin/books/{copies[0]['id']}")).json()
    assert copy["translations"] == []


@pytest.mark.parametrize(
    "translations",
    [
        [HOBBIT_RU, {**HOBBIT_RU, "title": "Хоббит"}],  # two for one language
        [{**HOBBIT_RU, "language": "fr"}],  # not an interface language
        [{**HOBBIT_RU, "title": " "}],  # no title
        [{**HOBBIT_RU, "source_url": "javascript:alert(1)"}],
    ],
)
async def test_invalid_translations_are_rejected(
    admin: ApiUser, translations: list[dict[str, Any]]
) -> None:
    response = await admin.post(
        f"{API}/admin/books",
        json={
            "title": "The Hobbit",
            "author": "J.R.R. Tolkien",
            "category": "fiction",
            "translations": translations,
        },
    )
    assert response.status_code == 422, response.text


async def test_books_are_found_by_their_translated_text(
    admin: ApiUser, client: AsyncClient
) -> None:
    await _book(
        admin,
        "The Catcher in the Rye",
        author="J. D. Salinger",
        translations=[
            {
                "language": "ru",
                "title": "Над пропастью во ржи",
                "author": "Джером Сэлинджер",
                "description": "Холден Колфилд бродит по Нью-Йорку.",
            }
        ],
    )
    await _book(admin, "Something Else")
    assert await _titles(client, "над пропастью") == ["The Catcher in the Rye"]
    assert await _titles(client, "Сэлинджер") == ["The Catcher in the Rye"]
    assert await _titles(client, "Колфилд") == ["The Catcher in the Rye"]  # description
    assert await _titles(client, "над проастью во рж") == ["The Catcher in the Rye"]  # typos


# --- Suggestions from Wikidata, Wikipedia and machine translation -------------------------

WORK = "OL3335245W"
QID = "Q183883"
AUTHOR_QID = "Q79904"
ARTICLE = "Над пропастью во ржи"
ARTICLE_URL = "https://ru.wikipedia.org/wiki/%D0%9D%D0%B0%D0%B4"


def _references(*, ru_article: bool = True) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:  # noqa: PLR0911 - one fake per URL
        url, params = request.url, dict(request.url.params)
        if url.host == "ol.test":
            if url.path == "/isbn/9780316769174.json":
                return httpx.Response(302, headers={"Location": "/books/OL1M.json"})
            if url.path == "/books/OL1M.json":
                return httpx.Response(200, json={"works": [{"key": f"/works/{WORK}"}]})
        if url.host == "wd.test" and params.get("action") == "query":
            assert params["srsearch"] == f"haswbstatement:P648={WORK}"
            return httpx.Response(200, json={"query": {"search": [{"title": QID}]}})
        if url.host == "wd.test" and params.get("ids") == QID:
            entity: dict[str, Any] = {
                "labels": {"ru": {"value": "Над пропастью во ржи"}},
                "claims": {"P50": [{"mainsnak": {"datavalue": {"value": {"id": AUTHOR_QID}}}}]},
                "sitelinks": {"ruwiki": {"title": ARTICLE}} if ru_article else {},
            }
            return httpx.Response(200, json={"entities": {QID: entity}})
        if url.host == "wd.test" and params.get("ids") == AUTHOR_QID:
            labels = {"labels": {"ru": {"value": "Джером Дэвид Сэлинджер"}}}
            return httpx.Response(200, json={"entities": {AUTHOR_QID: labels}})
        expected = "/api/rest_v1/page/summary/" + urllib.parse.quote(ARTICLE.replace(" ", "_"))
        if url.host == "ru.wp.test" and url.raw_path.decode() == expected:
            return httpx.Response(
                200,
                json={
                    "type": "standard",
                    "extract": "«Над пропастью во ржи» — роман Джерома Сэлинджера.",
                    "content_urls": {"desktop": {"page": ARTICLE_URL}},
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handle)


class FakeTranslator:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], str | None, UiLanguage]] = []

    async def translate(
        self, fields: dict[str, str], *, source: str | None, target: UiLanguage
    ) -> dict[str, str] | None:
        self.calls.append((dict(fields), source, target))
        return {key: f"[{target.value}] {value}" for key, value in fields.items()}


def _lookup(transport: httpx.MockTransport, machine: FakeTranslator | None) -> TranslationLookup:
    http = httpx.AsyncClient(transport=transport, follow_redirects=True)
    return TranslationLookup(
        OpenLibraryClient(http, base_url="https://ol.test"),
        WikimediaClient(
            http,
            wikidata_url="https://wd.test/w/api.php",
            wikipedia_url="https://{language}.wp.test",
        ),
        machine,
    )


@pytest.fixture
def use_lookup(app: FastAPI) -> Iterator[Any]:
    original = app.state.translation_lookup

    def use(lookup: TranslationLookup) -> None:
        app.state.translation_lookup = lookup

    yield use
    app.state.translation_lookup = original


CATCHER = {
    "target": "ru",
    "title": "The Catcher in the Rye",
    "author": "J. D. Salinger",
    "description": "Holden Caulfield wanders New York.",
    "isbn": "9780316769174",
    "language": "en",
}


async def test_the_official_title_and_a_wikipedia_summary_come_first(
    admin: ApiUser, customer: ApiUser, use_lookup: Any
) -> None:
    machine = FakeTranslator()
    use_lookup(_lookup(_references(), machine))
    response = await admin.post(f"{API}/admin/translations/suggest", json=CATCHER)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "language": "ru",
        "title": "Над пропастью во ржи",
        "author": "Джером Дэвид Сэлинджер",
        "description": "«Над пропастью во ржи» — роман Джерома Сэлинджера.",
        "title_source": "wikidata",
        "description_source": "wikipedia",
        "source_url": ARTICLE_URL,
        "wikidata_id": QID,
        "machine_available": True,
    }
    assert machine.calls == []  # nothing left to translate
    forbidden = await customer.post(f"{API}/admin/translations/suggest", json=CATCHER)
    assert forbidden.status_code == 403


async def test_machine_translation_fills_in_what_the_references_lack(
    admin: ApiUser, use_lookup: Any
) -> None:
    machine = FakeTranslator()
    use_lookup(_lookup(_references(ru_article=False), machine))
    body = (await admin.post(f"{API}/admin/translations/suggest", json=CATCHER)).json()
    assert (body["title"], body["title_source"]) == ("Над пропастью во ржи", "wikidata")
    assert (body["description"], body["description_source"]) == (
        "[ru] Holden Caulfield wanders New York.",
        "machine",
    )
    assert body["source_url"] is None
    assert machine.calls == [
        ({"description": "Holden Caulfield wanders New York."}, "en", UiLanguage.RU)
    ]

    # Without an ISBN only machine translation can help; it can also be switched off.
    no_isbn = {**CATCHER, "isbn": None}
    body = (await admin.post(f"{API}/admin/translations/suggest", json=no_isbn)).json()
    assert body["title"] == "[ru] The Catcher in the Rye"
    assert body["title_source"] == "machine"
    assert body["wikidata_id"] is None
    off = (
        await admin.post(f"{API}/admin/translations/suggest", json={**no_isbn, "machine": False})
    ).json()
    assert (off["title"], off["description"], off["machine_available"]) == (None, None, True)


async def test_without_machine_translation_only_references_are_used(
    admin: ApiUser, use_lookup: Any
) -> None:
    use_lookup(_lookup(_references(), None))
    body = (
        await admin.post(f"{API}/admin/translations/suggest", json={**CATCHER, "isbn": None})
    ).json()
    assert body["title"] is None
    assert body["machine_available"] is False


async def test_unreachable_references_are_not_an_error(admin: ApiUser, use_lookup: Any) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    machine = FakeTranslator()
    use_lookup(_lookup(httpx.MockTransport(down), machine))
    body = (await admin.post(f"{API}/admin/translations/suggest", json=CATCHER)).json()
    assert body["title"] == "[ru] The Catcher in the Rye"  # machine translation still works


# --- The Claude request -------------------------------------------------------------------


def _claude(reply: dict[str, Any], requests: list[httpx2.Request]) -> anthropic.AsyncAnthropic:
    def handle(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json=reply)

    return anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handle)),
    )


def _message(text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": text}] if text else [],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 50, "output_tokens": 20},
    }


async def test_claude_translator_asks_for_structured_output_with_a_fallback() -> None:
    requests: list[httpx2.Request] = []
    answer = {"title": "Над пропастью во ржи", "author": "", "description": "Роман."}
    translator = ClaudeTranslator(
        _claude(_message(json.dumps(answer, ensure_ascii=False)), requests), "claude-opus-5-5"
    )
    result = await translator.translate(
        {"title": "The Catcher in the Rye", "description": "A novel."},
        source="en",
        target=UiLanguage.RU,
    )
    assert result == {"title": "Над пропастью во ржи", "description": "Роман."}

    (request,) = requests
    body = json.loads(request.content)
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in request.headers["anthropic-beta"]
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "The Catcher in the Rye" in body["messages"][0]["content"]
    assert "into Russian" in body["messages"][0]["content"]


async def test_a_declined_translation_returns_nothing() -> None:
    translator = ClaudeTranslator(_claude(_message("", "refusal"), []), "claude-opus-5-5")
    assert await translator.translate({"title": "Dune"}, source="en", target=UiLanguage.RU) is None


# --- Translating the catalogue ------------------------------------------------------------


async def test_translate_books_fills_in_missing_translations_once(
    app: FastAPI, admin: ApiUser
) -> None:
    catcher = await _book(admin, "The Catcher in the Rye", isbn="9780316769174", language="en")
    await _book(admin, "Мастер и Маргарита", author="Михаил Булгаков")  # already Russian
    machine = FakeTranslator()
    lookup = _lookup(_references(), machine)
    lines: list[str] = []
    async with app.state.db.sessionmaker() as session:
        done = await translate_catalogue(
            session,
            lookup,
            target=UiLanguage.RU,
            machine=True,
            limit=10,
            pause_seconds=0,
            report=lines.append,
        )
    assert done == 1
    assert lines == ["+ The Catcher in the Rye -> Над пропастью во ржи (wikidata, wikipedia)"]
    saved = (await admin.get(f"{API}/admin/books/{catcher['id']}")).json()["translations"]
    assert [(t["language"], t["title"], t["source_url"]) for t in saved] == [
        ("ru", "Над пропастью во ржи", ARTICLE_URL)
    ]
    async with app.state.db.sessionmaker() as session:
        again = await translate_catalogue(
            session,
            lookup,
            target=UiLanguage.RU,
            machine=True,
            limit=10,
            pause_seconds=0,
            report=lines.append,
        )
    assert again == 0
