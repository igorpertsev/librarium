from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import ApiModel, RequestModel


class StocktakeBrief(ApiModel):
    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    marked_missing: int


class StocktakeLine(ApiModel):
    book_id: uuid.UUID = Field(description="A copy of the title (for counting by hand)")
    title: str
    author: str
    isbn: str | None
    expected: int = Field(description="Active copies not on loan and not marked not available")
    counted: int
    on_loan: int


class UnknownIsbn(ApiModel):
    isbn: str
    counted: int


class StocktakeReportRead(StocktakeBrief):
    expected: int
    counted: int
    lines: list[StocktakeLine]
    unknown_isbns: list[UnknownIsbn]


class ScanIn(RequestModel):
    isbn: Annotated[str, Field(min_length=10, max_length=20)]


class ScanResultRead(ApiModel):
    found: bool
    isbn: str
    title: str | None
    counted: int
    expected: int | None


class CountIn(RequestModel):
    book_id: uuid.UUID
    delta: Literal[1, -1] = 1


class Counted(ApiModel):
    counted: int


class FinishIn(RequestModel):
    mark_missing: bool = False
