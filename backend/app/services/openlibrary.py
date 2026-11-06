"""Book details by ISBN from Open Library (https://openlibrary.org/developers/api).

Used by the admin portal to fill in the "add book" form. Covers are referenced by cover id
(``covers.openlibrary.org/b/id/<id>-L.jpg``), which is not rate-limited, unlike ISBN-based
cover URLs.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.exceptions import AppError, NotFoundError

logger = logging.getLogger(__name__)

BASE_URL = "https://openlibrary.org"
_YEAR = re.compile(r"\b(1[5-9]\d{2}|20\d{2})\b")
# Open Library language keys -> ISO 639-1 codes used by the catalogue.
_LANGUAGES = {"eng": "en", "rus": "ru", "fre": "fr", "ger": "de", "spa": "es", "ita": "it"}


class LookupUnavailableError(AppError):
    status_code = 502
    code = "LOOKUP_UNAVAILABLE"
    message = "Open Library could not be reached; try again later"


@dataclass(frozen=True, slots=True)
class BookDetails:
    isbn: str
    title: str
    author: str | None
    description: str | None
    publication_year: int | None
    cover_url: str | None
    language: str | None
    series_name: str | None = None
    series_key: str | None = None  # Open Library series key, e.g. "OL326110L"
    series_position: float | None = None
    subjects: tuple[str, ...] = ()


_SERIES_KEY = re.compile(r"^/series/(OL\d+L)$")
_SERIES_TEXT = re.compile(
    r"^(?P<name>.*?)[\s,;:#(-]*(?:\b(?:bk|book|vol|volume|no|v|t|т|том|кн|книга)\b\.?\s*)?"
    r"(?P<number>\d+(?:\.\d+)?)\)?\s*$",
    re.IGNORECASE,
)


def _position(value: Any) -> float | None:
    try:
        number = float(str(value).strip())
    except ValueError:
        return None
    return number if 0 < number < 10000 else None


def parse_series_text(text: str) -> tuple[str, float | None]:
    """'Dune chronicles -- bk. 1' -> ('Dune chronicles', 1.0); no number -> (text, None)."""
    match = _SERIES_TEXT.match(text.strip())
    if match and match.group("name").strip(" ,;:#(-"):
        return match.group("name").strip(" ,;:#(-"), _position(match.group("number"))
    return text.strip(), None


def normalize_isbn(value: str) -> str | None:
    compact = re.sub(r"[\s-]", "", value).upper()
    return compact if re.fullmatch(r"\d{9}[\dX]|\d{13}", compact) else None


def _text(value: Any) -> str | None:
    """Open Library descriptions are either a string or {"type": ..., "value": ...}."""
    if isinstance(value, dict):
        value = value.get("value")
    return value.strip() if isinstance(value, str) and value.strip() else None


class OpenLibraryClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str = BASE_URL) -> None:
        self._http = http
        self._base_url = base_url

    async def _get_json(self, path: str, **params: str) -> Any:
        try:
            response = await self._http.get(f"{self._base_url}{path}", params=params or None)
        except httpx.HTTPError as exc:
            logger.warning("Open Library request failed: %s", exc)
            raise LookupUnavailableError from exc
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            logger.warning("Open Library answered %s for %s", response.status_code, path)
            raise LookupUnavailableError
        try:
            return response.json()
        except ValueError as exc:
            logger.warning("Open Library sent no JSON for %s (%s)", path, response.status_code)
            raise LookupUnavailableError from exc

    async def lookup(self, isbn: str) -> BookDetails:
        normalized = normalize_isbn(isbn)
        if normalized is None:
            raise NotFoundError("Not a valid ISBN-10 or ISBN-13", code="ISBN_NOT_FOUND")
        edition = await self._get_json(f"/isbn/{normalized}.json")
        if not isinstance(edition, dict) or not _text(edition.get("title")):
            raise NotFoundError("No book found for this ISBN", code="ISBN_NOT_FOUND")

        # The edition often lacks authors and description; the "work" record has them.
        work: dict[str, Any] = {}
        works = edition.get("works") or []
        if works and isinstance(works[0], dict) and isinstance(works[0].get("key"), str):
            record = await self._get_json(f"{works[0]['key']}.json")
            work = record if isinstance(record, dict) else {}
        author_keys = [
            ref.get("key") for ref in edition.get("authors") or [] if isinstance(ref, dict)
        ] or [
            ref.get("author", {}).get("key")
            for ref in work.get("authors") or []
            if isinstance(ref, dict) and isinstance(ref.get("author"), dict)
        ]
        authors: list[str] = []
        for key in author_keys[:3]:
            author = await self._get_json(f"{key}.json") if isinstance(key, str) else None
            name = _text(author.get("name")) if isinstance(author, dict) else None
            if name:
                authors.append(name)
        description = _text(edition.get("description")) or _text(work.get("description"))

        covers = [c for c in edition.get("covers", []) if isinstance(c, int) and c > 0]
        year_match = _YEAR.search(str(edition.get("publish_date", "")))
        languages = edition.get("languages") or []
        language_key = (
            languages[0].get("key", "") if languages and isinstance(languages[0], dict) else ""
        )
        series_name, series_key, series_position = await self._series(edition, work)
        subjects = [
            text
            for value in [*(work.get("subjects") or []), *(edition.get("subjects") or [])]
            if (text := _text(value))
        ]
        return BookDetails(
            series_name=series_name,
            series_key=series_key,
            series_position=series_position,
            subjects=tuple(dict.fromkeys(subjects))[:200],
            isbn=normalized,
            title=str(_text(edition.get("title"))),
            author=", ".join(authors) or None,
            description=description[:5000] if description else None,
            publication_year=int(year_match.group(1)) if year_match else None,
            cover_url=f"https://covers.openlibrary.org/b/id/{covers[0]}-L.jpg" if covers else None,
            language=_LANGUAGES.get(language_key.rsplit("/", 1)[-1]),
        )

    async def _series(
        self, edition: dict[str, Any], work: dict[str, Any]
    ) -> tuple[str | None, str | None, float | None]:
        """The story series: from the work record (key + position, the same for editions in
        every language), else from the edition's free-text series ("Dune chronicles, 1")."""
        for ref in work.get("series") or []:
            key_ref = ref.get("series", {}).get("key") if isinstance(ref, dict) else None
            match = _SERIES_KEY.match(key_ref) if isinstance(key_ref, str) else None
            if match is None:
                continue
            record = await self._get_json(f"/series/{match.group(1)}.json")
            name = _text(record.get("name")) if isinstance(record, dict) else None
            if name:
                return name[:300], match.group(1), _position(ref.get("position"))
        for text in edition.get("series") or []:
            if isinstance(text, str) and text.strip():
                name, position = parse_series_text(text)
                return name[:300], None, position
        return None, None, None
