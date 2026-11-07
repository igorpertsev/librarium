"""A private calendar feed (iCalendar, RFC 5545) for each reader.

The profile creates a secret link (``/api/v1/calendar/<token>.ics``) that calendar apps subscribe
to: they cannot send our sign-in, so the link itself is the key. Only its SHA-256 is stored; a new
link replaces the old one, and turning it off removes it. The feed shows due dates (with a
reminder the day before), pickup appointments, the last day to collect a held book and the dates
of reservations.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.models import AdvanceReservation, Book, BookHold, Order, User
from app.models.enums import OrderStatus, ReservationStatus, UiLanguage

PRODID = "-//Little Dragon//Library calendar//EN"
REFRESH = "PT6H"  # calendar apps may check every six hours


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def feed_url(settings: Settings, token: str) -> str:
    return f"{settings.public_api_url}/calendar/{token}.ics"


async def new_link(session: AsyncSession, settings: Settings, user: User) -> str:
    """A fresh feed URL for the reader; the previous one stops working."""
    token = secrets.token_urlsafe(32)
    user.calendar_token_hash = _hash(token)
    await session.commit()
    return feed_url(settings, token)


async def remove_link(session: AsyncSession, user: User) -> None:
    user.calendar_token_hash = None
    await session.commit()


async def reader_for(session: AsyncSession, token: str) -> User | None:
    if not token or len(token) > 100:
        return None
    user = await session.scalar(select(User).where(User.calendar_token_hash == _hash(token)))
    return user if user is not None and user.is_active else None


# --- Events ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Event:
    uid: str
    summary: str
    start: date | datetime
    end: date | datetime
    description: str = ""
    location: str = ""
    url: str = ""
    alarm: str = ""  # text of a reminder the day before, if any
    categories: tuple[str, ...] = field(default=())


_TEXT = {
    "due": ("Return to the library: {books}", "Вернуть в библиотеку: {books}"),
    "due_alarm": ("Library books are due tomorrow", "Завтра нужно вернуть книги в библиотеку"),
    "pickup": ("Pick up library books: {point}", "Забрать книги из библиотеки: {point}"),
    "held": ("Last day to collect: {book}", "Последний день, чтобы забрать: {book}"),
    "reserved": ("Reserved book: {book}", "Забронированная книга: {book}"),
    "for_child": (" (for {name})", " (для {name})"),
    "order": ("Order {number}", "Заказ {number}"),
}


def _say(language: UiLanguage | None, key: str, **values: object) -> str:
    english, russian = _TEXT[key]
    return (russian if language is UiLanguage.RU else english).format(**values)


def _books(order: Order) -> str:
    titles = [item.title for item in sorted(order.items, key=lambda i: i.position)]
    shown = ", ".join(titles[:3])
    return f"{shown} +{len(titles) - 3}" if len(titles) > 3 else shown


async def events(
    session: AsyncSession, settings: Settings, user: User, zone: ZoneInfo, now: datetime
) -> list[Event]:
    language = user.preferred_language
    profile = f"{settings.app_base_url}/profile"
    found: list[Event] = []
    orders = (
        await session.scalars(
            select(Order)
            .options(selectinload(Order.items))
            .where(
                Order.user_id == user.id,
                Order.status.in_([OrderStatus.PENDING, OrderStatus.CONFIRMED]),
            )
        )
    ).all()
    for order in orders:
        child = _say(language, "for_child", name=order.child_name) if order.child_name else ""
        details = "\n".join(f"• {item.title} — {item.author}" for item in order.items)
        number = _say(language, "order", number=order.number)
        if order.status is OrderStatus.CONFIRMED:
            found.append(
                Event(
                    uid=f"due-{order.id}",
                    summary=_say(language, "due", books=_books(order)) + child,
                    start=order.due_date,
                    end=order.due_date + timedelta(days=1),
                    description=f"{number}\n{details}",
                    url=profile,
                    alarm=_say(language, "due_alarm"),
                )
            )
        elif order.pickup_at is not None and order.pickup_at > now - timedelta(days=1):
            point = order.pickup_point
            length = timedelta(minutes=point.slot_minutes if point else 60)
            found.append(
                Event(
                    uid=f"pickup-{order.id}",
                    summary=_say(language, "pickup", point=point.name if point else "") + child,
                    start=order.pickup_at,
                    end=order.pickup_at + length,
                    description=f"{number}\n{details}",
                    location=f"{point.name}, {point.address}" if point else "",
                    url=profile,
                )
            )

    holds = (
        await session.execute(
            select(BookHold, Book.title)
            .join(Book, Book.id == BookHold.book_id)
            .where(BookHold.user_id == user.id, BookHold.held_until > now)
        )
    ).all()
    for hold, title in holds:
        day = hold.held_until.astimezone(zone).date()
        found.append(
            Event(
                uid=f"hold-{hold.book_id}-{hold.held_until:%Y%m%d%H%M}",
                summary=_say(language, "held", book=title),
                start=day,
                end=day + timedelta(days=1),
                url=f"{settings.app_base_url}/books/{hold.book_id}",
            )
        )

    reservations = (
        await session.execute(
            select(AdvanceReservation, Book.title)
            .join(Book, Book.id == AdvanceReservation.book_id)
            .where(
                AdvanceReservation.user_id == user.id,
                AdvanceReservation.status == ReservationStatus.ACTIVE,
            )
        )
    ).all()
    for reservation, title in reservations:
        found.append(
            Event(
                uid=f"reservation-{reservation.id}",
                summary=_say(language, "reserved", book=title),
                start=reservation.starts_on,
                end=reservation.starts_on + timedelta(days=1),
                url=f"{settings.app_base_url}/books/{reservation.book_id}",
            )
        )
    return sorted(found, key=lambda e: (str(e.start), e.uid))


# --- iCalendar text --------------------------------------------------------------------------


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> list[str]:
    """Lines of at most 75 octets; continuations start with a space (RFC 5545 3.1)."""
    out: list[str] = []
    current = ""
    for char in line:
        limit = 75 if not out else 74  # the leading space of a continuation counts
        if len((current + char).encode()) > limit:
            out.append(current)
            current = char
        else:
            current += char
    out.append(current)
    return [out[0], *(f" {part}" for part in out[1:])]


def _when(name: str, value: date | datetime) -> str:
    if isinstance(value, datetime):
        return f"{name}:{value.astimezone(UTC):%Y%m%dT%H%M%SZ}"
    return f"{name};VALUE=DATE:{value:%Y%m%d}"


def render(items: list[Event], *, calendar_name: str, host: str, now: datetime) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
        f"REFRESH-INTERVAL;VALUE=DURATION:{REFRESH}",
        f"X-PUBLISHED-TTL:{REFRESH}",
    ]
    stamp = f"DTSTAMP:{now.astimezone(UTC):%Y%m%dT%H%M%SZ}"
    for event in items:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{event.uid}@{host}",
            stamp,
            _when("DTSTART", event.start),
            _when("DTEND", event.end),
            f"SUMMARY:{_escape(event.summary)}",
            "TRANSP:TRANSPARENT",  # does not block time in the reader's calendar
        ]
        if event.description:
            lines.append(f"DESCRIPTION:{_escape(event.description)}")
        if event.location:
            lines.append(f"LOCATION:{_escape(event.location)}")
        if event.url:
            lines.append(f"URL:{event.url}")
        if event.alarm:
            lines += [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{_escape(event.alarm)}",
                "TRIGGER:-P1D",
                "END:VALARM",
            ]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "".join(f"{part}\r\n" for line in lines for part in _fold(line))
