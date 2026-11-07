"""Purchase requests: readers suggest books for the library to buy and vote for them.

A suggestion for a book that someone already suggested (same ISBN, or same title and author)
counts as a vote for that one. Books already in the catalogue cannot be suggested. Librarians
mark suggestions ordered, added or declined; "added" links the catalogue book (found by ISBN,
or title and author) and tells everyone who voted.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Book, Notification, PurchaseRequest, PurchaseVote, User
from app.models.enums import NotificationKind, PurchaseStatus

MAX_OPEN_PER_READER = 10
ACTIVE = (PurchaseStatus.OPEN, PurchaseStatus.ORDERED)


def _isbn(value: str | None) -> str | None:
    digits = re.sub(r"[^0-9Xx]", "", value or "").upper()
    return digits or None


@dataclass(frozen=True, slots=True)
class RequestView:
    id: uuid.UUID
    title: str
    author: str
    isbn: str | None
    note: str | None
    status: PurchaseStatus
    librarian_note: str | None
    book_id: uuid.UUID | None
    votes: int
    voted: bool
    mine: bool
    created_at: datetime


def not_found() -> NotFoundError:
    return NotFoundError("Suggestion not found", code="PURCHASE_REQUEST_NOT_FOUND")


def _catalogue_match(title: str, author: str, isbn: str | None) -> Select[uuid.UUID]:
    by_title = (func.lower(Book.title) == title.strip().lower()) & (
        func.lower(Book.author) == author.strip().lower()
    )
    by_isbn = (
        func.upper(func.regexp_replace(Book.isbn, "[^0-9Xx]", "", "g")) == isbn if isbn else None
    )
    condition = or_(by_title, by_isbn) if by_isbn is not None else by_title
    return select(Book.id).where(Book.is_active.is_(True), condition).limit(1)


async def _views(
    session: AsyncSession, user: User, requests: list[PurchaseRequest]
) -> list[RequestView]:
    ids = [r.id for r in requests]
    votes: dict[uuid.UUID, int] = {}
    if ids:
        rows = await session.execute(
            select(PurchaseVote.request_id, func.count())
            .where(PurchaseVote.request_id.in_(ids))
            .group_by(PurchaseVote.request_id)
        )
        votes = {row[0]: int(row[1]) for row in rows.all()}
    mine = (
        set(
            (
                await session.scalars(
                    select(PurchaseVote.request_id).where(
                        PurchaseVote.request_id.in_(ids), PurchaseVote.user_id == user.id
                    )
                )
            ).all()
        )
        if ids
        else set()
    )
    return [
        RequestView(
            id=r.id,
            title=r.title,
            author=r.author,
            isbn=r.isbn,
            note=r.note,
            status=r.status,
            librarian_note=r.librarian_note,
            book_id=r.book_id,
            votes=int(votes.get(r.id, 0)),
            voted=r.id in mine,
            mine=r.created_by_id == user.id,
            created_at=r.created_at,
        )
        for r in requests
    ]


async def list_requests(
    session: AsyncSession, user: User, statuses: tuple[PurchaseStatus, ...] | None = None
) -> list[RequestView]:
    """Most votes first, then newest."""
    votes = (
        select(func.count())
        .where(PurchaseVote.request_id == PurchaseRequest.id)
        .correlate(PurchaseRequest)
        .scalar_subquery()
    )
    stmt = select(PurchaseRequest).order_by(votes.desc(), PurchaseRequest.created_at.desc())
    if statuses:
        stmt = stmt.where(PurchaseRequest.status.in_(statuses))
    requests = list((await session.scalars(stmt.limit(200))).all())
    return await _views(session, user, requests)


async def _view(session: AsyncSession, user: User, request: PurchaseRequest) -> RequestView:
    return (await _views(session, user, [request]))[0]


async def vote(session: AsyncSession, user: User, request_id: uuid.UUID) -> RequestView:
    request = await session.get(PurchaseRequest, request_id)
    if request is None:
        raise not_found()
    await session.execute(
        pg_insert(PurchaseVote)
        .values(request_id=request_id, user_id=user.id)
        .on_conflict_do_nothing()
    )
    await session.commit()
    return await _view(session, user, request)


async def unvote(session: AsyncSession, user: User, request_id: uuid.UUID) -> RequestView:
    request = await session.get(PurchaseRequest, request_id)
    if request is None:
        raise not_found()
    await session.execute(
        delete(PurchaseVote).where(
            PurchaseVote.request_id == request_id, PurchaseVote.user_id == user.id
        )
    )
    await session.commit()
    return await _view(session, user, request)


async def suggest(
    session: AsyncSession,
    user: User,
    *,
    title: str,
    author: str,
    isbn: str | None,
    note: str | None,
) -> tuple[RequestView, bool]:
    """Create a suggestion (or vote for the same one); returns it and whether it was new."""
    isbn = _isbn(isbn)
    in_catalogue = await session.scalar(_catalogue_match(title, author, isbn))
    if in_catalogue is not None:
        raise ConflictError(
            "This book is already in the catalogue",
            code="ALREADY_IN_CATALOGUE",
            details={"book_id": str(in_catalogue)},
        )
    same_title = (func.lower(PurchaseRequest.title) == title.strip().lower()) & (
        func.lower(PurchaseRequest.author) == author.strip().lower()
    )
    existing = await session.scalar(
        select(PurchaseRequest)
        .where(
            PurchaseRequest.status.in_(ACTIVE),
            or_(same_title, PurchaseRequest.isbn == isbn) if isbn else same_title,
        )
        .limit(1)
    )
    if existing is not None:
        return await vote(session, user, existing.id), False
    open_count = await session.scalar(
        select(func.count()).where(
            PurchaseRequest.created_by_id == user.id, PurchaseRequest.status.in_(ACTIVE)
        )
    )
    if (open_count or 0) >= MAX_OPEN_PER_READER:
        raise ConflictError(
            f"You can have up to {MAX_OPEN_PER_READER} open suggestions",
            code="TOO_MANY_SUGGESTIONS",
            details={"limit": MAX_OPEN_PER_READER},
        )
    request = PurchaseRequest(
        id=uuid.uuid4(),
        created_by_id=user.id,
        title=title.strip(),
        author=author.strip(),
        isbn=isbn,
        note=note,
    )
    session.add(request)
    session.add(PurchaseVote(request_id=request.id, user_id=user.id))
    await session.commit()
    return await _view(session, user, request), True


async def update(
    session: AsyncSession,
    staff: User,
    request_id: uuid.UUID,
    *,
    status: PurchaseStatus | None,
    librarian_note: str | None,
    note_given: bool,
) -> RequestView:
    request = await session.get(PurchaseRequest, request_id, with_for_update=True)
    if request is None:
        raise not_found()
    if note_given:
        request.librarian_note = librarian_note
    if status is not None and status is not request.status:
        if status is PurchaseStatus.ADDED:
            book_id = await session.scalar(
                _catalogue_match(request.title, request.author, request.isbn)
            )
            if book_id is None:
                raise ConflictError(
                    "Add the book to the catalogue first (same ISBN, or title and author)",
                    code="BOOK_NOT_IN_CATALOGUE",
                )
            request.book_id = book_id
            voters = (
                await session.scalars(
                    select(PurchaseVote.user_id).where(PurchaseVote.request_id == request.id)
                )
            ).all()
            for voter in voters:
                session.add(
                    Notification(
                        id=uuid.uuid4(),
                        user_id=voter,
                        book_id=book_id,
                        kind=NotificationKind.PURCHASE_ADDED,
                    )
                )
        request.status = status
    await session.commit()
    return await _view(session, staff, request)
