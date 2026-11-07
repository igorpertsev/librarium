from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from app.services.audit import details_from_body
from tests.conftest import (
    API,
    PASSWORD,
    ApiUser,
    CreateBook,
    RegisterUser,
    SetBatch,
    fill_cart,
    place_order,
)

AUDIT = f"{API}/admin/audit"


async def _librarian(admin: ApiUser, register_user: RegisterUser) -> ApiUser:
    staff = await register_user(email="desk@example.com", full_name="Desk Staff")
    promoted = await admin.patch(f"{API}/admin/users/{staff.id}", json={"role": "librarian"})
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["role"] == "librarian"
    return staff


async def test_librarians_run_the_desk_but_not_the_library(
    admin: ApiUser,
    register_user: RegisterUser,
    customer: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
    client: AsyncClient,
) -> None:
    staff = await _librarian(admin, register_user)
    await set_batch(1)
    created = await staff.post(
        f"{API}/admin/books", json={"title": "Desk book", "author": "A", "category": "fiction"}
    )
    assert created.status_code == 201, created.text
    await fill_cart(customer, [await create_book("Dune")])
    order = (await place_order(customer)).json()
    confirmed = await staff.patch(
        f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"}
    )
    assert confirmed.status_code == 200
    assert (await staff.get(f"{API}/admin/users")).status_code == 200

    # Administrators only.
    for method, url, body in (
        ("PATCH", f"{API}/admin/settings", {"max_renewals": 3}),
        ("PATCH", f"{API}/admin/users/{customer.id}", {"role": "admin"}),
        ("POST", f"{API}/admin/pickup-points", {"name": "X", "address": "Y", "hours": []}),
        ("GET", AUDIT, None),
    ):
        refused = await staff.client.request(method, url, headers=staff.headers, json=body)
        assert refused.status_code == 403, (method, url)
    assert (await customer.get(f"{API}/admin/books")).status_code == 403

    # Staff accounts are not deleted by their owners.
    own = await client.request(
        "DELETE", f"{API}/users/me", headers=staff.headers, json={"password": PASSWORD}
    )
    assert own.json()["error"]["code"] == "ADMIN_ACCOUNT"


async def test_changes_are_logged_with_who_what_and_which_record(
    admin: ApiUser,
    register_user: RegisterUser,
    customer: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    staff = await _librarian(admin, register_user)
    await set_batch(1)
    dune = await create_book("Dune")
    await fill_cart(customer, [dune])
    order = (await place_order(customer)).json()
    await staff.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})
    await staff.patch(f"{API}/admin/books/{dune}", json={"status": "not-available"})
    # A change that fails is not logged.
    refused = await staff.patch(
        f"{API}/admin/orders/{order['id']}/status", json={"status": "pending"}
    )
    assert refused.status_code == 409
    await staff.get(f"{API}/admin/books")  # reading is not logged either

    log = (await admin.get(AUDIT)).json()
    events: list[dict[str, Any]] = log["items"]
    assert [(e["actor_email"], e["action"]) for e in events] == [
        ("desk@example.com", "admin_update_book"),
        ("desk@example.com", "admin_change_order_status"),
        ("librarian@example.com", "admin_update_user"),
    ]
    book_event, order_event, role_event = events
    assert (book_event["entity_type"], book_event["entity_label"]) == ("books", "Dune")
    assert book_event["details"] == {"status": "not-available"}
    assert order_event["entity_label"] == f"#{order['number']}"
    assert role_event["entity_label"] == "desk@example.com"
    assert role_event["details"] == {"role": "librarian"}
    mine = (await admin.get(AUDIT, params={"actor_id": staff.id})).json()
    assert mine["total"] == 2


def test_secrets_are_redacted_and_long_values_shortened() -> None:
    details = details_from_body(b'{"password": "hunter22", "csv": "' + b"x" * 1000 + b'"}')
    assert details["password"] == "[redacted]"
    assert details["csv"].endswith("(1000 characters)")
    assert details_from_body(b"not json") == {"body": "8 bytes"}
