from __future__ import annotations

from datetime import date
from decimal import Decimal

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
