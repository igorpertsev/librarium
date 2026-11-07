"""Stocktaking: count the copies on the shelves and compare with the catalogue.

A librarian starts a count and scans the ISBN of every book found (or counts books without an
ISBN by hand). Copies are counted per title, since copies of a title share an ISBN. A title is
expected on the shelf with every active copy that is not out on loan (in an active order) and
not marked "not available". The report lists missing and extra copies and unknown ISBNs.
Finishing can mark the missing copies "not available", with a note.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import String, and_, cast, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models import Book, Stocktake, StocktakeCount, User
from app.models.enums import BookStatus
from app.repositories.books import active_reservation_exists, copy_group_key

ISBN_CHARS = re.compile(r"[^0-9Xx]")


def normalize_isbn(value: str) -> str:
    return ISBN_CHARS.sub("", value).upper()


@dataclass(frozen=True, slots=True)
class TitleLine:
    book_id: uuid.UUID  # one copy of the title, for links and manual counting
    title: str
    author: str
    isbn: str | None
    expected: int
    counted: int
    on_loan: int


@dataclass(frozen=True, slots=True)
class StocktakeReport:
    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    marked_missing: int
    expected: int
    counted: int
    lines: list[TitleLine]  # titles with a difference first, then the rest
    unknown_isbns: list[tuple[str, int]]


@dataclass(frozen=True, slots=True)
class ScanResult:
    found: bool
    isbn: str
    title: str | None
    counted: int
    expected: int | None


def not_found() -> NotFoundError:
    return NotFoundError("Stocktake not found", code="STOCKTAKE_NOT_FOUND")


async def _open(session: AsyncSession, stocktake_id: uuid.UUID) -> Stocktake:
    stocktake = await session.get(Stocktake, stocktake_id)
    if stocktake is None:
        raise not_found()
    if stocktake.finished_at is not None:
        raise ConflictError("This stocktake is finished", code="STOCKTAKE_FINISHED")
    return stocktake


async def start(session: AsyncSession, user: User) -> Stocktake:
    stocktake = Stocktake(id=uuid.uuid4(), started_by_id=user.id)
    session.add(stocktake)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(
            "A stocktake is already open; finish it first", code="STOCKTAKE_OPEN"
        ) from None
    return stocktake


async def current(session: AsyncSession) -> Stocktake | None:
    return await session.scalar(select(Stocktake).where(Stocktake.finished_at.is_(None)))


async def latest(session: AsyncSession, limit: int = 10) -> list[Stocktake]:
    return list(
        (
            await session.scalars(
                select(Stocktake).order_by(Stocktake.started_at.desc()).limit(limit)
            )
        ).all()
    )


async def _add(
    session: AsyncSession,
    stocktake_id: uuid.UUID,
    *,
    group_id: uuid.UUID | None = None,
    isbn: str | None = None,
    delta: int = 1,
) -> int:
    """Add to a count (never below zero); returns the new count."""
    index = ["stocktake_id", "group_id"] if group_id is not None else ["stocktake_id", "isbn"]
    counted = await session.scalar(
        pg_insert(StocktakeCount)
        .values(
            id=uuid.uuid4(),
            stocktake_id=stocktake_id,
            group_id=group_id,
            isbn=isbn,
            counted=max(delta, 0),
        )
        .on_conflict_do_update(
            index_elements=index,
            set_={"counted": func.greatest(StocktakeCount.counted + delta, 0)},
        )
        .returning(StocktakeCount.counted)
    )
    await session.commit()
    return int(counted or 0)


async def _expected(session: AsyncSession, group: uuid.UUID) -> int:
    on_shelf = (
        Book.is_active.is_(True)
        & (Book.status != BookStatus.NOT_AVAILABLE)
        & ~active_reservation_exists(Book.id)
    )
    return int(
        await session.scalar(select(func.count()).where(copy_group_key() == group, on_shelf)) or 0
    )


async def scan(session: AsyncSession, stocktake_id: uuid.UUID, raw_isbn: str) -> ScanResult:
    await _open(session, stocktake_id)
    isbn = normalize_isbn(raw_isbn)
    if len(isbn) not in (10, 13):
        raise BadRequestError("That is not an ISBN", code="INVALID_ISBN")
    row = (
        await session.execute(
            select(copy_group_key(), Book.title)
            .where(
                Book.is_active.is_(True),
                func.upper(func.regexp_replace(Book.isbn, "[^0-9Xx]", "", "g")) == isbn,
            )
            .order_by(Book.created_at)
            .limit(1)
        )
    ).first()
    if row is None:
        counted = await _add(session, stocktake_id, isbn=isbn)
        return ScanResult(found=False, isbn=isbn, title=None, counted=counted, expected=None)
    group, title = row
    counted = await _add(session, stocktake_id, group_id=group)
    return ScanResult(
        found=True,
        isbn=isbn,
        title=title,
        counted=counted,
        expected=await _expected(session, group),
    )


async def count(
    session: AsyncSession, stocktake_id: uuid.UUID, book_id: uuid.UUID, delta: int
) -> int:
    """Count a title by hand (+1, or -1 to correct a mistake)."""
    await _open(session, stocktake_id)
    book = await session.get(Book, book_id)
    if book is None:
        raise NotFoundError("Book not found", code="BOOK_NOT_FOUND")
    return await _add(session, stocktake_id, group_id=book.group_id, delta=delta)


async def report(session: AsyncSession, stocktake_id: uuid.UUID) -> StocktakeReport:
    stocktake = await session.get(Stocktake, stocktake_id)
    if stocktake is None:
        raise not_found()
    group = copy_group_key()
    on_loan = active_reservation_exists(Book.id)
    titles = (
        await session.execute(
            select(
                group,
                func.min(cast(Book.id, String)),
                func.min(Book.title),
                func.min(Book.author),
                func.min(Book.isbn),
                func.count().filter(and_(~on_loan, Book.status != BookStatus.NOT_AVAILABLE)),
                func.count().filter(on_loan),
            )
            .where(Book.is_active.is_(True))
            .group_by(group)
        )
    ).all()
    counts = {
        row.group_id: row.counted
        for row in (
            await session.execute(
                select(StocktakeCount.group_id, StocktakeCount.counted).where(
                    StocktakeCount.stocktake_id == stocktake_id,
                    StocktakeCount.group_id.is_not(None),
                )
            )
        ).all()
    }
    unknown = [
        (row.isbn, row.counted)
        for row in (
            await session.execute(
                select(StocktakeCount.isbn, StocktakeCount.counted)
                .where(
                    StocktakeCount.stocktake_id == stocktake_id, StocktakeCount.isbn.is_not(None)
                )
                .order_by(StocktakeCount.isbn)
            )
        ).all()
        if row.counted > 0
    ]
    lines = [
        TitleLine(
            book_id=uuid.UUID(book_id),
            title=title,
            author=author,
            isbn=isbn,
            expected=int(expected),
            counted=int(counts.get(group_id, 0)),
            on_loan=int(lent),
        )
        for group_id, book_id, title, author, isbn, expected, lent in titles
    ]
    lines.sort(key=lambda line: (line.counted == line.expected, line.title.lower()))
    return StocktakeReport(
        id=stocktake.id,
        started_at=stocktake.started_at,
        finished_at=stocktake.finished_at,
        marked_missing=stocktake.marked_missing,
        expected=sum(line.expected for line in lines),
        counted=sum(line.counted for line in lines),
        lines=lines,
        unknown_isbns=unknown,
    )


async def finish(
    session: AsyncSession, stocktake_id: uuid.UUID, *, mark_missing: bool
) -> StocktakeReport:
    """Close the count; with ``mark_missing`` copies that were not found become "not
    available" with a note (copies on loan are never touched)."""
    stocktake = await _open(session, stocktake_id)
    marked = 0
    if mark_missing:
        today = datetime.now(UTC).date().isoformat()
        for line in (await report(session, stocktake_id)).lines:
            missing = line.expected - line.counted
            if missing <= 0:
                continue
            book = await session.get(Book, line.book_id)
            if book is None:  # pragma: no cover - the report lists existing books
                continue
            copies = (
                await session.scalars(
                    select(Book.id)
                    .where(
                        copy_group_key() == book.group_id,
                        Book.is_active.is_(True),
                        Book.status != BookStatus.NOT_AVAILABLE,
                        ~active_reservation_exists(Book.id),
                    )
                    .order_by(Book.id)
                    .limit(missing)
                )
            ).all()
            await session.execute(
                update(Book)
                .where(Book.id.in_(copies))
                .values(
                    status=BookStatus.NOT_AVAILABLE,
                    condition_note=f"Not found in the stocktake of {today}",
                )
            )
            marked += len(copies)
    stocktake.finished_at = datetime.now(UTC)
    stocktake.marked_missing = marked
    await session.commit()
    return await report(session, stocktake_id)
