from __future__ import annotations

import uuid
from typing import Annotated, ClassVar

from pydantic import Field, StringConstraints

from app.schemas.book import BookRead
from app.schemas.common import ApiModel, PatchModel, RequestModel

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
OptionalTitle = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
Slug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9-]+$"
    ),
]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Position = Annotated[int, Field(ge=0, le=1000, description="Lower comes first")]


class CollectionSummary(ApiModel):
    id: uuid.UUID
    slug: str = Field(description="Its page: /collections/<slug>")
    title_en: str
    title_ru: str | None
    description_en: str
    description_ru: str | None
    featured: bool = Field(description="Shown as a shelf above the catalogue")
    position: int
    book_count: int


class CollectionRead(CollectionSummary):
    books: list[BookRead] = Field(description="Its titles in the librarians' order")


class CollectionCreate(RequestModel):
    title_en: Title
    title_ru: OptionalTitle | None = None
    description_en: Description = ""
    description_ru: Description | None = None
    slug: Slug | None = Field(default=None, description="Default: made from the English title")
    featured: bool = False
    position: Position = 0


class CollectionUpdate(PatchModel):
    non_nullable_fields: ClassVar[frozenset[str]] = frozenset(
        {"title_en", "description_en", "slug", "featured", "position"}
    )

    title_en: Title | None = None
    title_ru: OptionalTitle | None = None
    description_en: Description | None = None
    description_ru: Description | None = None
    slug: Slug | None = None
    featured: bool | None = None
    position: Position | None = None


class CollectionBooks(RequestModel):
    book_ids: list[uuid.UUID] = Field(
        max_length=100, description="Any copy of each title, in order (a title counts once)"
    )


class BookPick(ApiModel):
    book: BookRead
    note_en: str | None
    note_ru: str | None


class BookPickUpdate(RequestModel):
    book_id: uuid.UUID = Field(description="Any copy of the title")
    note_en: Note | None = None
    note_ru: Note | None = None
