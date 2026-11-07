from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import Field

from app.models.enums import BookCategory
from app.schemas.common import ApiModel


class TopBookRead(ApiModel):
    title: str
    author: str
    loans: int


class ReportSummaryRead(ApiModel):
    date_from: date
    date_to: date
    orders_placed: int
    orders_confirmed: int
    books_lent: int
    books_returned: int
    active_readers: int
    overdue_now: int
    revenue: Decimal
    currency: str | None
    top_books: list[TopBookRead]


class WantedTitleRead(ApiModel):
    title: str
    author: str
    readers: int
    copies: int


class TagLoansRead(ApiModel):
    slug: str
    name_en: str
    name_ru: str
    loans: int


class DemandRead(ApiModel):
    waiting: list[WantedTitleRead]
    saved: list[WantedTitleRead]
    tags: list[TagLoansRead]


class MonthStatsRead(ApiModel):
    month: str = Field(description="YYYY-MM, in the library's time zone")
    loans: int = Field(description="Books handed over")
    returns: int = Field(description="Books brought back")
    active_readers: int = Field(description="Readers with a loan handed over that month")
    new_readers: int = Field(description="Reader accounts created that month")


class CategoryLoansRead(ApiModel):
    category: BookCategory
    loans: int
