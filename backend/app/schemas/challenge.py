from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, ClassVar, Self

from pydantic import Field, StringConstraints, model_validator

from app.models.enums import BookCategory
from app.schemas.common import ApiModel, PatchModel, RequestModel

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
OptionalName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
Goal = Annotated[int, Field(ge=1, le=100, description="Books to read")]


class ChallengeProgress(ApiModel):
    child_id: uuid.UUID | None = Field(description="null: the reader themselves")
    child_name: str | None
    read: int = Field(description="Titles read in the challenge's dates that count")
    completed: bool


class ChallengeRead(ApiModel):
    id: uuid.UUID
    name_en: str
    name_ru: str | None
    description_en: str
    description_ru: str | None
    starts_on: date
    ends_on: date
    goal: int
    category: BookCategory | None = Field(description="Only books of this category count")
    participants: int
    completed: int = Field(description="Participants who reached the goal")
    mine: list[ChallengeProgress] = Field(description="The reader's own profiles taking part")


class ChallengeCreate(RequestModel):
    name_en: Name
    name_ru: OptionalName | None = None
    description_en: Description = ""
    description_ru: Description | None = None
    starts_on: date
    ends_on: date
    goal: Goal
    category: BookCategory | None = None

    @model_validator(mode="after")
    def _dates_in_order(self) -> Self:
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on must not be before starts_on")
        return self


class ChallengeUpdate(PatchModel):
    non_nullable_fields: ClassVar[frozenset[str]] = frozenset(
        {"name_en", "description_en", "starts_on", "ends_on", "goal"}
    )

    name_en: Name | None = None
    name_ru: OptionalName | None = None
    description_en: Description | None = None
    description_ru: Description | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    goal: Goal | None = None
    category: BookCategory | None = None


class ChallengeParticipant(ApiModel):
    name: str
    parent_name: str | None = Field(description="For a child: the account it belongs to")
    read: int
    completed: bool
    joined_at: datetime
