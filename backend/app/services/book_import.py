"""Bulk import of books from CSV (admin portal).

All or nothing: every row is validated first with the same rules as the "add book" form;
if any row is invalid nothing is created and the errors are reported per row.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.book import BookCreate
from app.services import catalog, duplicates
from app.services.books import new_book

MAX_ROWS = 500
REQUIRED_COLUMNS = ("title", "author", "category")
# Accepted header spellings -> BookCreate field.
_ALIASES = {
    "year": "publication_year",
    "published_year": "publication_year",
    "age": "age_range",
    "cover": "cover_url",
    "cover_image": "cover_url",
    "images": "image_urls",
    "series": "series_name",
    "volume": "series_position",
    "series_number": "series_position",
}
_FIELDS = set(BookCreate.model_fields)
TEMPLATE = (
    "title,author,category,age_range,isbn,publication_year,language,status,tags,series,"
    "series_position,cover_url,description\n"
    "The Hobbit,J.R.R. Tolkien,fiction,8+,9780547928227,1937,en,available,fantasy|adventure,,,,"
    '"A hobbit, a dragon and a long journey."\n'
)


@dataclass
class RowError:
    row: int  # line number in the file (the header is line 1)
    message: str


@dataclass
class RowWarning:
    row: int
    message: str
    existing_book_id: uuid.UUID | None = None  # a copy of the title already in the library


@dataclass
class ImportResult:
    rows: int = 0
    created: int = 0
    errors: list[RowError] = field(default_factory=list)
    # Rows that look like a book already in the library or earlier in the file.
    warnings: list[RowWarning] = field(default_factory=list)


def _column(name: str) -> str:
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    return _ALIASES.get(key, key)


class UnknownTagsError(ValueError):
    pass


def _tags(text: str, lookup: dict[str, str]) -> list[str]:
    """Tags by slug or by English/Russian name, separated by | ; or ,."""
    names = [name.strip() for name in re.split(r"[|;,]", text) if name.strip()]
    unknown = [name for name in names if name.lower() not in lookup]
    if unknown:
        raise UnknownTagsError(f"tags: unknown tag(s) {', '.join(unknown)}")
    return [lookup[name.lower()] for name in names]


def _row_values(raw: dict[str, str | None], tag_lookup: dict[str, str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for column, value in raw.items():
        text = (value or "").strip()
        if not column or column not in _FIELDS or not text:
            continue
        if column == "image_urls":
            values[column] = [url for url in text.replace("|", " ").split() if url]
        elif column == "tags":
            values[column] = _tags(text, tag_lookup)
        elif column in {"category", "status"}:
            values[column] = text.lower().replace(" ", "-").replace("_", "-")
        else:
            values[column] = text
    return values


def parse(
    text: str, tag_lookup: dict[str, str]
) -> tuple[list[tuple[int, BookCreate]], ImportResult]:
    result = ImportResult()
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if reader.fieldnames is None:
        result.errors.append(RowError(1, "The file is empty"))
        return [], result
    reader.fieldnames = [_column(name) for name in reader.fieldnames]
    missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        result.errors.append(RowError(1, f"Missing column(s): {', '.join(missing)}"))
        return [], result

    books: list[tuple[int, BookCreate]] = []  # (line, book)
    for raw in reader:
        line = reader.line_num
        if not any((value or "").strip() for value in raw.values() if isinstance(value, str)):
            continue  # blank line
        result.rows += 1
        if result.rows > MAX_ROWS:
            result.errors.append(RowError(line, f"At most {MAX_ROWS} books per import"))
            break
        try:
            books.append((line, BookCreate.model_validate(_row_values(raw, tag_lookup))))
        except UnknownTagsError as exc:
            result.errors.append(RowError(line, str(exc)))
        except ValidationError as exc:
            for error in exc.errors():
                where = ".".join(str(part) for part in error["loc"]) or "row"
                result.errors.append(RowError(line, f"{where}: {error['msg']}"))
    return books, result


async def _warn_about_duplicates(
    session: AsyncSession, books: list[tuple[int, BookCreate]], result: ImportResult
) -> None:
    by_isbn, by_name = await duplicates.existing_keys(
        session,
        [key for _, book in books if (key := duplicates.isbn_key(book.isbn))],
        [names for _, book in books if (names := duplicates.name_key(book.title, book.author))],
    )
    seen_isbn: dict[str, int] = {}
    seen_name: dict[tuple[str, str], int] = {}
    for line, book in books:
        key = duplicates.isbn_key(book.isbn)
        names = duplicates.name_key(book.title, book.author)
        existing = (by_isbn.get(key) if key else None) or (by_name.get(names) if names else None)
        if existing:
            result.warnings.append(
                RowWarning(
                    line,
                    f"“{existing[1]}” is already in the library; importing adds a separate "
                    "entry (use “Add a copy” for another copy of the same title)",
                    existing[0],
                )
            )
        earlier = (seen_isbn.get(key) if key else None) or (seen_name.get(names) if names else None)
        if earlier:
            result.warnings.append(RowWarning(line, f"Same book as line {earlier}"))
        if key:
            seen_isbn.setdefault(key, line)
        if names:
            seen_name.setdefault(names, line)


async def import_books(session: AsyncSession, text: str, *, dry_run: bool) -> ImportResult:
    books, result = parse(text, await catalog.tag_lookup(session))
    if not result.errors:
        await _warn_about_duplicates(session, books, result)
    if result.errors or dry_run:
        return result
    for _, book in books:  # one transaction: the series a file names are created once
        await new_book(session, book)
        await session.flush()
    await session.commit()
    result.created = len(books)
    return result
