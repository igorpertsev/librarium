"""Ratings and short reviews of titles, by readers who borrowed them.

A rating without text is published at once; a written review waits for a librarian
(moderation), and so does an edited one. One review per reader and title.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models import Book, Order, OrderItem, Review, User
from app.models.enums import OrderStatus, ReviewStatus
from app.repositories.books import copy_group_key
from app.services import books as books_service

_BORROWED = (OrderStatus.CONFIRMED, OrderStatus.RETURNED)
MAX_PUBLIC = 50


def display_name(full_name: str) -> str:
    """ "Dana Reader" -> "Dana R.": readers are named, but not fully."""
    words = full_name.split()
    if not words:
        return "Reader"
    if len(words) == 1:
        return words[0]
    return f"{words[0]} {words[-1][0]}."


def review_not_found() -> NotFoundError:
    return NotFoundError("Review not found", code="REVIEW_NOT_FOUND")


@dataclass(frozen=True, slots=True)
class PublicReview:
    id: uuid.UUID
    author_name: str
    rating: int
    text: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Summary:
    average: float | None
    count: int
    reviews: list[PublicReview]


async def _group_of(session: AsyncSession, book_id: uuid.UUID) -> uuid.UUID:
    return (await books_service.get_book(session, book_id)).group_id


async def summary(session: AsyncSession, book_id: uuid.UUID) -> Summary:
    """Average and number of published ratings, and the published reviews with text."""
    group = await _group_of(session, book_id)
    in_title = (Book.id == Review.book_id, copy_group_key() == group)
    published = Review.status == ReviewStatus.PUBLISHED
    average, count = (
        await session.execute(
            select(func.avg(Review.rating), func.count(Review.id))
            .join(Book, in_title[0])
            .where(in_title[1], published)
        )
    ).one()
    rows = (
        await session.execute(
            select(Review, User.full_name)
            .join(Book, in_title[0])
            .join(User, User.id == Review.user_id)
            .where(in_title[1], published, Review.text != "")
            .order_by(Review.created_at.desc())
            .limit(MAX_PUBLIC)
        )
    ).all()
    return Summary(
        average=round(float(average), 1) if average is not None else None,
        count=int(count),
        reviews=[
            PublicReview(r.id, display_name(name), r.rating, r.text, r.created_at)
            for r, name in rows
        ],
    )


async def _borrowed(session: AsyncSession, user: User, group: uuid.UUID) -> bool:
    found = await session.scalar(
        select(OrderItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Book, Book.id == OrderItem.book_id)
        .where(Order.user_id == user.id, Order.status.in_(_BORROWED), copy_group_key() == group)
        .limit(1)
    )
    return found is not None


async def _own(session: AsyncSession, user: User, group: uuid.UUID) -> Review | None:
    return await session.scalar(
        select(Review)
        .join(Book, Book.id == Review.book_id)
        .where(Review.user_id == user.id, copy_group_key() == group)
        .limit(1)
    )


async def mine(session: AsyncSession, user: User, book_id: uuid.UUID) -> tuple[bool, Review | None]:
    """(may the reader review this title, their review if any)."""
    group = await _group_of(session, book_id)
    return await _borrowed(session, user, group), await _own(session, user, group)


async def save(
    session: AsyncSession, user: User, book_id: uuid.UUID, *, rating: int, text: str
) -> Review:
    group = await _group_of(session, book_id)
    if not await _borrowed(session, user, group):
        raise PermissionDeniedError(
            "Only readers who borrowed this book can review it", code="NOT_BORROWED"
        )
    review = await _own(session, user, group)
    if review is None:
        review = Review(id=uuid.uuid4(), user_id=user.id, book_id=book_id)
        session.add(review)
    review.rating = rating
    review.text = text
    review.status = ReviewStatus.PENDING if text else ReviewStatus.PUBLISHED
    review.moderated_at = None
    await session.commit()
    return review


async def delete_mine(session: AsyncSession, user: User, book_id: uuid.UUID) -> None:
    review = await _own(session, user, await _group_of(session, book_id))
    if review is not None:
        await session.delete(review)
        await session.commit()


@dataclass(frozen=True, slots=True)
class ModerationItem:
    review: Review
    book_title: str
    reader_name: str
    reader_email: str


async def for_moderation(
    session: AsyncSession, status: ReviewStatus, *, page: int, page_size: int
) -> tuple[list[ModerationItem], int]:
    total = await session.scalar(select(func.count(Review.id)).where(Review.status == status))
    rows = (
        await session.execute(
            select(Review, Book.title, User.full_name, User.email)
            .join(Book, Book.id == Review.book_id)
            .join(User, User.id == Review.user_id)
            .where(Review.status == status)
            .order_by(Review.updated_at)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()
    return [ModerationItem(r, title, name, email) for r, title, name, email in rows], int(
        total or 0
    )


async def moderate(session: AsyncSession, review_id: uuid.UUID, status: ReviewStatus) -> Review:
    review = await session.get(Review, review_id)
    if review is None:
        raise review_not_found()
    review.status = status
    review.moderated_at = datetime.now(UTC)
    await session.commit()
    return review


async def delete(session: AsyncSession, review_id: uuid.UUID) -> None:
    review = await session.get(Review, review_id)
    if review is None:
        raise review_not_found()
    await session.delete(review)
    await session.commit()
