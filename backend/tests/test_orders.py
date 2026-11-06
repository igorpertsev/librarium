from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import Select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book, LibrarySettings, Order, OrderItem
from app.models.enums import BookCategory, OrderStatus
from app.repositories.books import reserved_book_ids
from app.services import orders as orders_service
from app.services.library_settings import get_library_settings
from app.services.orders import allocate_batch_price
from tests.conftest import (
    API,
    ApiUser,
    CreateBook,
    RegisterUser,
    SetBatch,
    fill_cart,
    place_order,
)

ORDERS = f"{API}/orders"


async def _set_status(admin: ApiUser, order_id: str, status: str) -> int:
    response = await admin.patch(f"{API}/admin/orders/{order_id}/status", json={"status": status})
    return response.status_code


async def test_place_order_from_cart(
    customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(2, "10.00")
    books = [await create_book(f"Book {i}") for i in range(2)]
    await fill_cart(customer, books)

    response = await place_order(customer)
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["status"] == "pending"
    assert order["user_id"] == customer.id
    assert order["total_amount"] == "10.00"
    assert order["currency"] == "USD"
    assert order["batch_count"] == 1
    assert [i["book_id"] for i in order["items"]] == books
    assert [i["unit_price"] for i in order["items"]] == ["5.00", "5.00"]
    assert order["contact_name"] == "Charlie Customer"
    assert order["contact_telegram"] == "@reader"
    assert order["contact_preferred_method"] == "telegram"
    expected_due = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
    assert order["due_date"] == expected_due

    # Cart is emptied (it contained exactly one complete batch).
    cart = await customer.get(f"{API}/cart")
    assert cart.json()["items"] == []

    listed = await customer.get(ORDERS)
    assert listed.json()["total"] == 1
    single = await customer.get(f"{ORDERS}/{order['id']}")
    assert single.status_code == 200
    assert single.json()["id"] == order["id"]


async def test_empty_cart_and_incomplete_batch(customer: ApiUser, create_book: CreateBook) -> None:
    empty = await place_order(customer)
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "CART_EMPTY"

    await fill_cart(customer, [await create_book() for _ in range(3)])  # batch size is 5
    incomplete = await place_order(customer)
    assert incomplete.status_code == 400
    error = incomplete.json()["error"]
    assert error["code"] == "INCOMPLETE_BATCH"
    assert error["details"] == {"books_per_batch": 5, "item_count": 3}


async def test_total_is_computed_by_server_and_leftovers_stay_in_cart(
    customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(5, "15.99")
    books = [await create_book() for _ in range(11)]
    await fill_cart(customer, books)

    # Anything the client sends is ignored: the endpoint has no body.
    response = await customer.post(ORDERS, json={"total_amount": "0.01", "price_per_batch": 0})
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["batch_count"] == 2
    assert order["total_amount"] == "31.98"
    prices = [Decimal(i["unit_price"]) for i in order["items"]]
    assert sum(prices) == Decimal("31.98")
    assert [i["batch_number"] for i in order["items"]] == [1] * 5 + [2] * 5
    assert [i["book_id"] for i in order["items"]] == books[:10]

    cart = (await customer.get(f"{API}/cart")).json()
    assert [i["book"]["id"] for i in cart["items"]] == books[10:]


def test_allocate_batch_price_sums_exactly() -> None:
    assert allocate_batch_price(Decimal("15.99"), 5) == [Decimal("3.20")] * 4 + [Decimal("3.19")]
    for price, n in [("10.00", 3), ("0.01", 4), ("99.99", 7), ("0.00", 2)]:
        parts = allocate_batch_price(Decimal(price), n)
        assert len(parts) == n
        assert sum(parts) == Decimal(price)


async def test_order_items_keep_a_snapshot(
    customer: ApiUser, admin: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1, "4.50")
    book = await create_book("Original Title", author="Original Author")
    await fill_cart(customer, [book])
    order = (await place_order(customer)).json()

    edited = await admin.patch(
        f"{API}/admin/books/{book}", json={"title": "New Title", "author": "New Author"}
    )
    assert edited.status_code == 200
    changed_price = await admin.patch(f"{API}/admin/settings", json={"price_per_batch": "9.99"})
    assert changed_price.status_code == 200

    item = (await customer.get(f"{ORDERS}/{order['id']}")).json()["items"][0]
    assert item["title"] == "Original Title"
    assert item["author"] == "Original Author"
    assert item["unit_price"] == "4.50"
    assert item["book"]["title"] == "New Title"  # current catalogue data, for display
    refreshed = (await customer.get(f"{ORDERS}/{order['id']}")).json()
    assert refreshed["total_amount"] == "4.50"


async def test_active_order_blocks_book_and_cancel_releases_it(
    customer: ApiUser, other_customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    book = await create_book()
    await fill_cart(customer, [book])
    order = (await place_order(customer)).json()

    blocked = await other_customer.post(f"{API}/cart/items", json={"book_id": book})
    assert blocked.status_code == 409

    cancelled = await customer.post(f"{ORDERS}/{order['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["cancelled_at"] is not None

    await fill_cart(other_customer, [book])
    assert (await place_order(other_customer)).status_code == 201

    again = await customer.post(f"{ORDERS}/{order['id']}/cancel")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


async def test_customer_cannot_cancel_confirmed_order(
    customer: ApiUser, admin: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    await fill_cart(customer, [await create_book()])
    order = (await place_order(customer)).json()
    assert await _set_status(admin, order["id"], "confirmed") == 200

    response = await customer.post(f"{ORDERS}/{order['id']}/cancel")
    assert response.status_code == 409


async def test_returned_and_cancelled_orders_do_not_block(
    customer: ApiUser,
    other_customer: ApiUser,
    admin: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    returned_book, cancelled_book = await create_book("Returned"), await create_book("Cancelled")

    await fill_cart(customer, [returned_book])
    first = (await place_order(customer)).json()
    assert await _set_status(admin, first["id"], "confirmed") == 200
    assert await _set_status(admin, first["id"], "returned") == 200

    await fill_cart(customer, [cancelled_book])
    second = (await place_order(customer)).json()
    assert await _set_status(admin, second["id"], "cancelled") == 200

    for book in (returned_book, cancelled_book):
        detail = await other_customer.get(f"{API}/books/{book}")
        assert detail.json()["is_reserved"] is False
        await fill_cart(other_customer, [book])
        assert (await place_order(other_customer)).status_code == 201


async def test_checkout_fails_atomically_when_a_book_became_unavailable(
    app: FastAPI,
    customer: ApiUser,
    other_customer: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(2)
    shared, mine = await create_book("Shared"), await create_book("Mine")
    await fill_cart(customer, [shared, mine])
    await fill_cart(other_customer, [shared, await create_book()])
    assert (await place_order(other_customer)).status_code == 201

    conflict = await place_order(customer)
    assert conflict.status_code == 409
    error = conflict.json()["error"]
    assert error["code"] == "BOOK_UNAVAILABLE"
    assert error["details"]["book_ids"] == [shared]

    # Nothing was created and the cart is untouched.
    assert (await customer.get(ORDERS)).json()["total"] == 0
    cart = (await customer.get(f"{API}/cart")).json()
    assert {i["book"]["id"] for i in cart["items"]} == {shared, mine}
    assert cart["has_unavailable_items"] is True


async def test_inactive_book_cannot_be_ordered(
    app: FastAPI, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    book = await create_book()
    await fill_cart(customer, [book])
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(Book).where(Book.id == uuid.UUID(book)).values(is_active=False)
        )
        await session.commit()

    response = await place_order(customer)
    assert response.status_code == 409
    assert response.json()["error"]["details"]["book_ids"] == [book]


async def test_user_cannot_read_or_cancel_someone_elses_order(
    customer: ApiUser, other_customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    await fill_cart(customer, [await create_book()])
    order = (await place_order(customer)).json()

    read = await other_customer.get(f"{ORDERS}/{order['id']}")
    assert read.status_code == 404
    assert read.json()["error"]["code"] == "ORDER_NOT_FOUND"
    cancel = await other_customer.post(f"{ORDERS}/{order['id']}/cancel")
    assert cancel.status_code == 404
    assert (await other_customer.get(ORDERS)).json()["total"] == 0


@dataclass
class CheckoutProbe:
    reserved_checks: list[set[uuid.UUID]] = field(default_factory=list)


@pytest.fixture
def synchronized_checkouts(monkeypatch: pytest.MonkeyPatch) -> CheckoutProbe:
    """Hold two checkouts at a barrier right before they lock the books.

    Without it the first request usually finishes before the second one starts its checks,
    and the test would pass even without any locking. With it both transactions are inside
    the critical section at the same time.
    """
    probe = CheckoutProbe()
    barrier = asyncio.Barrier(2)

    async def settings_then_wait(session: AsyncSession, **kwargs: Any) -> LibrarySettings:
        result = await get_library_settings(session, **kwargs)
        async with asyncio.timeout(5):
            await barrier.wait()
        return result

    async def recording_reserved(session: AsyncSession, ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
        result = await reserved_book_ids(session, ids)
        probe.reserved_checks.append(result)
        return result

    monkeypatch.setattr(orders_service, "get_library_settings", settings_then_wait)
    monkeypatch.setattr(orders_service, "reserved_book_ids", recording_reserved)
    return probe


@pytest.mark.parametrize("round_", range(5))
async def test_concurrent_orders_for_the_same_book_only_one_succeeds(
    round_: int,
    register_user: RegisterUser,
    create_book: CreateBook,
    set_batch: SetBatch,
    synchronized_checkouts: CheckoutProbe,
) -> None:
    await set_batch(2)
    x, y = await create_book("X"), await create_book("Y")
    alice, bob = await register_user(), await register_user()
    # Opposite insertion order: the sorted FOR UPDATE locking must not deadlock.
    await fill_cart(alice, [x, y])
    await fill_cart(bob, [y, x])

    responses = await asyncio.gather(place_order(alice), place_order(bob))
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201, 409], [r.text for r in responses]
    loser = next(r for r in responses if r.status_code == 409)
    assert loser.json()["error"]["code"] == "BOOK_UNAVAILABLE"
    assert set(loser.json()["error"]["details"]["book_ids"]) == {x, y}
    # The loser waited on the row lock and then saw the winner's reservation.
    assert sorted(len(found) for found in synchronized_checkouts.reserved_checks) == [0, 2]


async def test_partial_unique_index_stops_the_race_even_without_row_locks(
    monkeypatch: pytest.MonkeyPatch,
    register_user: RegisterUser,
    create_book: CreateBook,
    set_batch: SetBatch,
    synchronized_checkouts: CheckoutProbe,
) -> None:
    """Defence in depth: simulate a code path that forgot SELECT ... FOR UPDATE."""
    monkeypatch.setattr(Select, "with_for_update", lambda self, **_: self)
    await set_batch(1)
    book = await create_book()
    alice, bob = await register_user(), await register_user()
    await fill_cart(alice, [book])
    await fill_cart(bob, [book])

    responses = await asyncio.gather(place_order(alice), place_order(bob))
    assert sorted(r.status_code for r in responses) == [201, 409], [r.text for r in responses]
    loser = next(r for r in responses if r.status_code == 409)
    assert loser.json()["error"]["details"]["book_ids"] == [book]
    # Both passed the availability check: only the database index stopped the second one.
    assert [len(found) for found in synchronized_checkouts.reserved_checks] == [0, 0]


async def test_concurrent_double_submit_by_same_user_creates_one_order(
    customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    await fill_cart(customer, [await create_book()])
    responses = await asyncio.gather(*(place_order(customer) for _ in range(4)))
    assert sorted(r.status_code for r in responses).count(201) == 1
    assert (await customer.get(ORDERS)).json()["total"] == 1


async def test_database_rejects_two_active_reservations_of_one_copy(
    app: FastAPI, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    """The partial unique index is the last line of defence, independent of the service."""
    await set_batch(1)
    book = await create_book()
    await fill_cart(customer, [book])
    order = (await place_order(customer)).json()

    async with app.state.db.sessionmaker() as session:
        duplicate = Order(
            id=uuid.uuid4(),
            user_id=uuid.UUID(customer.id),
            status=OrderStatus.PENDING,
            total_amount=Decimal("1.00"),
            currency="USD",
            books_per_batch=1,
            price_per_batch=Decimal("1.00"),
            batch_count=1,
            contact_name="x",
            contact_email="x@example.com",
            due_date=datetime.now(UTC).date(),
        )
        duplicate.items = [
            OrderItem(
                id=uuid.uuid4(),
                book_id=uuid.UUID(book),
                position=0,
                batch_number=1,
                title="x",
                author="x",
                category=BookCategory.FICTION,
                age_range="",
                unit_price=Decimal("1.00"),
                currency="USD",
            )
        ]
        session.add(duplicate)
        with pytest.raises(IntegrityError, match="uq_order_items_active_book"):
            await session.commit()

    assert order["status"] == "pending"
