from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.conftest import (
    API,
    FRONTEND_ORIGIN,
    ApiUser,
    CreateBook,
    RegisterUser,
    SetBatch,
    fill_cart,
    place_order,
)

ADMIN = f"{API}/admin"
SOME_ID = "00000000-0000-0000-0000-000000000001"

ADMIN_ENDPOINTS = [
    ("GET", f"{ADMIN}/books", None),
    ("GET", f"{ADMIN}/books/stats", None),
    ("POST", f"{ADMIN}/books", {"title": "T", "author": "A", "category": "fiction"}),
    ("GET", f"{ADMIN}/books/{SOME_ID}", None),
    ("PATCH", f"{ADMIN}/books/{SOME_ID}", {"title": "T"}),
    ("DELETE", f"{ADMIN}/books/{SOME_ID}", None),
    ("GET", f"{ADMIN}/users", None),
    ("PATCH", f"{ADMIN}/users/{SOME_ID}", {"role": "admin"}),
    ("GET", f"{ADMIN}/orders", None),
    ("GET", f"{ADMIN}/orders/{SOME_ID}", None),
    ("PATCH", f"{ADMIN}/orders/{SOME_ID}/status", {"status": "confirmed"}),
    ("PATCH", f"{ADMIN}/orders/{SOME_ID}/due-date", {"due_date": "2030-01-01"}),
    ("GET", f"{ADMIN}/settings", None),
    ("PATCH", f"{ADMIN}/settings", {"books_per_batch": 3}),
]


@pytest.mark.parametrize(("method", "url", "body"), ADMIN_ENDPOINTS)
async def test_customer_is_forbidden_on_admin_endpoints(
    customer: ApiUser, method: str, url: str, body: dict[str, object] | None
) -> None:
    response = await customer.client.request(method, url, json=body, headers=customer.headers)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "FORBIDDEN"

    anonymous = await customer.client.request(method, url, json=body)
    assert anonymous.status_code == 401


async def test_admin_has_access(admin: ApiUser) -> None:
    for url in (f"{ADMIN}/books", f"{ADMIN}/users", f"{ADMIN}/orders", f"{ADMIN}/settings"):
        response = await admin.get(url)
        assert response.status_code == 200, (url, response.text)


async def test_role_claim_in_token_is_not_trusted(
    admin: ApiUser, register_user: RegisterUser
) -> None:
    """Demoting a user takes effect immediately even though their token still says 'admin'."""
    second = await register_user()
    promote = await admin.patch(f"{ADMIN}/users/{second.id}", json={"role": "admin"})
    assert promote.status_code == 200
    login = await second.client.post(
        f"{API}/auth/login", json={"email": second.email, "password": second.password}
    )
    second.access_token = login.json()["access_token"]
    assert (await second.get(f"{ADMIN}/users")).status_code == 200

    demote = await admin.patch(f"{ADMIN}/users/{second.id}", json={"role": "customer"})
    assert demote.status_code == 200
    assert (await second.get(f"{ADMIN}/users")).status_code == 403


async def test_book_crud(admin: ApiUser, client: AsyncClient) -> None:
    created = await admin.post(
        f"{ADMIN}/books",
        json={
            "title": "  Neuromancer ",
            "author": "William Gibson",
            "category": "fiction",
            "age_range": "16+",
            "cover_url": "https://images.example.com/n.jpg",
            "image_urls": ["https://images.example.com/n.jpg"],
            "isbn": "978-0441569595",
            "language": "en",
            "publication_year": 1984,
            "description": "Cyberpunk.",
        },
    )
    assert created.status_code == 201, created.text
    book = created.json()
    assert book["title"] == "Neuromancer"
    assert book["status"] == "available"
    book_id = book["id"]

    invalid = await admin.post(
        f"{ADMIN}/books",
        json={"title": "X", "author": "Y", "category": "fiction", "cover_url": "javascript:x"},
    )
    assert invalid.status_code == 422

    patched = await admin.patch(
        f"{ADMIN}/books/{book_id}", json={"status": "available-soon", "isbn": None}
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "available-soon"
    assert patched.json()["isbn"] is None
    assert patched.json()["title"] == "Neuromancer"

    null_title = await admin.patch(f"{ADMIN}/books/{book_id}", json={"title": None})
    assert null_title.status_code == 422

    stats = (await admin.get(f"{ADMIN}/books/stats")).json()
    assert stats == {
        "total": 1,
        "available": 0,
        "available_soon": 1,
        "not_available": 0,
        "reserved": 0,
    }

    deleted = await admin.delete(f"{ADMIN}/books/{book_id}")
    assert deleted.status_code == 204
    assert (await client.get(f"{API}/books/{book_id}")).status_code == 404
    still_there = await admin.get(f"{ADMIN}/books/{book_id}")
    assert still_there.status_code == 200
    assert still_there.json()["is_active"] is False
    listed = await admin.get(f"{ADMIN}/books", params={"include_inactive": "true"})
    assert listed.json()["total"] == 1
    assert (await admin.delete(f"{ADMIN}/books/{book_id}")).status_code == 404


async def test_deleting_a_book_removes_it_from_carts(
    admin: ApiUser, customer: ApiUser, create_book: CreateBook
) -> None:
    book = await create_book()
    await fill_cart(customer, [book])
    assert (await admin.delete(f"{ADMIN}/books/{book}")).status_code == 204
    assert (await customer.get(f"{API}/cart")).json()["items"] == []


async def test_users_list_with_active_loans_and_role_management(
    admin: ApiUser, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    book = await create_book("Borrowed Book")
    await fill_cart(customer, [book])
    order = (await place_order(customer)).json()
    await admin.patch(f"{ADMIN}/orders/{order['id']}/status", json={"status": "confirmed"})

    users = (await admin.get(f"{ADMIN}/users")).json()
    assert users["total"] == 2
    row = next(u for u in users["items"] if u["id"] == customer.id)
    assert row["telegram"] == "@reader"
    assert "password_hash" not in row
    assert [loan["title"] for loan in row["active_loans"]] == ["Borrowed Book"]
    assert row["active_loans"][0]["due_date"] == order["due_date"]

    promoted = await admin.patch(f"{ADMIN}/users/{customer.id}", json={"role": "admin"})
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"
    assert (await customer.get(f"{ADMIN}/users")).status_code == 200

    self_demote = await admin.patch(f"{ADMIN}/users/{admin.id}", json={"role": "customer"})
    assert self_demote.status_code == 409
    assert self_demote.json()["error"]["code"] == "CANNOT_MODIFY_SELF"
    self_disable = await admin.patch(f"{ADMIN}/users/{admin.id}", json={"is_active": False})
    assert self_disable.status_code == 409

    unknown = await admin.patch(f"{ADMIN}/users/{uuid.uuid4()}", json={"role": "admin"})
    assert unknown.status_code == 404
    empty = await admin.patch(f"{ADMIN}/users/{customer.id}", json={})
    assert empty.status_code == 422


async def test_order_status_workflow(
    admin: ApiUser, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    await fill_cart(customer, [await create_book()])
    order_id = (await place_order(customer)).json()["id"]

    listed = await admin.get(f"{ADMIN}/orders", params={"status": "pending"})
    assert [o["id"] for o in listed.json()["items"]] == [order_id]

    skip = await admin.patch(f"{ADMIN}/orders/{order_id}/status", json={"status": "returned"})
    assert skip.status_code == 409
    assert skip.json()["error"]["details"] == {
        "current_status": "pending",
        "requested_status": "returned",
    }

    confirmed = await admin.patch(f"{ADMIN}/orders/{order_id}/status", json={"status": "confirmed"})
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["confirmed_at"] is not None

    cannot_cancel = await admin.patch(
        f"{ADMIN}/orders/{order_id}/status", json={"status": "cancelled"}
    )
    assert cannot_cancel.status_code == 409

    returned = await admin.patch(f"{ADMIN}/orders/{order_id}/status", json={"status": "returned"})
    assert returned.json()["status"] == "returned"
    assert returned.json()["returned_at"] is not None

    bogus = await admin.patch(f"{ADMIN}/orders/{order_id}/status", json={"status": "lost"})
    assert bogus.status_code == 422
    missing = await admin.get(f"{ADMIN}/orders/{uuid.uuid4()}")
    assert missing.status_code == 404


async def test_due_date_update(
    admin: ApiUser, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    await fill_cart(customer, [await create_book()])
    order_id = (await place_order(customer)).json()["id"]

    new_due = (datetime.now(UTC) + timedelta(days=45)).date().isoformat()
    response = await admin.patch(f"{ADMIN}/orders/{order_id}/due-date", json={"due_date": new_due})
    assert response.status_code == 200
    assert response.json()["due_date"] == new_due

    past = await admin.patch(f"{ADMIN}/orders/{order_id}/due-date", json={"due_date": "2000-01-01"})
    assert past.status_code == 400

    await admin.patch(f"{ADMIN}/orders/{order_id}/status", json={"status": "cancelled"})
    closed = await admin.patch(f"{ADMIN}/orders/{order_id}/due-date", json={"due_date": new_due})
    assert closed.status_code == 409


async def test_library_settings(admin: ApiUser, customer: ApiUser) -> None:
    current = (await admin.get(f"{ADMIN}/settings")).json()
    assert current["books_per_batch"] == 5
    assert current["price_per_batch"] == "15.99"

    updated = await admin.patch(
        f"{ADMIN}/settings", json={"books_per_batch": 3, "price_per_batch": 9.5}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["books_per_batch"] == 3
    assert updated.json()["price_per_batch"] == "9.50"

    cart = (await customer.get(f"{API}/cart")).json()
    assert cart["books_per_batch"] == 3

    for invalid in (
        {"books_per_batch": 0},
        {"price_per_batch": "-1"},
        {"price_per_batch": "1.234"},
        {"currency": "usd"},
        {"books_per_batch": None},
    ):
        response = await admin.patch(f"{ADMIN}/settings", json=invalid)
        assert response.status_code == 422, invalid


async def test_error_format_and_health(client: AsyncClient) -> None:
    unknown = await client.get(f"{API}/does-not-exist")
    assert unknown.status_code == 404
    assert unknown.json() == {
        "error": {"code": "NOT_FOUND", "message": "Not Found", "details": None}
    }

    assert (await client.get("/health")).json() == {"status": "ok"}
    assert (await client.get(f"{API}/health")).json() == {"status": "ok", "database": "ok"}


async def test_cors_allows_only_configured_origins(client: AsyncClient) -> None:
    preflight = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    allowed = await client.options(
        f"{API}/auth/login", headers={"Origin": FRONTEND_ORIGIN, **preflight}
    )
    assert allowed.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    assert allowed.headers["access-control-allow-credentials"] == "true"

    denied = await client.options(
        f"{API}/auth/login", headers={"Origin": "https://evil.example", **preflight}
    )
    assert "access-control-allow-origin" not in denied.headers
