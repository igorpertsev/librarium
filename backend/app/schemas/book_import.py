from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

from app.schemas.common import ApiModel, RequestModel


class BookImportRequest(RequestModel):
    csv: Annotated[str, StringConstraints(min_length=1, max_length=1_000_000)]


class BookImportError(ApiModel):
    row: int
    message: str


class BookImportResult(ApiModel):
    rows: int
    created: int
    errors: list[BookImportError]


class BookLookup(ApiModel):
    isbn: str
    title: str
    author: str | None
    description: str | None
    publication_year: int | None
    cover_url: str | None
    language: str | None
