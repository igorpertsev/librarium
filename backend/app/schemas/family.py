from __future__ import annotations

import uuid
from typing import Annotated, ClassVar

from pydantic import AfterValidator, Field, StringConstraints

from app.schemas.common import ApiModel, PatchModel, RequestModel
from app.schemas.types import no_control_chars

ChildName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(no_control_chars),
]
BirthYear = Annotated[int, Field(ge=1990, le=2100)]


class ChildRead(ApiModel):
    id: uuid.UUID
    name: str
    birth_year: int | None


class ChildCreate(RequestModel):
    name: ChildName
    birth_year: BirthYear | None = None


class ChildUpdate(PatchModel):
    non_nullable_fields: ClassVar[frozenset[str]] = frozenset({"name"})

    name: ChildName | None = None
    birth_year: BirthYear | None = None
