from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from app.models import PickupPoint
from app.services.notifications import deliver_pending
from app.services.pickup import slot_starts
from tests.conftest import API, ApiUser, CreateBook, SetBatch, fill_cart, place_order
from tests.test_holds import FakeSender

WEEKDAYS = [{"weekday": day, "opens": "09:00", "closes": "21:00"} for day in range(7)]


def _point(hours: list[dict[str, Any]], minutes: int = 60) -> PickupPoint:
    return PickupPoint(name="Main", address="1 Road", hours=hours, slot_minutes=minutes)


def test_slots_follow_opening_hours_in_the_library_time_zone() -> None:
    point = _point([{"weekday": 0, "opens": time(10), "closes": time(12)}])
    zone = ZoneInfo("Europe/Moscow")  # UTC+3
    sunday_noon = datetime(2026, 11, 8, 12, tzinfo=UTC)
    starts = list(slot_starts(point, zone, sunday_noon))
    # Mondays 9 and 16 November (two weeks ahead), 10:00 and 11:00 in Moscow.
    assert starts == [
        datetime(2026, 11, 9, 7, tzinfo=UTC),
        datetime(2026, 11, 9, 8, tzinfo=UTC),
        datetime(2026, 11, 16, 7, tzinfo=UTC),
        datetime(2026, 11, 16, 8, tzinfo=UTC),
    ]
    # Less than an hour's notice: the 10:00 slot is gone at 09:30.
    monday_morning = datetime(2026, 11, 9, 6, 30, tzinfo=UTC)
    assert next(slot_starts(point, zone, monday_morning)) == datetime(2026, 11, 9, 8, tzinfo=UTC)


async def _create_point(admin: ApiUser, **extra: Any) -> dict[str, Any]:
    body = {"name": "Main hall", "address": "1 Library Road", "hours": WEEKDAYS, **extra}
    response = await admin.post(f"{API}/admin/pickup-points", json=body)
    assert response.status_code == 201, response.text
    point: dict[str, Any] = response.json()
    return point


async def _order(user: ApiUser, body: dict[str, Any] | None = None) -> Any:
    return await user.post(f"{API}/orders", json=body) if body else await place_order(user)


async def test_readers_pick_a_point_and_a_slot_that_is_not_full(
    app: FastAPI,
    admin: ApiUser,
    customer: ApiUser,
    other_customer: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    await admin.patch(f"{API}/admin/settings", json={"timezone": "Europe/Moscow"})
    point = await _create_point(admin, slot_capacity=1, notes="Ring the bell")
    assert point["hours"][0] == {"weekday": 0, "opens": "09:00:00", "closes": "21:00:00"}

    listed = (await customer.get(f"{API}/library/pickup-points")).json()
    assert [p["name"] for p in listed] == ["Main hall"]
    slots = (await customer.get(f"{API}/library/pickup-points/{point['id']}/slots")).json()
    first = slots[0]
    assert first["left"] == 1

    await fill_cart(customer, [await create_book("Dune")])
    missing = await _order(customer)
    assert (missing.status_code, missing.json()["error"]["code"]) == (400, "PICKUP_REQUIRED")
    odd = await _order(
        customer, {"pickup_point_id": point["id"], "pickup_at": "2020-01-01T10:00:00Z"}
    )
    assert (odd.status_code, odd.json()["error"]["code"]) == (400, "INVALID_PICKUP_SLOT")

    choice = {"pickup_point_id": point["id"], "pickup_at": first["starts_at"]}
    placed = await _order(customer, choice)
    assert placed.status_code == 201, placed.text
    order = placed.json()
    assert order["pickup_point"]["name"] == "Main hall"
    assert datetime.fromisoformat(order["pickup_at"]) == datetime.fromisoformat(first["starts_at"])
    # The "order received" email says where and when, in the library's time zone.
    send = FakeSender()
    async with app.state.db.sessionmaker() as session:
        await deliver_pending(session, app.state.settings, send)
    local = datetime.fromisoformat(first["starts_at"]).astimezone(ZoneInfo("Europe/Moscow"))
    (message,) = send.messages
    assert "Main hall, 1 Library Road" in message.get_content()
    assert f"{local:%H:%M}" in message.get_content()

    await fill_cart(other_customer, [await create_book("Emma")])
    full = await _order(other_customer, choice)
    assert (full.status_code, full.json()["error"]["code"]) == (409, "PICKUP_SLOT_FULL")
    slots = (await customer.get(f"{API}/library/pickup-points/{point['id']}/slots")).json()
    assert slots[0]["left"] == 0

    # A cancelled order frees its place.
    await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "cancelled"})
    assert (await _order(other_customer, choice)).status_code == 201


async def test_points_in_use_are_switched_off_not_deleted(
    admin: ApiUser, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    point = await _create_point(admin)
    unused = await _create_point(admin, name="Annex")
    slot = (await customer.get(f"{API}/library/pickup-points/{point['id']}/slots")).json()[0]
    await fill_cart(customer, [await create_book("Dune")])
    choice = {"pickup_point_id": point["id"], "pickup_at": slot["starts_at"]}
    assert (await _order(customer, choice)).status_code == 201

    in_use = await admin.delete(f"{API}/admin/pickup-points/{point['id']}")
    assert (in_use.status_code, in_use.json()["error"]["code"]) == (409, "PICKUP_POINT_IN_USE")
    assert (await admin.delete(f"{API}/admin/pickup-points/{unused['id']}")).status_code == 204
    off = await admin.patch(f"{API}/admin/pickup-points/{point['id']}", json={"active": False})
    assert off.json()["active"] is False
    assert (await customer.get(f"{API}/library/pickup-points")).json() == []
    gone = await customer.get(f"{API}/library/pickup-points/{point['id']}/slots")
    assert gone.status_code == 404

    # Without active points an order needs none.
    await fill_cart(customer, [await create_book("Emma")])
    assert (await _order(customer)).status_code == 201
    listed = (await admin.get(f"{API}/admin/pickup-points")).json()
    assert [p["name"] for p in listed] == ["Main hall"]


async def test_hours_and_time_zone_are_validated(admin: ApiUser) -> None:
    backwards = await admin.post(
        f"{API}/admin/pickup-points",
        json={
            "name": "Main",
            "address": "1 Road",
            "hours": [{"weekday": 0, "opens": "18:00", "closes": "10:00"}],
        },
    )
    assert backwards.status_code == 422
    zone = await admin.patch(f"{API}/admin/settings", json={"timezone": "Mars/Olympus"})
    assert zone.status_code == 422
