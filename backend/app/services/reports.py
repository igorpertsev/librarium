"""Lending reports for librarians: a summary for a period and an orders export (CSV)."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Order, OrderItem
from app.models.enums import OrderStatus


@dataclass
class TopBook:
    title: str
    author: str
    loans: int


@dataclass
class ReportSummary:
    date_from: date
    date_to: date
    orders_placed: int = 0
    orders_confirmed: int = 0
    books_lent: int = 0
    books_returned: int = 0
    active_readers: int = 0
    overdue_now: int = 0
    revenue: Decimal = Decimal("0.00")
    currency: str | None = None
    top_books: list[TopBook] = field(default_factory=list)


def _bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """[start of date_from, start of the day after date_to) in UTC."""
    start = datetime.combine(date_from, time.min, tzinfo=UTC)
    return start, datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)


def _within(column: Any, start: datetime, end: datetime) -> ColumnElement[bool]:
    return and_(column >= start, column < end)


async def summary(session: AsyncSession, date_from: date, date_to: date) -> ReportSummary:
    start, end = _bounds(date_from, date_to)
    report = ReportSummary(date_from=date_from, date_to=date_to)
    confirmed = _within(Order.confirmed_at, start, end)

    report.orders_placed = int(
        await session.scalar(select(func.count()).where(_within(Order.created_at, start, end))) or 0
    )
    row = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(Order.total_amount), 0),
                func.count(func.distinct(Order.user_id)),
                func.min(Order.currency),
            ).where(confirmed)
        )
    ).one()
    report.orders_confirmed, report.revenue, report.active_readers, report.currency = (
        int(row[0]),
        Decimal(row[1]).quantize(Decimal("0.01")),
        int(row[2]),
        row[3],
    )
    report.books_lent = int(
        await session.scalar(
            select(func.count()).select_from(OrderItem).join(Order).where(confirmed)
        )
        or 0
    )
    report.books_returned = int(
        await session.scalar(
            select(func.count())
            .select_from(OrderItem)
            .join(Order)
            .where(_within(Order.returned_at, start, end))
        )
        or 0
    )
    report.overdue_now = int(
        await session.scalar(
            select(func.count()).where(
                Order.status == OrderStatus.CONFIRMED, Order.due_date < datetime.now(UTC).date()
            )
        )
        or 0
    )
    loans = func.count().label("loans")
    top = await session.execute(
        select(OrderItem.title, OrderItem.author, loans)
        .join(Order)
        .where(confirmed)
        .group_by(OrderItem.title, OrderItem.author)
        .order_by(loans.desc(), OrderItem.title)
        .limit(10)
    )
    report.top_books = [TopBook(title, author, int(count)) for title, author, count in top]
    return report


CSV_COLUMNS = (
    "number", "status", "customer", "email", "books", "titles", "total", "currency",
    "ordered_at", "confirmed_at", "due_date", "returned_at", "cancelled_at",
)  # fmt: skip


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    # Spreadsheet apps run cells starting with these as formulas (CSV injection).
    return "'" + text if text[:1] in {"=", "+", "-", "@", "\t", "\r"} else text


async def orders_csv(session: AsyncSession, date_from: date, date_to: date) -> str:
    """Orders placed in the period, oldest first, as CSV."""
    start, end = _bounds(date_from, date_to)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    orders = await session.scalars(
        select(Order)
        .where(_within(Order.created_at, start, end))
        .options(selectinload(Order.items))
        .order_by(Order.created_at, Order.id)
    )
    for order in orders:
        writer.writerow(
            _cell(value)
            for value in (
                order.number,
                order.status.value,
                order.contact_name,
                order.contact_email,
                len(order.items),
                "; ".join(item.title for item in order.items),
                order.total_amount,
                order.currency,
                order.created_at.isoformat(timespec="seconds"),
                order.confirmed_at.isoformat(timespec="seconds") if order.confirmed_at else None,
                order.due_date.isoformat(),
                order.returned_at.isoformat(timespec="seconds") if order.returned_at else None,
                order.cancelled_at.isoformat(timespec="seconds") if order.cancelled_at else None,
            )
        )
    return buffer.getvalue()
