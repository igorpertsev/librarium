from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Annotated, ClassVar, Self

from pydantic import BaseModel, Field, WithJsonSchema, model_validator

from app.schemas.common import ApiModel, PatchModel, RequestModel
from app.schemas.types import Address, OptionalNote, PlaceName

# A wall-clock time in the library's time zone, without an offset. JSON Schema's "time" format
# (RFC 3339) requires an offset, so the schema says what is really sent: "HH:MM" or "HH:MM:SS".
LocalTime = Annotated[
    time,
    WithJsonSchema(
        {
            "type": "string",
            "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9](\\.[0-9]+)?)?$",
            "examples": ["09:30", "18:00:00"],
        }
    ),
]
SlotMinutes = Annotated[int, Field(ge=15, le=240)]
SlotCapacity = Annotated[int, Field(ge=1, le=100)]


class OpeningHours(BaseModel):
    """One opening period on a weekday (0 = Monday), in the library's time zone."""

    weekday: int = Field(ge=0, le=6)
    opens: LocalTime
    closes: LocalTime

    @model_validator(mode="after")
    def _closes_after_opening(self) -> Self:
        if self.closes <= self.opens:
            raise ValueError("closes must be after opens")
        return self


Hours = Annotated[list[OpeningHours], Field(max_length=28)]


class PickupPointRead(ApiModel):
    id: uuid.UUID
    name: str
    address: str
    notes: str | None
    hours: list[OpeningHours]
    slot_minutes: int
    slot_capacity: int | None = Field(description="Orders per slot (null: no limit)")
    active: bool


class PickupPointBrief(ApiModel):
    id: uuid.UUID
    name: str
    address: str


class PickupPointCreate(RequestModel):
    name: PlaceName
    address: Address
    notes: OptionalNote = None
    hours: Hours
    slot_minutes: SlotMinutes = 60
    slot_capacity: SlotCapacity | None = None
    active: bool = True


class PickupPointUpdate(PatchModel):
    non_nullable_fields: ClassVar[frozenset[str]] = frozenset(
        {"name", "address", "hours", "slot_minutes", "active"}
    )

    name: PlaceName | None = None
    address: Address | None = None
    notes: OptionalNote = None
    hours: Hours | None = None
    slot_minutes: SlotMinutes | None = None
    slot_capacity: SlotCapacity | None = None
    active: bool | None = None


class PickupSlot(ApiModel):
    starts_at: datetime
    ends_at: datetime
    left: int | None = Field(description="Orders that still fit (null: no limit; 0: full)")


class PickupChoice(RequestModel):
    """Optional body of POST /orders: where and when the reader collects the books, and which
    child of the account they are for."""

    pickup_point_id: uuid.UUID | None = None
    pickup_at: datetime | None = None
    child_id: uuid.UUID | None = None
