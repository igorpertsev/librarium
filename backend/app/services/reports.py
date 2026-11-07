"""Lending reports for librarians: a summary for a period and an orders export (CSV)."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Book,
    Order,
    OrderItem,
    ReadingListEntry,
    Tag,
    User,
    WaitlistEntry,
    book_tags,
)
from app.models.enums import BookCategory, OrderStatus, UserRole
from app.repositories.books import copy_group_key


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
    "ordered_at", "confirmed_at", "due_date", "returned_at", "cancelled_at", "renewals",
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
                order.renewal_count,
            )
        )
    return buffer.getvalue()


# --- Demand: what to buy more of ---------------------------------------------------------

MAX_DEMAND_ROWS = 10


@dataclass
class WantedTitle:
    title: str
    author: str
    readers: int  # waiting for it, or saved it to read
    copies: int


@dataclass
class TagLoans:
    slug: str
    name_en: str
    name_ru: str
    loans: int


@dataclass
class Demand:
    waiting: list[WantedTitle] = field(default_factory=list)
    saved: list[WantedTitle] = field(default_factory=list)
    tags: list[TagLoans] = field(default_factory=list)


async def _wanted(session: AsyncSession, entries: Any) -> list[WantedTitle]:
    """Titles by the number of readers in ``entries`` (a table with user_id and book_id)."""
    group = copy_group_key()
    readers = (
        select(group.label("grp"), func.count(func.distinct(entries.user_id)).label("readers"))
        .join(entries, entries.book_id == Book.id)
        .where(Book.is_active.is_(True))
        .group_by(group)
        .subquery()
    )
    copies = (
        select(group.label("grp"), func.count().label("copies"))
        .where(Book.is_active.is_(True))
        .group_by(group)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Book.title, Book.author, readers.c.readers, copies.c.copies)
            .join(readers, readers.c.grp == Book.id)
            .join(copies, copies.c.grp == Book.id)
            .order_by(readers.c.readers.desc(), func.lower(Book.title))
            .limit(MAX_DEMAND_ROWS)
        )
    ).all()
    return [WantedTitle(title, author, int(n), int(c)) for title, author, n, c in rows]


async def demand(session: AsyncSession, date_from: date, date_to: date) -> Demand:
    """Titles with the longest waiting lists and the most "want to read" saves (now), and the
    tags of the books lent in the period."""
    start, end = _bounds(date_from, date_to)
    report = Demand(
        waiting=await _wanted(session, WaitlistEntry),
        saved=await _wanted(session, ReadingListEntry),
    )
    rows = (
        await session.execute(
            select(Tag.slug, Tag.name_en, Tag.name_ru, func.count(OrderItem.id).label("loans"))
            .join(book_tags, book_tags.c.tag_id == Tag.id)
            .join(OrderItem, OrderItem.book_id == book_tags.c.book_id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(_within(Order.confirmed_at, start, end))
            .group_by(Tag.id)
            .order_by(func.count(OrderItem.id).desc(), Tag.slug)
            .limit(MAX_DEMAND_ROWS)
        )
    ).all()
    report.tags = [TagLoans(slug, en, ru, int(n)) for slug, en, ru, n in rows]
    return report


# --- Statistics by month -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MonthStats:
    month: str  # YYYY-MM
    loans: int  # books handed over
    returns: int  # books brought back
    active_readers: int  # readers with a loan handed over that month
    new_readers: int  # reader accounts created that month


def _month_starts(until: date, months: int) -> list[date]:
    first = until.replace(day=1)
    starts = []
    year, month = first.year, first.month
    for _ in range(months):
        starts.append(date(year, month, 1))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return starts[::-1]


async def monthly(
    session: AsyncSession, *, until: date, months: int, zone: ZoneInfo
) -> list[MonthStats]:
    """The last ``months`` calendar months up to ``until``, in the library's time zone."""
    starts = _month_starts(until, months)
    since = datetime.combine(starts[0], time.min, tzinfo=zone)

    def month_of(column: Any) -> Any:
        return func.to_char(func.timezone(str(zone), column), "YYYY-MM")

    async def counted(stmt: Any) -> dict[str, int]:
        return {month: int(n) for month, n in (await session.execute(stmt)).all()}

    lent_month = month_of(Order.confirmed_at)
    loans = await counted(
        select(lent_month, func.count(OrderItem.id))
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.confirmed_at >= since)
        .group_by(lent_month)
    )
    readers = await counted(
        select(lent_month, func.count(func.distinct(Order.user_id)))
        .where(Order.confirmed_at >= since)
        .group_by(lent_month)
    )
    back_month = month_of(Order.returned_at)
    returns = await counted(
        select(back_month, func.count(OrderItem.id))
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.returned_at >= since)
        .group_by(back_month)
    )
    joined_month = month_of(User.created_at)
    joined = await counted(
        select(joined_month, func.count(User.id))
        .where(User.created_at >= since, User.role == UserRole.CUSTOMER)
        .group_by(joined_month)
    )
    keys = [f"{start:%Y-%m}" for start in starts]
    return [
        MonthStats(
            month=key,
            loans=loans.get(key, 0),
            returns=returns.get(key, 0),
            active_readers=readers.get(key, 0),
            new_readers=joined.get(key, 0),
        )
        for key in keys
    ]


def monthly_csv(stats: list[MonthStats]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["month", "loans", "returns", "active_readers", "new_readers"])
    for row in stats:
        writer.writerow([row.month, row.loans, row.returns, row.active_readers, row.new_readers])
    return out.getvalue()


@dataclass(frozen=True, slots=True)
class CategoryLoans:
    category: BookCategory
    loans: int


async def categories(session: AsyncSession, date_from: date, date_to: date) -> list[CategoryLoans]:
    """Books handed over in the period, by category (most first)."""
    start, end = _bounds(date_from, date_to)
    loans = func.count(OrderItem.id).label("loans")
    rows = await session.execute(
        select(OrderItem.category, loans)
        .join(Order, Order.id == OrderItem.order_id)
        .where(_within(Order.confirmed_at, start, end))
        .group_by(OrderItem.category)
        .order_by(loans.desc(), OrderItem.category)
    )
    return [CategoryLoans(category, int(n)) for category, n in rows]
