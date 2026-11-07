from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import ClassVar

from pydantic import Field, field_validator

from app.models.enums import PurchaseStatus
from app.schemas.common import ApiModel, PatchModel, RequestModel
from app.schemas.types import AuthorName, Isbn, OptionalNote, Title


class PurchaseRequestCreate(RequestModel):
    title: Title
    author: AuthorName
    isbn: Isbn = Field(default=None, description="ISBN-10 or ISBN-13; stored as its digits")
    note: OptionalNote = None

    @field_validator("isbn")
    @classmethod
    def _ten_or_thirteen_digits(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = re.sub(r"[^0-9Xx]", "", value).upper()
        if len(digits) not in (10, 13):
            raise ValueError("An ISBN has 10 or 13 digits")
        return digits


class PurchaseRequestRead(ApiModel):
    id: uuid.UUID
    title: str
    author: str
    isbn: str | None
    note: str | None
    status: PurchaseStatus
    librarian_note: str | None
    book_id: uuid.UUID | None = Field(description="The catalogue book, once added")
    votes: int
    voted: bool = Field(description="The signed-in reader voted for it")
    mine: bool = Field(description="The signed-in reader suggested it")
    created_at: datetime


class PurchaseRequestCreated(ApiModel):
    request: PurchaseRequestRead
    created: bool = Field(description="False when it was suggested already: it got a vote")


class PurchaseRequestUpdate(PatchModel):
    non_nullable_fields: ClassVar[frozenset[str]] = frozenset({"status"})

    status: PurchaseStatus | None = None
    librarian_note: OptionalNote = None
