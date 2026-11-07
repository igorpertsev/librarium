"""Tags and series: response and request bodies."""

from __future__ import annotations

import uuid
from typing import Annotated, ClassVar

from pydantic import AfterValidator, Field, StringConstraints

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


def _two_decimals(value: float) -> float:
    return round(value, 2)


# Stored as NUMERIC(6, 2): what fits, rounded to hundredths (a tiny or huge number would otherwise
# round to 0 or overflow in the database).
SeriesPosition = Annotated[float, Field(ge=0.01, le=9999.99), AfterValidator(_two_decimals)]


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
    name_en: str | None = Field(None, description="English name, if it differs from name")
    name_ru: str | None = Field(None, description="Russian name, if it differs from name")


class SeriesRead(SeriesBrief):
    description: str
    openlibrary_key: str | None
    book_count: int = Field(0, description="Titles in the series (copies counted once)")


def _blank_none(value: str | None) -> str | None:
    return value or None


OptionalSeriesName = Annotated[
    str | None,
    StringConstraints(strip_whitespace=True, max_length=300),
    AfterValidator(_blank_none),
]


class SeriesCreate(RequestModel):
    name: SeriesName
    name_en: OptionalSeriesName = None
    name_ru: OptionalSeriesName = None
    description: SeriesDescription = ""


class SeriesUpdate(PatchModel):
    non_nullable_fields: ClassVar[frozenset[str]] = frozenset({"name", "description"})

    name: SeriesName | None = None
    name_en: OptionalSeriesName = None
    name_ru: OptionalSeriesName = None
    description: SeriesDescription | None = None
