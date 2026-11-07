from __future__ import annotations

import uuid
from datetime import datetime
from typing import ClassVar

from pydantic import Field

from app.models.enums import PurchaseStatus
from app.schemas.common import ApiModel, PatchModel, RequestModel
from app.schemas.types import AuthorName, Isbn, OptionalNote, Title


class PurchaseRequestCreate(RequestModel):
    title: Title
    author: AuthorName
    isbn: Isbn = None
    note: OptionalNote = None


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
