"""Reading challenges: set by the library, joined by readers and children, progress from logs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.enums import BookCategory
from tests.conftest import API, ApiUser, CreateBook

ADMIN = f"{API}/admin/challenges"
MINE = f"{API}/challenges"
LOG = f"{API}/users/me/reading-log"
KIDS = f"{API}/users/me/children"


def _day(offset: int) -> str:
    return (datetime.now(UTC).date() + timedelta(days=offset)).isoformat()


async def _create(admin: ApiUser, **values: Any) -> dict[str, Any]:
    body = {
        "name_en": "Summer of fiction",
        "name_ru": "Лето художественной литературы",
        "starts_on": _day(-5),
        "ends_on": _day(30),
        "goal": 2,
        **values,
    }
    response = await admin.post(ADMIN, json=body)
    assert response.status_code == 201, response.text
    made: dict[str, Any] = response.json()
    return made


async def _read(reader: ApiUser, book_id: str, offset: int = 0, child: str | None = None) -> None:
    params = {"child": child} if child else None
    response = await reader.put(
        f"{LOG}/{book_id}", json={"finished_on": _day(offset)}, params=params
    )
    assert response.status_code in (200, 204), response.text


async def _mine(reader: ApiUser, challenge_id: str) -> list[dict[str, Any]]:
    current = (await reader.get(MINE)).json()
    found = next(c for c in current if c["id"] == challenge_id)
    mine: list[dict[str, Any]] = found["mine"]
    return mine


async def test_the_library_sets_challenges(admin: ApiUser, customer: ApiUser) -> None:
    backwards = await admin.post(
        ADMIN, json={"name_en": "X", "starts_on": _day(5), "ends_on": _day(1), "goal": 3}
    )
    assert backwards.status_code == 422
    assert (await customer.post(ADMIN, json={"name_en": "X"})).status_code == 403

    made = await _create(admin, category="fiction")
    assert (made["participants"], made["completed"], made["mine"]) == (0, 0, [])
    changed = await admin.patch(f"{ADMIN}/{made['id']}", json={"goal": 3, "name_ru": None})
    assert (changed.json()["goal"], changed.json()["name_ru"]) == (3, None)
    wrong = await admin.patch(f"{ADMIN}/{made['id']}", json={"ends_on": _day(-10)})
    assert wrong.json()["error"]["code"] == "INVALID_DATES"

    over = await _create(admin, starts_on=_day(-30), ends_on=_day(-1))
    listed = [c["id"] for c in (await customer.get(MINE)).json()]
    assert listed == [made["id"]]  # the one that is over is not offered any more
    late = await customer.put(f"{MINE}/{over['id']}/entry")
    assert late.json()["error"]["code"] == "CHALLENGE_OVER"
    assert len((await admin.get(ADMIN)).json()) == 2

    assert (await admin.delete(f"{ADMIN}/{over['id']}")).status_code == 204
    assert (await admin.delete(f"{ADMIN}/{over['id']}")).status_code == 404


async def test_progress_comes_from_the_reading_log(
    admin: ApiUser, customer: ApiUser, other_customer: ApiUser, create_book: CreateBook
) -> None:
    challenge = await _create(admin, category="fiction", goal=2)
    cid = challenge["id"]
    fiction_one = await create_book("Fiction One")
    fiction_two = await create_book("Fiction Two")
    science = await create_book("Cosmos", category=BookCategory.SCIENCE)
    mia = (await customer.post(KIDS, json={"name": "Mia", "birth_year": 2019})).json()["id"]

    assert (await customer.put(f"{MINE}/{cid}/entry")).status_code == 204
    assert (await customer.put(f"{MINE}/{cid}/entry")).status_code == 204  # once is enough
    assert (await customer.put(f"{MINE}/{cid}/entry", params={"child": mia})).status_code == 204
    others = await other_customer.put(f"{MINE}/{cid}/entry", params={"child": mia})
    assert others.status_code == 404  # not their child

    await _read(customer, fiction_one)
    await _read(customer, science)  # another category: does not count
    await _read(customer, fiction_two, offset=-10)  # before the challenge started
    await _read(customer, fiction_two, child=mia)
    mine = await _mine(customer, cid)
    assert [(p["child_name"], p["read"], p["completed"]) for p in mine] == [
        (None, 1, False),
        ("Mia", 1, False),
    ]

    await _read(customer, fiction_one, child=mia)
    mine = await _mine(customer, cid)
    assert [(p["child_name"], p["read"], p["completed"]) for p in mine] == [
        (None, 1, False),
        ("Mia", 2, True),
    ]
    listed = next(c for c in (await admin.get(ADMIN)).json() if c["id"] == cid)
    assert (listed["participants"], listed["completed"]) == (2, 1)
    people = (await admin.get(f"{ADMIN}/{cid}/participants")).json()
    assert [(p["name"], p["parent_name"], p["read"], p["completed"]) for p in people] == [
        ("Mia", customer.data["full_name"], 2, True),
        (customer.data["full_name"], None, 1, False),
    ]

    assert (await customer.delete(f"{MINE}/{cid}/entry")).status_code == 204
    assert [p["child_name"] for p in await _mine(customer, cid)] == ["Mia"]
