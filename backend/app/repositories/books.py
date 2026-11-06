"""Book queries, including the computed reservation state."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Date,
    Exists,
    ScalarSelect,
    and_,
    case,
    cast,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models import (
    Book,
    BookHold,
    BookTranslation,
    Order,
    OrderItem,
    Series,
    Tag,
    book_tags,
)
from app.models.enums import ACTIVE_ORDER_STATUSES, BookCategory, BookStatus, TranslationSource
from app.schemas.book import BookSort, QualityIssue


def copy_group_key() -> ColumnElement[uuid.UUID]:
    """Copies of one title share this key (a copy without a group is its own group)."""
    return func.coalesce(Book.copy_group_id, Book.id)


def active_reservation_exists(book_id: InstrumentedAttribute[uuid.UUID]) -> Exists:
    """EXISTS(an order in an ACTIVE status contains this copy)."""
    return exists().where(
        OrderItem.book_id == book_id,
        OrderItem.order_id == Order.id,
        Order.status.in_(ACTIVE_ORDER_STATUSES),
    )


def active_reservation_due_date(book_id: InstrumentedAttribute[uuid.UUID]) -> ScalarSelect[date]:
    """Due date of the active order holding this copy; NULL when the copy is free.

    Every active order has a due date, so this also answers "is the copy reserved?".
    """
    return (
        select(Order.due_date)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(OrderItem.book_id == book_id, Order.status.in_(ACTIVE_ORDER_STATUSES))
        .order_by(Order.due_date.desc())
        .limit(1)
        .scalar_subquery()
    )


def active_hold_until(book_id: InstrumentedAttribute[uuid.UUID]) -> ScalarSelect[date]:
    """Last day of an unexpired hold on this copy for the next reader; NULL when none."""
    return (
        select(cast(BookHold.held_until, Date))
        .where(BookHold.book_id == book_id, BookHold.held_until > func.now())
        .scalar_subquery()
    )


def active_hold_exists(book_id: InstrumentedAttribute[uuid.UUID]) -> Exists:
    return exists().where(BookHold.book_id == book_id, BookHold.held_until > func.now())


def unavailable_until(book_id: InstrumentedAttribute[uuid.UUID]) -> ColumnElement[date]:
    """When the copy is expected to be free again: the due date of the order holding it, or
    the end of a hold for another reader; NULL when it is free."""
    return func.coalesce(active_reservation_due_date(book_id), active_hold_until(book_id))


async def reserved_book_ids(session: AsyncSession, book_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    ids = list(book_ids)
    if not ids:
        return set()
    stmt = (
        select(OrderItem.book_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(OrderItem.book_id.in_(ids), Order.status.in_(ACTIVE_ORDER_STATUSES))
    )
    return set((await session.scalars(stmt)).all())


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# Allow-list mapping from API sort keys to columns; user input never reaches SQL text.
_SORT_COLUMNS: dict[BookSort, ColumnElement[Any]] = {
    BookSort.TITLE: func.lower(Book.title).asc(),
    BookSort.TITLE_DESC: func.lower(Book.title).desc(),
    BookSort.AUTHOR: func.lower(Book.author).asc(),
    BookSort.AUTHOR_DESC: func.lower(Book.author).desc(),
    BookSort.PUBLICATION_YEAR: Book.publication_year.asc().nulls_last(),
    BookSort.PUBLICATION_YEAR_DESC: Book.publication_year.desc().nulls_last(),
    BookSort.CREATED_AT: Book.created_at.asc(),
    BookSort.CREATED_AT_DESC: Book.created_at.desc(),
    BookSort.RELEVANCE: func.lower(Book.title).asc(),  # without a search text
    BookSort.SERIES: Book.series_position.asc().nulls_last(),
}

# word_similarity() above which a title or author counts as a (possibly misspelt) match:
# "hobit" ~ "The Hobbit" 0.63, "harri poter" ~ "Harry Potter..." 0.56, unrelated <= 0.25.
TYPO_SIMILARITY = 0.5


def _search_query(text: str) -> ColumnElement[Any]:
    """Words of the search text; quotes, OR and -word work as on web search engines."""
    return func.websearch_to_tsquery("simple", text)


def search_condition(text: str) -> ColumnElement[bool]:
    pattern = f"%{escape_like(text)}%"
    clauses: list[ColumnElement[bool]] = [
        Book.search_vector.op("@@")(_search_query(text)),
        Book.title.ilike(pattern, escape="\\"),
        Book.author.ilike(pattern, escape="\\"),
        Book.isbn.ilike(pattern, escape="\\"),
        func.word_similarity(literal(text), Book.title) >= TYPO_SIMILARITY,
        func.word_similarity(literal(text), Book.author) >= TYPO_SIMILARITY,
    ]
    # Tag names in both languages and series names (also misspelt) find their books.
    clauses.append(
        Book.id.in_(
            select(book_tags.c.book_id)
            .join(Tag, Tag.id == book_tags.c.tag_id)
            .where(
                or_(
                    Tag.name_en.ilike(pattern, escape="\\"),
                    Tag.name_ru.ilike(pattern, escape="\\"),
                    Tag.slug.ilike(pattern, escape="\\"),
                )
            )
        )
    )
    # Translated titles, authors and descriptions ("над пропастью" finds the English book).
    translated_text = func.to_tsvector(
        "simple",
        BookTranslation.title + " " + BookTranslation.author + " " + BookTranslation.description,
    )
    clauses.append(
        Book.id.in_(
            select(BookTranslation.book_id).where(
                or_(
                    translated_text.op("@@")(_search_query(text)),
                    BookTranslation.title.ilike(pattern, escape="\\"),
                    BookTranslation.author.ilike(pattern, escape="\\"),
                    func.word_similarity(literal(text), BookTranslation.title) >= TYPO_SIMILARITY,
                )
            )
        )
    )
    clauses.append(
        Book.series_id.in_(
            select(Series.id).where(
                or_(
                    Series.name.ilike(pattern, escape="\\"),
                    Series.name_en.ilike(pattern, escape="\\"),
                    Series.name_ru.ilike(pattern, escape="\\"),
                    func.word_similarity(literal(text), Series.name) >= TYPO_SIMILARITY,
                )
            )
        )
    )
    digits = re.sub(r"[^0-9Xx]", "", text)
    if len(digits) >= 4 and len(digits) >= len(text.replace(" ", "")) - 4:  # looks like an ISBN
        clauses.append(func.regexp_replace(Book.isbn, "[^0-9Xx]", "", "g").ilike(f"%{digits}%"))
    return or_(*clauses)


def relevance(text: str) -> ColumnElement[float]:
    """Full-text rank, plus how well the text matches words of the title or author, plus how
    close it is to the whole title (so "dune" ranks "Dune" above "Children of Dune")."""
    full_text = func.ts_rank_cd(Book.search_vector, _search_query(text)) * 2
    translated_title = (
        select(func.max(func.word_similarity(literal(text), BookTranslation.title)))
        .where(BookTranslation.book_id == Book.id)
        .scalar_subquery()
    )
    words = func.greatest(
        func.word_similarity(literal(text), Book.title),
        func.word_similarity(literal(text), Book.author) * 0.8,
        func.coalesce(translated_title, 0),
    )
    return full_text + words + func.similarity(literal(text), Book.title)


def quality_condition(issue: QualityIssue) -> ColumnElement[bool]:
    has_translation = exists().where(BookTranslation.book_id == Book.id)
    conditions: dict[QualityIssue, ColumnElement[bool]] = {
        QualityIssue.NO_COVER: or_(Book.cover_url.is_(None), Book.cover_url == ""),
        QualityIssue.NO_DESCRIPTION: Book.description == "",
        QualityIssue.NO_TAGS: ~exists().where(book_tags.c.book_id == Book.id),
        QualityIssue.NO_ISBN: or_(Book.isbn.is_(None), Book.isbn == ""),
        QualityIssue.NO_TRANSLATION: ~has_translation,
        QualityIssue.MACHINE_TRANSLATION: exists().where(
            BookTranslation.book_id == Book.id,
            or_(
                BookTranslation.title_source == TranslationSource.MACHINE,
                BookTranslation.description_source == TranslationSource.MACHINE,
            ),
        ),
    }
    return conditions[issue]


async def quality_counts(session: AsyncSession) -> tuple[int, dict[QualityIssue, int]]:
    """Active titles, and how many of them have each gap (copies of a title count once)."""
    group = copy_group_key()
    columns = [func.count(func.distinct(group))] + [
        func.count(func.distinct(case((quality_condition(issue), group)))) for issue in QualityIssue
    ]
    row = (await session.execute(select(*columns).where(Book.is_active.is_(True)))).one()
    return int(row[0]), {issue: int(row[i + 1]) for i, issue in enumerate(QualityIssue)}


@dataclass(frozen=True, slots=True)
class BookFilters:
    q: str | None = None
    category: BookCategory | None = None
    age_range: str | None = None
    status: BookStatus | None = None
    available: bool | None = None
    include_inactive: bool = False
    tags: tuple[str, ...] = ()  # slugs; a book must have every one of them
    series_id: uuid.UUID | None = None
    language: str | None = None  # ISO 639 code
    groups: tuple[uuid.UUID, ...] | None = None  # only these titles (copy groups)
    author: str | None = None  # exact name, any case
    quality: QualityIssue | None = None


def _conditions(
    filters: BookFilters, *, per_copy_availability: bool = True
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if not filters.include_inactive:
        conditions.append(Book.is_active.is_(True))
    if filters.q:
        conditions.append(search_condition(filters.q))
    if filters.category is not None:
        conditions.append(Book.category == filters.category)
    if filters.age_range:
        conditions.append(Book.age_range == filters.age_range)
    if filters.status is not None:
        conditions.append(Book.status == filters.status)
    for slug in filters.tags:
        conditions.append(
            Book.id.in_(
                select(book_tags.c.book_id)
                .join(Tag, Tag.id == book_tags.c.tag_id)
                .where(Tag.slug == slug)
            )
        )
    if filters.series_id is not None:
        conditions.append(Book.series_id == filters.series_id)
    if filters.language:
        conditions.append(Book.language == filters.language)
    if filters.groups is not None:
        conditions.append(copy_group_key().in_(filters.groups))
    if filters.author:
        conditions.append(func.lower(Book.author) == filters.author.strip().lower())
    if filters.quality is not None:
        conditions.append(quality_condition(filters.quality))
    if filters.available is not None and per_copy_availability:
        reserved = active_reservation_exists(Book.id) | active_hold_exists(Book.id)
        is_available = Book.is_active.is_(True) & (Book.status == BookStatus.AVAILABLE) & ~reserved
        conditions.append(is_available if filters.available else ~is_available)
    return conditions


@dataclass(frozen=True, slots=True)
class ListedBook:
    book: Book
    reserved_until: date | None  # due date of the active order holding this copy
    copies: int  # copies of the title matching the filters
    copies_available: int


async def list_books(
    session: AsyncSession,
    filters: BookFilters,
    *,
    sort: BookSort,
    page: int,
    page_size: int,
    group_copies: bool = False,
) -> tuple[list[ListedBook], int]:
    """Books of one page with their reservation state and copy counts.

    ``group_copies``: one entry per title (copy group), represented by its best copy: an
    available one if there is any, otherwise the reserved copy expected back first. The
    ``available`` filter then applies to the title (any copy available) instead of the copy.
    """
    group = copy_group_key()
    copies = (
        select(
            Book.id.label("id"),
            group.label("grp"),
            unavailable_until(Book.id).label("reserved_until"),
            (Book.is_active.is_(True) & (Book.status == BookStatus.AVAILABLE)).label("lendable"),
        )
        .where(*_conditions(filters, per_copy_availability=not group_copies))
        .subquery("copies")
    )
    available = and_(copies.c.lendable, copies.c.reserved_until.is_(None))
    ranked = select(
        copies.c.id,
        copies.c.reserved_until,
        func.row_number()
        .over(
            partition_by=copies.c.grp if group_copies else copies.c.id,
            order_by=(
                case((available, 0), else_=1),
                copies.c.reserved_until.asc().nulls_last(),
                copies.c.id,
            ),
        )
        .label("rank"),
        func.count().over(partition_by=copies.c.grp).label("copies"),
        # sum(CASE) rather than count(*) FILTER: PostgreSQL cannot use the latter as a
        # "run condition" for the filter below ("WindowFunc not found in subplan target lists").
        func.sum(case((available, 1), else_=0))
        .over(partition_by=copies.c.grp)
        .label("copies_available"),
    ).subquery("ranked")

    outer: list[ColumnElement[bool]] = [ranked.c.rank == 1]
    if group_copies and filters.available is not None:
        outer.append(
            ranked.c.copies_available > 0 if filters.available else ranked.c.copies_available == 0
        )
    total = await session.scalar(select(func.count()).select_from(ranked).where(*outer))
    stmt = (
        select(Book, ranked.c.reserved_until, ranked.c.copies, ranked.c.copies_available)
        .join(ranked, ranked.c.id == Book.id)
        .where(*outer)
        .order_by(
            relevance(filters.q).desc()
            if sort is BookSort.RELEVANCE and filters.q
            else _SORT_COLUMNS[sort],
            func.lower(Book.title),
            Book.id,
        )
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    rows = (await session.execute(stmt)).all()
    return [ListedBook(row[0], row[1], int(row[2]), int(row[3])) for row in rows], int(total or 0)


async def copy_counts(session: AsyncSession, book: Book) -> tuple[int, int]:
    """(active copies, copies available now) of the book's title."""
    group = copy_group_key()
    key = book.copy_group_id or book.id
    reserved = active_reservation_exists(Book.id) | active_hold_exists(Book.id)
    available = Book.status == BookStatus.AVAILABLE
    row = (
        await session.execute(
            select(func.count(), func.count().filter(available & ~reserved)).where(
                group == key, Book.is_active.is_(True)
            )
        )
    ).one()
    return int(row[0]), int(row[1])


async def get_book_with_reservation(
    session: AsyncSession, book_id: uuid.UUID
) -> tuple[Book, date | None] | None:
    """The book and the due date of the order reserving it (None when free)."""
    stmt = select(Book, unavailable_until(Book.id).label("reserved_until")).where(
        Book.id == book_id
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return row[0], row[1]


async def distinct_languages(session: AsyncSession) -> Sequence[str]:
    stmt = (
        select(Book.language)
        .where(Book.is_active.is_(True), Book.language.is_not(None), Book.language != "")
        .distinct()
        .order_by(Book.language)
    )
    return [language for language in (await session.scalars(stmt)).all() if language]


async def distinct_age_ranges(session: AsyncSession) -> Sequence[str]:
    stmt = (
        select(Book.age_range)
        .where(Book.is_active.is_(True), Book.age_range != "")
        .distinct()
        .order_by(Book.age_range)
    )
    return (await session.scalars(stmt)).all()
