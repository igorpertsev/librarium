from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import Field, StringConstraints

from app.schemas.catalog import TagBrief
from app.schemas.common import ApiModel, RequestModel


class BookImportRequest(RequestModel):
    csv: Annotated[str, StringConstraints(min_length=1, max_length=1_000_000)]


class BookImportError(ApiModel):
    row: int
    message: str


class BookImportWarning(ApiModel):
    row: int
    message: str
    existing_book_id: uuid.UUID | None = Field(
        description="A copy of the matching title already in the library"
    )


class BookImportResult(ApiModel):
    rows: int
    created: int
    errors: list[BookImportError]
    warnings: list[BookImportWarning] = Field(
        description="Rows that look like a book already in the library or earlier in the file; "
        "they are imported anyway"
    )


class LookupSeries(ApiModel):
    id: uuid.UUID | None = Field(description="The library's series, if it already has it")
    name: str
    openlibrary_key: str | None
    position: float | None


class BookLookup(ApiModel):
    isbn: str
    title: str
    author: str | None
    description: str | None
    publication_year: int | None
    cover_url: str | None
    language: str | None
    series: LookupSeries | None
    suggested_tags: list[TagBrief] = Field(
        description="Library tags matching the book's Open Library subjects"
    )
