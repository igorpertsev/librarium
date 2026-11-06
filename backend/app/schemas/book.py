from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Any, ClassVar

from pydantic import Field, field_validator

from app.models.book import Book
from app.models.enums import BookCategory, BookStatus
from app.schemas.common import ApiModel, Page, PatchModel, RequestModel
from app.schemas.types import (
    AgeRange,
    AuthorName,
    Description,
    HttpUrlStr,
    Isbn,
    LanguageCode,
    OptionalHttpUrlStr,
    Title,
)

ImageUrls = Annotated[list[HttpUrlStr], Field(max_length=20)]
PublicationYear = Annotated[int, Field(ge=0, le=9999)]


def _check_year(value: int | None) -> int | None:
    if value is not None and value > datetime.now(UTC).year + 1:
        raise ValueError("publication_year cannot be in the future")
    return value


class BookSort(StrEnum):
    """Allow-list of sort keys; ``-`` prefix means descending. Never interpolated into SQL."""

    TITLE = "title"
    TITLE_DESC = "-title"
    AUTHOR = "author"
    AUTHOR_DESC = "-author"
    PUBLICATION_YEAR = "publication_year"
    PUBLICATION_YEAR_DESC = "-publication_year"
    CREATED_AT = "created_at"
    CREATED_AT_DESC = "-created_at"
    # Best match for the search text first (falls back to title without a search).
    RELEVANCE = "relevance"


class BookBrief(ApiModel):
    """Current catalogue data of a book (no availability computation)."""

    id: uuid.UUID
    title: str
    author: str
    description: str
    category: BookCategory
    age_range: str
    status: BookStatus
    cover_url: str | None
    image_urls: list[str]
    isbn: str | None
    language: str | None
    publication_year: int | None
    is_active: bool


class BookRead(BookBrief):
    is_reserved: bool = Field(description="True while the copy belongs to an active order")
    is_available: bool = Field(
        description="True when the copy can be added to a cart: active, status 'available' "
        "and not reserved"
    )
    available_from: date | None = Field(
        description="While reserved: the due date of the order holding the copy, i.e. when it "
        "is expected back. null when the copy is not reserved."
    )
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_book(cls, book: Book, *, reserved_until: date | None) -> BookRead:
        """``reserved_until``: due date of the active order holding the copy, if any."""
        computed = {"is_reserved", "is_available", "available_from"}
        data: dict[str, Any] = {
            name: getattr(book, name) for name in cls.model_fields if name not in computed
        }
        is_reserved = reserved_until is not None
        return cls(
            **data,
            is_reserved=is_reserved,
            is_available=book.is_active and book.status is BookStatus.AVAILABLE and not is_reserved,
            available_from=reserved_until,
        )


class BookPage(Page[BookRead]):
    pass


class BookCreate(RequestModel):
    title: Title
    author: AuthorName
    description: Description = ""
    category: BookCategory
    age_range: AgeRange = ""
    status: BookStatus = BookStatus.AVAILABLE
    cover_url: OptionalHttpUrlStr = None
    image_urls: ImageUrls = Field(default_factory=list)
    isbn: Isbn = None
    language: LanguageCode = None
    publication_year: PublicationYear | None = None

    _year = field_validator("publication_year")(_check_year)


class BookUpdate(PatchModel):
    non_nullable_fields: ClassVar[frozenset[str]] = frozenset(
        {"title", "author", "description", "category", "age_range", "status", "image_urls"}
    )

    title: Title | None = None
    author: AuthorName | None = None
    description: Description | None = None
    category: BookCategory | None = None
    age_range: AgeRange | None = None
    status: BookStatus | None = None
    cover_url: OptionalHttpUrlStr = None
    image_urls: ImageUrls | None = None
    isbn: Isbn = None
    language: LanguageCode = None
    publication_year: PublicationYear | None = None

    _year = field_validator("publication_year")(_check_year)


class BookStats(ApiModel):
    total: int
    available: int
    available_soon: int
    not_available: int
    reserved: int
