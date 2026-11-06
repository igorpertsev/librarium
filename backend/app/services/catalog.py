"""Tags and series: the librarian-kept lists books are grouped by."""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Iterable

from sqlalchemy import ScalarSelect, Select, Uuid, delete, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models import Book, Series, Tag, book_tags
from app.schemas.catalog import (
    SeriesCreate,
    SeriesRead,
    SeriesUpdate,
    TagCreate,
    TagRead,
    TagUpdate,
)


def _titles() -> Select[int]:
    """Count of active titles (copies of a title count once)."""
    group = func.coalesce(Book.copy_group_id, Book.id)
    return select(func.count(func.distinct(group))).where(Book.is_active.is_(True))


def _titles_with_tag() -> ScalarSelect[int]:
    return (
        _titles()
        .join(book_tags, book_tags.c.book_id == Book.id)
        .where(book_tags.c.tag_id == Tag.id)
        .correlate(Tag)
        .scalar_subquery()
    )


def _titles_in_series() -> ScalarSelect[int]:
    return _titles().where(Book.series_id == Series.id).correlate(Series).scalar_subquery()


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:64].strip("-")


# --- Tags -------------------------------------------------------------------------------


def tag_not_found() -> NotFoundError:
    return NotFoundError("Tag not found", code="TAG_NOT_FOUND")


async def list_tags(session: AsyncSession) -> list[TagRead]:
    rows = (await session.execute(select(Tag, _titles_with_tag()).order_by(Tag.name_en))).all()
    return [
        TagRead(id=tag.id, slug=tag.slug, name_en=tag.name_en, name_ru=tag.name_ru, book_count=n)
        for tag, n in rows
    ]


async def _commit_tag(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("A tag with this slug already exists", code="TAG_EXISTS") from exc


async def create_tag(session: AsyncSession, data: TagCreate) -> Tag:
    slug = data.slug or slugify(data.name_en)
    if not slug:
        raise BadRequestError("Give the tag a slug (latin letters and digits)", code="TAG_SLUG")
    tag = Tag(id=uuid.uuid4(), slug=slug, name_en=data.name_en, name_ru=data.name_ru)
    session.add(tag)
    await _commit_tag(session)
    return tag


async def update_tag(session: AsyncSession, tag_id: uuid.UUID, patch: TagUpdate) -> Tag:
    tag = await session.get(Tag, tag_id)
    if tag is None:
        raise tag_not_found()
    for field, value in patch.changes().items():
        setattr(tag, field, value)
    await _commit_tag(session)
    return tag


async def delete_tag(session: AsyncSession, tag_id: uuid.UUID) -> None:
    result = await session.execute(delete(Tag).where(Tag.id == tag_id).returning(Tag.id))
    if result.first() is None:
        raise tag_not_found()
    await session.commit()


async def merge_tags(session: AsyncSession, tag_id: uuid.UUID, into_id: uuid.UUID) -> None:
    """Give every book of ``tag_id`` the tag ``into_id`` and delete ``tag_id``."""
    if tag_id == into_id:
        raise BadRequestError("A tag cannot be merged into itself", code="SAME_TAG")
    if await session.get(Tag, tag_id) is None or await session.get(Tag, into_id) is None:
        raise tag_not_found()
    await session.execute(
        pg_insert(book_tags)
        .from_select(
            ["book_id", "tag_id"],
            select(book_tags.c.book_id, literal(into_id, type_=Uuid)).where(
                book_tags.c.tag_id == tag_id
            ),
        )
        .on_conflict_do_nothing()
    )
    await session.execute(delete(Tag).where(Tag.id == tag_id))
    await session.commit()


async def tag_lookup(session: AsyncSession) -> dict[str, str]:
    """Slug, English and Russian name (lower case) -> slug: for CSV imports."""
    lookup: dict[str, str] = {}
    for tag in (await session.scalars(select(Tag))).all():
        for key in (tag.slug, tag.name_en, tag.name_ru):
            lookup.setdefault(key.strip().lower(), tag.slug)
    return lookup


async def resolve_tags(session: AsyncSession, slugs: Iterable[str]) -> list[Tag]:
    wanted = list(dict.fromkeys(slugs))
    if not wanted:
        return []
    tags = (await session.scalars(select(Tag).where(Tag.slug.in_(wanted)))).all()
    unknown = sorted(set(wanted) - {tag.slug for tag in tags})
    if unknown:
        raise BadRequestError(
            f"Unknown tags: {', '.join(unknown)}", code="UNKNOWN_TAGS", details={"tags": unknown}
        )
    return sorted(tags, key=lambda tag: tag.slug)


# --- Series -----------------------------------------------------------------------------


def series_not_found() -> NotFoundError:
    return NotFoundError("Series not found", code="SERIES_NOT_FOUND")


def _series_read(series: Series, book_count: int) -> SeriesRead:
    return SeriesRead(
        id=series.id,
        name=series.name,
        description=series.description,
        openlibrary_key=series.openlibrary_key,
        book_count=book_count,
    )


async def list_series(session: AsyncSession, q: str | None = None) -> list[SeriesRead]:
    stmt = select(Series, _titles_in_series()).order_by(func.lower(Series.name))
    if q:
        stmt = stmt.where(Series.name.ilike(f"%{q.strip()}%"))
    rows = (await session.execute(stmt.limit(200))).all()
    return [_series_read(series, n) for series, n in rows]


async def get_series(session: AsyncSession, series_id: uuid.UUID) -> SeriesRead:
    row = (
        await session.execute(select(Series, _titles_in_series()).where(Series.id == series_id))
    ).first()
    if row is None:
        raise series_not_found()
    return _series_read(row[0], row[1])


async def _commit_series(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("A series with this name already exists", code="SERIES_EXISTS") from exc


async def create_series(session: AsyncSession, data: SeriesCreate) -> SeriesRead:
    if await _series_by_name(session, data.name) is not None:
        raise ConflictError("A series with this name already exists", code="SERIES_EXISTS")
    series = Series(id=uuid.uuid4(), name=data.name, description=data.description)
    session.add(series)
    await _commit_series(session)
    return _series_read(series, 0)


async def update_series(
    session: AsyncSession, series_id: uuid.UUID, patch: SeriesUpdate
) -> SeriesRead:
    series = await session.get(Series, series_id)
    if series is None:
        raise series_not_found()
    changes = patch.changes()
    if "name" in changes:
        other = await _series_by_name(session, changes["name"])
        if other is not None and other.id != series.id:
            raise ConflictError("A series with this name already exists", code="SERIES_EXISTS")
    for field, value in changes.items():
        setattr(series, field, value)
    await _commit_series(session)
    return await get_series(session, series_id)


async def delete_series(session: AsyncSession, series_id: uuid.UUID) -> None:
    """The books stay in the catalogue, without a series."""
    if await session.get(Series, series_id) is None:
        raise series_not_found()
    await session.execute(
        update(Book).where(Book.series_id == series_id).values(series_id=None, series_position=None)
    )
    await session.execute(delete(Series).where(Series.id == series_id))
    await session.commit()


async def merge_series(session: AsyncSession, series_id: uuid.UUID, into_id: uuid.UUID) -> None:
    """Move the books of ``series_id`` to ``into_id`` and delete ``series_id``."""
    if series_id == into_id:
        raise BadRequestError("A series cannot be merged into itself", code="SAME_SERIES")
    source = await session.get(Series, series_id)
    target = await session.get(Series, into_id)
    if source is None or target is None:
        raise series_not_found()
    await session.execute(update(Book).where(Book.series_id == series_id).values(series_id=into_id))
    key = source.openlibrary_key
    await session.delete(source)
    await session.flush()
    if target.openlibrary_key is None and key is not None:
        target.openlibrary_key = key  # later ISBN lookups of either edition find the target
    await session.commit()


async def _series_by_name(session: AsyncSession, name: str) -> Series | None:
    return await session.scalar(
        select(Series).where(func.lower(Series.name) == name.strip().lower()).limit(1)
    )


async def find_series(
    session: AsyncSession, *, name: str | None, openlibrary_key: str | None
) -> Series | None:
    if openlibrary_key:
        series = await session.scalar(
            select(Series).where(Series.openlibrary_key == openlibrary_key)
        )
        if series is not None:
            return series
    return await _series_by_name(session, name) if name else None


async def find_or_create_series(
    session: AsyncSession, *, name: str, openlibrary_key: str | None = None
) -> Series:
    """Series by Open Library key, then by name (any case); created when missing."""
    series = await find_series(session, name=name, openlibrary_key=openlibrary_key)
    if series is None:
        series = Series(id=uuid.uuid4(), name=name.strip(), openlibrary_key=openlibrary_key)
        session.add(series)
        await session.flush()
    elif openlibrary_key and series.openlibrary_key is None:
        series.openlibrary_key = openlibrary_key
    return series
