"""Server-side cart. The cart is not a reservation: books are only reserved by orders."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from app.core.exceptions import BookUnavailableError
from app.models import Book, Cart, CartItem, User
from app.models.enums import BookStatus
from app.repositories.books import active_reservation_due_date, get_book_with_reservation
from app.schemas.book import BookRead
from app.schemas.cart import CartItemRead, CartRead
from app.services import holds
from app.services.books import book_not_found
from app.services.library_settings import get_library_settings


async def _get_cart_id(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    return await session.scalar(select(Cart.id).where(Cart.user_id == user_id))


async def _get_or_create_cart_id(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    await session.execute(
        pg_insert(Cart)
        .values(id=uuid.uuid4(), user_id=user_id)
        .on_conflict_do_nothing(index_elements=[Cart.user_id])
    )
    cart_id = await _get_cart_id(session, user_id)
    assert cart_id is not None  # noqa: S101 - just inserted or already present
    return cart_id


async def build_cart(session: AsyncSession, user_id: uuid.UUID) -> CartRead:
    settings = await get_library_settings(session)
    per_batch = settings.books_per_batch

    rows: list[tuple[CartItem, date | None]] = []
    cart_id = await _get_cart_id(session, user_id)
    if cart_id is not None:
        result = await session.execute(
            select(CartItem, active_reservation_due_date(Book.id).label("reserved_until"))
            .join(CartItem.book)
            .options(contains_eager(CartItem.book))
            .where(CartItem.cart_id == cart_id)
            .order_by(CartItem.added_at, CartItem.id)
        )
        rows = [(row[0], row[1]) for row in result.all()]

    complete_batches = len(rows) // per_batch
    orderable = complete_batches * per_batch
    items = [
        CartItemRead(
            book=BookRead.from_book(item.book, reserved_until=reserved_until),
            added_at=item.added_at,
            batch_number=index // per_batch + 1,
            in_complete_batch=index < orderable,
        )
        for index, (item, reserved_until) in enumerate(rows)
    ]
    return CartRead(
        items=items,
        item_count=len(items),
        books_per_batch=per_batch,
        price_per_batch=settings.price_per_batch,
        currency=settings.currency,
        complete_batches=complete_batches,
        orderable_item_count=orderable,
        total_amount=settings.price_per_batch * complete_batches,
        has_unavailable_items=any(not item.book.is_available for item in items),
    )


async def add_item(session: AsyncSession, user: User, book_id: uuid.UUID) -> CartRead:
    found = await get_book_with_reservation(session, book_id)
    if found is None or not found[0].is_active:
        raise book_not_found()
    book, reserved_until = found
    if book.status is not BookStatus.AVAILABLE:
        raise BookUnavailableError(
            [(book.id, book.title)], "This book is not available for borrowing"
        )
    # A copy held for this reader (see app.services.holds) is theirs to take.
    if reserved_until is not None and not await holds.held_for(
        session, book.id, user.id, datetime.now(UTC)
    ):
        raise BookUnavailableError(
            [(book.id, book.title)], "This book is already reserved by another order"
        )

    cart_id = await _get_or_create_cart_id(session, user.id)
    # Re-adding the same book is a no-op thanks to UNIQUE (cart_id, book_id).
    await session.execute(
        pg_insert(CartItem)
        .values(id=uuid.uuid4(), cart_id=cart_id, book_id=book.id)
        .on_conflict_do_nothing(index_elements=[CartItem.cart_id, CartItem.book_id])
    )
    await session.commit()
    return await build_cart(session, user.id)


async def remove_item(session: AsyncSession, user: User, book_id: uuid.UUID) -> CartRead:
    cart_id = await _get_cart_id(session, user.id)
    if cart_id is not None:
        await session.execute(
            delete(CartItem).where(CartItem.cart_id == cart_id, CartItem.book_id == book_id)
        )
        await session.commit()
    return await build_cart(session, user.id)


async def clear(session: AsyncSession, user: User) -> CartRead:
    cart_id = await _get_cart_id(session, user.id)
    if cart_id is not None:
        await session.execute(delete(CartItem).where(CartItem.cart_id == cart_id))
        await session.commit()
    return await build_cart(session, user.id)
