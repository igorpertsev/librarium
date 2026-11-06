"""Tags and series: response and request bodies."""

from __future__ import annotations

import uuid
from typing import Annotated, ClassVar

from pydantic import Field, StringConstraints

from app.schemas.common import ApiModel, PatchModel, RequestModel

TagSlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, max_length=64, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$"
    ),
]
TagName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
SeriesName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
SeriesDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
SeriesPosition = Annotated[float, Field(gt=0, lt=10000)]


class TagBrief(ApiModel):
    slug: str
    name_en: str
    name_ru: str


class TagRead(TagBrief):
    id: uuid.UUID
    book_count: int = Field(0, description="Titles with this tag (copies counted once)")


class TagCreate(RequestModel):
    slug: TagSlug | None = Field(None, description="Generated from name_en when omitted")
    name_en: TagName
    name_ru: TagName


class TagUpdate(PatchModel):
    non_nullable_fields: ClassVar[frozenset[str]] = frozenset({"slug", "name_en", "name_ru"})

    slug: TagSlug | None = None
    name_en: TagName | None = None
    name_ru: TagName | None = None


class MergeInto(RequestModel):
    into_id: uuid.UUID = Field(description="Books move to this one; the merged one is deleted")


class SeriesBrief(ApiModel):
    id: uuid.UUID
    name: str


class SeriesRead(SeriesBrief):
    description: str
    openlibrary_key: str | None
    book_count: int = Field(0, description="Titles in the series (copies counted once)")


class SeriesCreate(RequestModel):
    name: SeriesName
    description: SeriesDescription = ""


class SeriesUpdate(PatchModel):
    non_nullable_fields: ClassVar[frozenset[str]] = frozenset({"name", "description"})

    name: SeriesName | None = None
    description: SeriesDescription | None = None
