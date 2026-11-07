from __future__ import annotations

from datetime import date

from pydantic import Field

from app.schemas.book import BookRead
from app.schemas.common import ApiModel, RequestModel


class BadgeRead(ApiModel):
    key: str = Field(
        description="first_book, five_books, ten_books, twenty_five_books, explorer (3 "
        "categories), two_languages, series_finisher, three_months (a book in each of the last "
        "three months)"
    )
    earned: bool
    progress: int
    goal: int


class LoggedBookRead(ApiModel):
    book: BookRead
    finished_on: date


class ReadingLogRead(ApiModel):
    entries: list[LoggedBookRead]
    total: int
    this_year: int
    badges: list[BadgeRead]
    to_log: list[BookRead] = Field(description="Borrowed titles that are not in the log yet")


class MarkFinished(RequestModel):
    finished_on: date | None = None
