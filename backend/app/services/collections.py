"""Collections of titles put together by the librarians, and the book of the month.

A collection keeps titles by their copy group, in the order the librarian chose; featured ones
appear as shelves above the catalogue, every one has a page (``/collections/<slug>``). The book
of the month is one title with a short note, shown at the top of the catalogue.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Book, Collection, CollectionBook
from app.repositories.books import BookFilters, copy_group_key
from app.schemas.book import BookRead, BookSort
from app.services import books as books_service
from app.services.library_settings import get_library_settings

MAX_BOOKS = 100


def not_found() -> NotFoundError:
    return NotFoundError("Collection not found", code="COLLECTION_NOT_FOUND")


@dataclass(frozen=True, slots=True)
class Summary:
    collection: Collection
    book_count: int


@dataclass(frozen=True, slots=True)
class Pick:
    book: BookRead
    note_en: str | None
    note_ru: str | None


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:60] or "collection"


async def _free_slug(session: AsyncSession, wanted: str, keep: uuid.UUID | None = None) -> str:
    slug, n = wanted, 2
    while True:
        taken = await session.scalar(select(Collection.id).where(Collection.slug == slug))
        if taken is None or taken == keep:
            return slug
        slug = f"{wanted[:70]}-{n}"
        n += 1


async def _titles(session: AsyncSession, groups: list[uuid.UUID]) -> list[BookRead]:
    """The titles (active copies) of these groups, in this order."""
    if not groups:
        return []
    found, _ = await books_service.list_books(
        session,
        BookFilters(groups=tuple(groups)),
        sort=BookSort.TITLE,
        page=1,
        page_size=len(groups),
        group_copies=True,
    )
    order = {group: index for index, group in enumerate(groups)}
    return sorted(found, key=lambda book: order.get(book.group_id, len(order)))


async def summaries(session: AsyncSession, *, featured_only: bool = False) -> list[Summary]:
    count = (
        select(func.count())
        .where(CollectionBook.collection_id == Collection.id)
        .correlate(Collection)
        .scalar_subquery()
    )
    stmt = select(Collection, count).order_by(Collection.position, Collection.title_en)
    if featured_only:
        stmt = stmt.where(Collection.featured.is_(True))
    return [Summary(c, n) for c, n in (await session.execute(stmt)).all()]


async def _collection(session: AsyncSession, collection_id: uuid.UUID) -> Collection:
    found = await session.get(Collection, collection_id)
    if found is None:
        raise not_found()
    return found


async def detail(session: AsyncSession, slug: str) -> tuple[Collection, list[BookRead]]:
    collection = await session.scalar(select(Collection).where(Collection.slug == slug))
    if collection is None:
        raise not_found()
    groups = (
        await session.scalars(
            select(CollectionBook.group_id)
            .where(CollectionBook.collection_id == collection.id)
            .order_by(CollectionBook.position)
        )
    ).all()
    return collection, await _titles(session, list(groups))


async def create(session: AsyncSession, values: dict[str, Any]) -> Collection:
    wanted = slugify(values.pop("slug", None) or values["title_en"])
    collection = Collection(id=uuid.uuid4(), slug=await _free_slug(session, wanted), **values)
    session.add(collection)
    await session.commit()
    return collection


async def update(
    session: AsyncSession, collection_id: uuid.UUID, changes: dict[str, Any]
) -> Collection:
    collection = await _collection(session, collection_id)
    if "slug" in changes:
        wanted = slugify(changes.pop("slug"))
        taken = await session.scalar(
            select(Collection.id).where(Collection.slug == wanted, Collection.id != collection.id)
        )
        if taken is not None:
            raise ConflictError("Another collection has this address", code="SLUG_TAKEN")
        collection.slug = wanted
    for name, value in changes.items():
        setattr(collection, name, value)
    await session.commit()
    return collection


async def remove(session: AsyncSession, collection_id: uuid.UUID) -> None:
    await session.delete(await _collection(session, collection_id))
    await session.commit()


async def _groups_of(session: AsyncSession, book_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """The titles of these copies, in the given order, each once (unknown ids are skipped)."""
    rows = (
        await session.execute(select(Book.id, copy_group_key()).where(Book.id.in_(book_ids)))
    ).all()
    group_of = dict(rows)
    return list(dict.fromkeys(group_of[b] for b in book_ids if b in group_of))


async def set_books(
    session: AsyncSession, collection_id: uuid.UUID, book_ids: list[uuid.UUID]
) -> tuple[Collection, list[BookRead]]:
    collection = await _collection(session, collection_id)
    groups = (await _groups_of(session, book_ids))[:MAX_BOOKS]
    await session.execute(
        delete(CollectionBook).where(CollectionBook.collection_id == collection.id)
    )
    session.add_all(
        CollectionBook(collection_id=collection.id, group_id=group, position=index)
        for index, group in enumerate(groups)
    )
    await session.commit()
    return collection, await _titles(session, groups)


# --- Book of the month -----------------------------------------------------------------------


async def pick(session: AsyncSession) -> Pick | None:
    settings = await get_library_settings(session)
    if settings.pick_group_id is None:
        return None
    titles = await _titles(session, [settings.pick_group_id])
    if not titles:  # the title was removed from the catalogue
        return None
    return Pick(titles[0], settings.pick_note_en, settings.pick_note_ru)


async def set_pick(
    session: AsyncSession, book_id: uuid.UUID, note_en: str | None, note_ru: str | None
) -> Pick:
    groups = await _groups_of(session, [book_id])
    if not groups:
        raise NotFoundError("Book not found", code="BOOK_NOT_FOUND")
    settings = await get_library_settings(session, lock="update")
    settings.pick_group_id = groups[0]
    settings.pick_note_en = note_en
    settings.pick_note_ru = note_ru
    await session.commit()
    chosen = await pick(session)
    if chosen is None:  # pragma: no cover - the copy exists, so its title does
        raise NotFoundError("Book not found", code="BOOK_NOT_FOUND")
    return chosen


async def clear_pick(session: AsyncSession) -> None:
    settings = await get_library_settings(session, lock="update")
    settings.pick_group_id = None
    settings.pick_note_en = None
    settings.pick_note_ru = None
    await session.commit()
