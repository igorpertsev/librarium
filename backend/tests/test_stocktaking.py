from __future__ import annotations

from typing import Any

from tests.conftest import API, ApiUser, SetBatch, fill_cart, place_order

TAKES = f"{API}/admin/stocktakes"


async def _book(admin: ApiUser, title: str, **extra: Any) -> str:
    body = {"title": title, "author": "A", "category": "fiction", **extra}
    created = await admin.post(f"{API}/admin/books", json=body)
    assert created.status_code == 201, created.text
    book_id: str = created.json()["id"]
    return book_id


async def test_counting_the_shelves_finds_missing_and_unknown_books(
    admin: ApiUser, customer: ApiUser, set_batch: SetBatch
) -> None:
    await set_batch(1)
    dune = await _book(admin, "Dune", isbn="978-0-441-17271-9")
    added = await admin.post(f"{API}/admin/books/{dune}/copies", json={"count": 1})
    second_dune = added.json()[0]["id"]
    emma = await _book(admin, "Emma", isbn="9780141439587")
    hamlet = await _book(admin, "Hamlet")
    await _book(admin, "Lost", status="not-available")
    await fill_cart(customer, [emma])
    order = (await place_order(customer)).json()
    await admin.patch(f"{API}/admin/orders/{order['id']}/status", json={"status": "confirmed"})

    take = (await admin.post(TAKES)).json()
    again = await admin.post(TAKES)
    assert again.json()["error"]["code"] == "STOCKTAKE_OPEN"
    url = f"{TAKES}/{take['id']}"

    scanned = (await admin.post(f"{url}/scan", json={"isbn": "9780441172719"})).json()
    assert scanned == {
        "found": True,
        "isbn": "9780441172719",
        "title": "Dune",
        "counted": 1,
        "expected": 2,
    }
    unknown = (await admin.post(f"{url}/scan", json={"isbn": "978-1-234-56789-7"})).json()
    assert (unknown["found"], unknown["counted"]) == (False, 1)
    for delta in (1, -1, 1):
        counted = await admin.post(f"{url}/count", json={"book_id": hamlet, "delta": delta})
    assert counted.json() == {"counted": 1}

    report = (await admin.get(url)).json()
    lines = {line["title"]: line for line in report["lines"]}
    assert report["lines"][0]["title"] == "Dune"  # titles with a difference come first
    assert (lines["Dune"]["expected"], lines["Dune"]["counted"]) == (2, 1)
    assert (lines["Emma"]["expected"], lines["Emma"]["on_loan"]) == (0, 1)
    assert (lines["Hamlet"]["expected"], lines["Hamlet"]["counted"]) == (1, 1)
    assert lines["Lost"]["expected"] == 0
    assert report["unknown_isbns"] == [{"isbn": "9781234567897", "counted": 1}]

    finished = (await admin.post(f"{url}/finish", json={"mark_missing": True})).json()
    assert finished["marked_missing"] == 1
    assert finished["finished_at"] is not None
    dunes = [(await admin.get(f"{API}/admin/books/{i}")).json() for i in (dune, second_dune)]
    assert sorted(d["status"] for d in dunes) == ["available", "not-available"]
    missing = next(d for d in dunes if d["status"] == "not-available")
    assert missing["condition_note"].startswith("Not found in the stocktake of ")
    emma_now = (await admin.get(f"{API}/admin/books/{emma}")).json()
    assert emma_now["status"] == "available"  # out on loan, so never marked
    late = await admin.post(f"{url}/scan", json={"isbn": "9780441172719"})
    assert late.json()["error"]["code"] == "STOCKTAKE_FINISHED"
    history = (await admin.get(TAKES)).json()
    assert [t["marked_missing"] for t in history] == [1]
    # Scans are not in the activity log; starting and finishing are.
    actions = [e["action"] for e in (await admin.get(f"{API}/admin/audit")).json()["items"]]
    assert "admin_stocktake_scan" not in actions
    assert {"admin_start_stocktake", "admin_finish_stocktake"} <= set(actions)
