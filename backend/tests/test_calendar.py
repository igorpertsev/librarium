"""The reader's private calendar feed (iCalendar)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

from httpx import AsyncClient

from app.services import calendar
from tests.conftest import API, ApiUser, CreateBook, SetBatch
from tests.test_reservations import _borrow, _reserve


def _unfold(text: str) -> list[str]:
    """iCalendar lines, joined back together (RFC 5545 3.1)."""
    assert text.endswith("\r\n")
    lines: list[str] = []
    for raw in text.split("\r\n")[:-1]:
        if raw.startswith(" "):
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _events(lines: list[str]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            found.append(current)
            current = None
        elif current is not None and ":" in line:
            name, _, value = line.partition(":")
            current.setdefault(name, value)
    return found


async def _feed(client: AsyncClient, url: str) -> tuple[int, str]:
    response = await client.get(urlsplit(url).path)
    return response.status_code, response.text


async def test_the_link_can_be_replaced_and_turned_off(
    client: AsyncClient, customer: ApiUser
) -> None:
    assert (await customer.get(f"{API}/users/me")).json()["calendar_feed"] is False
    first = (await customer.post(f"{API}/users/me/calendar")).json()["url"]
    assert first.endswith(".ics")
    status, text = await _feed(client, first)  # no sign-in needed: the link is the key
    assert status == 200
    assert text.startswith("BEGIN:VCALENDAR\r\n")
    response = await client.get(urlsplit(first).path)
    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    assert (await customer.get(f"{API}/users/me")).json()["calendar_feed"] is True

    second = (await customer.post(f"{API}/users/me/calendar")).json()["url"]
    assert second != first
    assert (await _feed(client, first))[0] == 404  # the old link stopped working
    assert (await _feed(client, second))[0] == 200

    assert (await customer.delete(f"{API}/users/me/calendar")).status_code == 204
    assert (await _feed(client, second))[0] == 404
    assert (await client.get(f"{API}/calendar/not-a-token.ics")).status_code == 404


async def test_the_feed_shows_due_dates_and_reservations(
    client: AsyncClient,
    admin: ApiUser,
    customer: ApiUser,
    create_book: CreateBook,
    set_batch: SetBatch,
) -> None:
    await set_batch(1)
    borrowed = await create_book("War, Peace; and More")
    order_id = await _borrow(admin, customer, borrowed)
    dune = await create_book("Dune")
    assert (await _reserve(customer, dune, 10)).status_code == 201

    url = (await customer.post(f"{API}/users/me/calendar")).json()["url"]
    status, text = await _feed(client, url)
    assert status == 200
    lines = _unfold(text)
    assert all(len(raw.encode()) <= 75 for raw in text.split("\r\n"))
    assert lines[:2] == ["BEGIN:VCALENDAR", "VERSION:2.0"]
    assert lines[-1] == "END:VCALENDAR"

    events = {e["SUMMARY"].split(":")[0]: e for e in _events(lines)}
    due = events["Return to the library"]
    order = (await customer.get(f"{API}/orders/{order_id}")).json()
    due_day = date.fromisoformat(order["due_date"])
    assert due["SUMMARY"] == "Return to the library: War\\, Peace\\; and More"  # escaped
    assert due["DTSTART;VALUE=DATE"] == f"{due_day:%Y%m%d}"
    assert due["DTEND;VALUE=DATE"] == f"{due_day + timedelta(days=1):%Y%m%d}"
    assert due["UID"] == f"due-{order_id}@localhost"
    assert "TRIGGER:-P1D" in lines  # a reminder the day before

    reserved = events["Reserved book"]
    starts = datetime.now(UTC).date() + timedelta(days=10)
    assert reserved["SUMMARY"] == "Reserved book: Dune"
    assert reserved["DTSTART;VALUE=DATE"] == f"{starts:%Y%m%d}"
    assert reserved["URL"].endswith(f"/books/{dune}")

    # In Russian for a reader who chose Russian.
    await customer.patch(f"{API}/users/me", json={"preferred_language": "ru"})
    _, russian = await _feed(client, url)
    assert "SUMMARY:Вернуть в библиотеку: War\\, Peace\\; and More" in _unfold(russian)


def test_long_lines_are_folded_on_character_boundaries() -> None:
    event = calendar.Event(
        uid="x",
        summary="Вернуть в библиотеку: " + "Мастер и Маргарита, " * 6,
        start=date(2026, 12, 1),
        end=date(2026, 12, 2),
        description="line one\nline two",
    )
    text = calendar.render(
        [event], calendar_name="Little Dragon", host="lib", now=datetime.now(UTC)
    )
    raw_lines = text.split("\r\n")[:-1]
    assert all(len(line.encode()) <= 75 for line in raw_lines)
    assert any(line.startswith(" ") for line in raw_lines)  # something was folded
    lines = _unfold(text)
    summary = next(line for line in lines if line.startswith("SUMMARY:"))
    assert summary.removeprefix("SUMMARY:") == calendar._escape(event.summary)
    assert "DESCRIPTION:line one\\nline two" in lines
