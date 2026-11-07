from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from sqlalchemy import update

from app.models import Order
from app.models.enums import BookCategory
from tests.conftest import API, ApiUser, CreateBook, SetBatch, fill_cart, place_order


async def _order(user: ApiUser, create_book: CreateBook, *titles: str) -> dict[str, Any]:
    await fill_cart(user, [await create_book(title) for title in titles])
    response = await place_order(user)
    assert response.status_code == 201, response.text
    order: dict[str, Any] = response.json()
    return order


async def test_summary_counts_the_period(
    app: FastAPI,
    customer: ApiUser,
    other_customer: ApiUser,
    admin: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(2, "10.00")
    first = await _order(customer, create_book, "Dune", "Emma")
    second = await _order(other_customer, create_book, "Dune", "Ulysses")  # another copy
    await _order(customer, create_book, "Pending 1", "Pending 2")
    for order in (first, second):
        await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})
    await admin.patch(f"{API}/admin/orders/{first['id']}/status", json={"status": "returned"})
    async with app.state.db.sessionmaker() as session:  # make the second loan overdue
        await session.execute(
            update(Order)
            .where(Order.id == uuid.UUID(second["id"]))
            .values(due_date=datetime.now(UTC).date() - timedelta(days=1))
        )
        await session.commit()

    body = (await admin.get(f"{API}/admin/reports/summary")).json()
    assert body["orders_placed"] == 3
    assert body["orders_confirmed"] == 2
    assert body["books_lent"] == 4
    assert body["books_returned"] == 2
    assert body["active_readers"] == 2
    assert body["overdue_now"] == 1
    assert body["revenue"] == "20.00"
    assert body["currency"] == "USD"
    assert body["top_books"][0] == {"title": "Dune", "author": "Ann Author", "loans": 2}

    last_year = datetime.now(UTC).date() - timedelta(days=365)
    old = (
        await admin.get(
            f"{API}/admin/reports/summary",
            params={"date_from": str(last_year), "date_to": str(last_year + timedelta(days=1))},
        )
    ).json()
    assert old["orders_placed"] == 0
    assert old["top_books"] == []


async def test_orders_csv_export(
    customer: ApiUser, admin: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(1)
    await _order(customer, create_book, "=HYPERLINK(evil)")
    response = await admin.get(f"{API}/admin/reports/orders.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text.lstrip("﻿"))))
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["email"] == customer.email
    assert rows[0]["titles"] == "'=HYPERLINK(evil)"  # no formula injection


async def test_invalid_periods_and_access(admin: ApiUser, customer: ApiUser) -> None:
    response = await admin.get(
        f"{API}/admin/reports/summary", params={"date_from": "2026-02-01", "date_to": "2026-01-01"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PERIOD"
    response = await admin.get(
        f"{API}/admin/reports/summary", params={"date_from": "2020-01-01", "date_to": "2026-01-01"}
    )
    assert response.status_code == 400
    assert (await customer.get(f"{API}/admin/reports/summary")).status_code == 403


async def test_figures_by_month_in_the_library_time_zone(
    app: FastAPI,
    customer: ApiUser,
    other_customer: ApiUser,
    admin: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await admin.patch(f"{API}/admin/settings", json={"timezone": "Europe/Amsterdam"})
    zone = ZoneInfo("Europe/Amsterdam")
    await set_batch(2)
    earlier = await _order(customer, create_book, "Dune", "Emma")
    later = await _order(other_customer, create_book, "Cosmos", "Ulysses")
    for order in (earlier, later):
        await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})
    await admin.patch(f"{API}/admin/orders/{later['id']}/status", json={"status": "returned"})

    this_month = datetime.now(zone).date().replace(day=1)
    last_month = (this_month - timedelta(days=1)).replace(day=1)
    # Half past midnight on the 1st in Amsterdam is still the previous month in UTC: it counts
    # for this month.
    just_in = datetime.combine(this_month, time(0, 30), tzinfo=zone)
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(Order)
            .where(Order.id == uuid.UUID(earlier["id"]))
            .values(confirmed_at=datetime.combine(last_month, time(12), tzinfo=zone))
        )
        await session.execute(
            update(Order).where(Order.id == uuid.UUID(later["id"])).values(confirmed_at=just_in)
        )
        await session.commit()
    assert just_in.astimezone(UTC).date() < this_month

    months = (await admin.get(f"{API}/admin/reports/monthly", params={"months": 3})).json()
    assert [m["month"] for m in months][-2:] == [f"{last_month:%Y-%m}", f"{this_month:%Y-%m}"]
    previous, current = months[-2], months[-1]
    assert (previous["loans"], previous["active_readers"], previous["returns"]) == (2, 1, 0)
    assert (current["loans"], current["active_readers"], current["returns"]) == (2, 1, 2)
    assert current["new_readers"] == 2  # the two readers; staff accounts do not count
    assert len((await admin.get(f"{API}/admin/reports/monthly")).json()) == 12
    too_many = await admin.get(f"{API}/admin/reports/monthly", params={"months": 37})
    assert too_many.status_code == 422

    exported = await admin.get(f"{API}/admin/reports/monthly.csv", params={"months": 3})
    rows = list(csv.reader(io.StringIO(exported.text.lstrip("﻿"))))
    assert rows[0] == ["month", "loans", "returns", "active_readers", "new_readers"]
    assert rows[-1] == [f"{this_month:%Y-%m}", "2", "2", "1", "2"]
    assert len(rows) == 4


async def test_loans_by_category(
    admin: ApiUser, customer: ApiUser, create_book: CreateBook, set_batch: SetBatch
) -> None:
    await set_batch(3)
    await fill_cart(
        customer,
        [
            await create_book("Dune"),
            await create_book("Emma"),
            await create_book("Cosmos", category=BookCategory.SCIENCE),
        ],
    )
    order = (await place_order(customer)).json()
    await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})
    found = (await admin.get(f"{API}/admin/reports/categories")).json()
    assert found == [{"category": "fiction", "loans": 2}, {"category": "science", "loans": 1}]
