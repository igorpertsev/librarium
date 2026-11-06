"""Orders: transactional checkout, status workflow and reservation release.

Reservation invariant: a book copy belongs to at most one order whose status is in
``ACTIVE_ORDER_STATUSES``. It is enforced twice:

1. ``place_order`` locks the copies with ``SELECT ... FOR UPDATE`` (sorted by id, so
   concurrent checkouts cannot deadlock) and re-checks active orders inside the same
   transaction. A second concurrent checkout blocks on the row lock and, once the first one
   commits, sees its order and fails with 409.
2. A partial unique index ``uq_order_items_active_book`` on ``order_items(book_id) WHERE
   reservation_active`` makes PostgreSQL reject a double reservation even if a future code
   path forgets the lock.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, BookUnavailableError, ConflictError, NotFoundError
from app.models import Book, Cart, CartItem, Order, OrderItem, User
from app.models.enums import (
    ACTIVE_ORDER_STATUSES,
    CUSTOMER_CANCELLABLE_STATUSES,
    ORDER_STATUS_TRANSITIONS,
    BookStatus,
    OrderStatus,
)
from app.repositories import orders as orders_repo
from app.repositories.books import reserved_book_ids
from app.services.library_settings import get_library_settings

ACTIVE_BOOK_INDEX = "uq_order_items_active_book"
CENT = Decimal("0.01")


def order_not_found() -> NotFoundError:
    return NotFoundError("Order not found", code="ORDER_NOT_FOUND")


def allocate_batch_price(price_per_batch: Decimal, books_per_batch: int) -> list[Decimal]:
    """Split a batch price into per-book cents that add up exactly (largest remainder)."""
    cents = int((price_per_batch * 100).to_integral_value(rounding=ROUND_HALF_UP))
    base, remainder = divmod(cents, books_per_batch)
    return [
        (Decimal(base + (1 if i < remainder else 0)) / 100).quantize(CENT)
        for i in range(books_per_batch)
    ]


def _today() -> date:
    return datetime.now(UTC).date()


async def place_order(session: AsyncSession, user: User) -> Order:
    """Create an order from the complete batches of the user's cart, in one transaction."""
    # 1. Serialise checkouts of the same cart (double click, two tabs).
    cart = await session.scalar(select(Cart).where(Cart.user_id == user.id).with_for_update())
    items = (
        list(
            (
                await session.scalars(
                    select(CartItem)
                    .where(CartItem.cart_id == cart.id)
                    .order_by(CartItem.added_at, CartItem.id)
                )
            ).all()
        )
        if cart is not None
        else []
    )
    # 2. The cart must not be empty and must contain at least one complete batch.
    if not items:
        raise BadRequestError("Your cart is empty", code="CART_EMPTY")

    library = await get_library_settings(session, lock="share")
    per_batch = library.books_per_batch
    batch_count = len(items) // per_batch
    if batch_count == 0:
        raise BadRequestError(
            f"Add at least {per_batch} books to complete a batch",
            code="INCOMPLETE_BATCH",
            details={"books_per_batch": per_batch, "item_count": len(items)},
        )
    selected = items[: batch_count * per_batch]
    book_ids = [item.book_id for item in selected]

    # 3. Lock the copies (deterministic order prevents deadlocks).
    locked = (
        await session.scalars(
            select(Book).where(Book.id.in_(book_ids)).order_by(Book.id).with_for_update()
        )
    ).all()
    books = {book.id: book for book in locked}

    # 4-6. Re-check availability under the lock. Any active order blocks a copy, including
    # the customer's own: the UI never lets a reserved copy be added again.
    reserved = await reserved_book_ids(session, book_ids)
    unavailable = [
        (book_id, books[book_id].title if book_id in books else "")
        for book_id in book_ids
        if book_id not in books
        or not books[book_id].is_active
        or books[book_id].status is not BookStatus.AVAILABLE
        or book_id in reserved
    ]
    if unavailable:
        # 7-8. Raising aborts the request; the session rolls back everything.
        raise BookUnavailableError(unavailable)

    # 9. Totals are computed here only; nothing price-related is read from the client.
    unit_prices = allocate_batch_price(library.price_per_batch, per_batch)
    order = Order(
        id=uuid.uuid4(),
        user_id=user.id,
        status=OrderStatus.PENDING,
        total_amount=library.price_per_batch * batch_count,
        currency=library.currency,
        books_per_batch=per_batch,
        price_per_batch=library.price_per_batch,
        batch_count=batch_count,
        contact_name=user.full_name,
        contact_email=user.email,
        contact_whatsapp=user.whatsapp,
        contact_telegram=user.telegram,
        contact_instagram=user.instagram,
        contact_phone=user.phone,
        contact_preferred_method=user.preferred_contact_method,
        due_date=_today() + timedelta(days=library.loan_period_days),
    )
    # 10-11. Items keep a snapshot of title, author and price at the time of the order.
    order.items = [
        OrderItem(
            id=uuid.uuid4(),
            book_id=book_id,
            position=index,
            batch_number=index // per_batch + 1,
            title=books[book_id].title,
            author=books[book_id].author,
            isbn=books[book_id].isbn,
            cover_url=books[book_id].cover_url,
            category=books[book_id].category,
            age_range=books[book_id].age_range,
            unit_price=unit_prices[index % per_batch],
            currency=library.currency,
            reservation_active=True,
        )
        for index, book_id in enumerate(book_ids)
    ]
    session.add(order)

    # 12. Remove the ordered books from the cart. Books of an incomplete trailing batch stay.
    await session.execute(delete(CartItem).where(CartItem.id.in_([i.id for i in selected])))

    # Captured now: after a failed flush the ORM objects are expired and unusable.
    requested = [(book_id, books[book_id].title) for book_id in book_ids]
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        if ACTIVE_BOOK_INDEX in str(exc.orig):
            # Only reachable if the row locks above were bypassed; the index still holds.
            raise BookUnavailableError(requested) from exc
        raise

    # 13. Commit: the order, its reservations and the cart change become visible atomically.
    await session.commit()
    return await get_order(session, order.id)


async def get_order(
    session: AsyncSession, order_id: uuid.UUID, *, user_id: uuid.UUID | None = None
) -> Order:
    order = await orders_repo.get_order(session, order_id, user_id=user_id)
    if order is None:
        raise order_not_found()
    return order


async def _apply_status(session: AsyncSession, order: Order, new_status: OrderStatus) -> None:
    now = datetime.now(UTC)
    order.status = new_status
    if new_status is OrderStatus.CONFIRMED:
        order.confirmed_at = now
    elif new_status is OrderStatus.RETURNED:
        order.returned_at = now
    elif new_status is OrderStatus.CANCELLED:
        order.cancelled_at = now
    # Keep the indexed reservation flag in sync with ACTIVE_ORDER_STATUSES.
    await session.execute(
        update(OrderItem)
        .where(OrderItem.order_id == order.id)
        .values(reservation_active=new_status in ACTIVE_ORDER_STATUSES)
    )


def _invalid_transition(current: OrderStatus, target: OrderStatus) -> ConflictError:
    return ConflictError(
        f"Cannot change order status from '{current.value}' to '{target.value}'",
        code="INVALID_STATUS_TRANSITION",
        details={"current_status": current.value, "requested_status": target.value},
    )


async def cancel_own_order(session: AsyncSession, user: User, order_id: uuid.UUID) -> Order:
    order = await orders_repo.lock_order(session, order_id, user_id=user.id)
    if order is None:
        raise order_not_found()
    if order.status not in CUSTOMER_CANCELLABLE_STATUSES:
        raise _invalid_transition(order.status, OrderStatus.CANCELLED)
    await _apply_status(session, order, OrderStatus.CANCELLED)
    await session.commit()
    return await get_order(session, order_id)


async def change_status(
    session: AsyncSession, order_id: uuid.UUID, new_status: OrderStatus
) -> Order:
    order = await orders_repo.lock_order(session, order_id)
    if order is None:
        raise order_not_found()
    if order.status is not new_status:
        if new_status not in ORDER_STATUS_TRANSITIONS[order.status]:
            raise _invalid_transition(order.status, new_status)
        await _apply_status(session, order, new_status)
        await session.commit()
    return await get_order(session, order_id)


async def change_due_date(session: AsyncSession, order_id: uuid.UUID, due_date: date) -> Order:
    order = await orders_repo.lock_order(session, order_id)
    if order is None:
        raise order_not_found()
    if order.status not in ACTIVE_ORDER_STATUSES:
        raise ConflictError(
            "The due date can only be changed for active orders", code="ORDER_NOT_ACTIVE"
        )
    if due_date < order.created_at.date():
        raise BadRequestError(
            "The due date cannot be before the order date", code="INVALID_DUE_DATE"
        )
    order.due_date = due_date
    await session.commit()
    return await get_order(session, order_id)
