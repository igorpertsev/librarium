"""Customer email notifications: an outbox written with order changes, delivered later.

* ``enqueue`` is called inside the transaction that changes an order.
* ``queue_reminders`` adds due-soon / overdue reminders (run periodically).
* ``deliver_pending`` renders and sends queued emails with retries and backoff.

Messages are bilingual (English, then Russian) because the user's UI language is only
known to their browser. They are rendered at send time, from current order data.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Notification, Order, User
from app.models.enums import NotificationKind, NotificationStatus, OrderStatus
from app.repositories import orders as orders_repo

MAX_ATTEMPTS = 5
MAX_AGE = timedelta(days=7)  # older queued messages are no longer useful
BASE_RETRY_DELAY = timedelta(minutes=5)

Sender = Callable[[EmailMessage], Awaitable[None]]

_MONTHS_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip
_MONTHS_RU = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)  # fmt: skip


async def enqueue(
    session: AsyncSession, *, order_id: uuid.UUID, user_id: uuid.UUID, kind: NotificationKind
) -> None:
    """Queue a notification in the caller's transaction (at most once per order and kind)."""
    await session.execute(
        pg_insert(Notification)
        .values(id=uuid.uuid4(), order_id=order_id, user_id=user_id, kind=kind)
        .on_conflict_do_nothing(index_elements=[Notification.order_id, Notification.kind])
    )


async def queue_reminders(session: AsyncSession, *, today: date, due_soon_days: int) -> int:
    """Queue due-soon and overdue reminders for books that are out. Returns how many."""
    rows = (
        await session.execute(
            select(Order.id, Order.user_id, Order.due_date).where(
                Order.status == OrderStatus.CONFIRMED,
                Order.due_date <= today + timedelta(days=due_soon_days),
            )
        )
    ).all()
    values = [
        {
            "id": uuid.uuid4(),
            "order_id": order_id,
            "user_id": user_id,
            "kind": NotificationKind.OVERDUE if due < today else NotificationKind.DUE_SOON,
        }
        for order_id, user_id, due in rows
    ]
    if not values:
        return 0
    inserted = await session.execute(
        pg_insert(Notification)
        .values(values)
        .on_conflict_do_nothing(index_elements=[Notification.order_id, Notification.kind])
        .returning(Notification.id)
    )
    return len(inserted.all())


# --- Rendering -------------------------------------------------------------------------


def _date_en(value: date) -> str:
    return f"{value.day} {_MONTHS_EN[value.month - 1]} {value.year}"


def _date_ru(value: date) -> str:
    return f"{value.day} {_MONTHS_RU[value.month - 1]} {value.year} г."


def _render(kind: NotificationKind, user: User, order: Order, app_url: str) -> tuple[str, str]:
    books = "\n".join(f"  - {item.title} — {item.author}" for item in order.items)
    due_en, due_ru = _date_en(order.due_date), _date_ru(order.due_date)
    profile = f"{app_url}/profile"
    texts: dict[NotificationKind, tuple[str, str, str]] = {
        NotificationKind.ORDER_RECEIVED: (
            "We received your request · Заявка получена",
            f"we have received your request for these books:\n{books}\n\n"
            f"The library will confirm it soon. You can follow it on your profile: {profile}",
            f"мы получили вашу заявку на эти книги:\n{books}\n\n"
            f"Библиотека скоро её подтвердит. Статус можно посмотреть в профиле: {profile}",
        ),
        NotificationKind.ORDER_CONFIRMED: (
            "Your books have been handed over · Книги выданы",
            f"the library has confirmed your order and handed over these books:\n{books}\n\n"
            f"Please return them by {due_en}.",
            f"библиотека подтвердила заказ и выдала вам эти книги:\n{books}\n\n"
            # The Russian date already ends with the year abbreviation and its period.
            f"Пожалуйста, верните их до {due_ru}",
        ),
        NotificationKind.ORDER_CANCELLED: (
            "Your request was cancelled · Заявка отменена",
            f"the library has cancelled your request for these books:\n{books}\n\n"
            "If you think this is a mistake, please contact the library.",
            f"библиотека отменила вашу заявку на эти книги:\n{books}\n\n"
            "Если это ошибка, пожалуйста, свяжитесь с библиотекой.",
        ),
        NotificationKind.DUE_SOON: (
            f"Please return your books by {due_en} · Верните книги до {due_ru}",
            f"a friendly reminder: please return these books by {due_en}:\n{books}",
            f"напоминаем: пожалуйста, верните эти книги до {due_ru}:\n{books}",
        ),
        NotificationKind.OVERDUE: (
            "Your books are overdue · Срок возврата истёк",
            f"these books were due on {due_en} and have not been returned yet:\n{books}\n\n"
            "Please bring them back as soon as possible.",
            f"срок возврата этих книг истёк {due_ru}, но они ещё не возвращены:\n{books}\n\n"
            "Пожалуйста, верните их как можно скорее.",
        ),
    }
    subject, english, russian = texts[kind]
    body = (
        f"Hello {user.full_name},\n\n{english}\n\n— Little Dragon library\n\n"
        f"----------------------------------------\n\n"
        f"Здравствуйте, {user.full_name}!\n\n{russian}\n\n— Библиотека Little Dragon\n"
    )
    return subject, body


def build_message(settings: Settings, *, user: User, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = formataddr((user.full_name, user.email))
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain="little-dragon.library")
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(body)
    return message


# --- Delivery --------------------------------------------------------------------------


@dataclass
class DeliveryReport:
    sent: int = 0
    retried: int = 0
    failed: int = 0
    expired: int = 0

    @property
    def total(self) -> int:
        return self.sent + self.retried + self.failed + self.expired


async def deliver_pending(
    session: AsyncSession,
    settings: Settings,
    send: Sender,
    *,
    now: datetime | None = None,
    limit: int = 50,
) -> DeliveryReport:
    """Send due notifications. SKIP LOCKED lets several workers run without double sends."""
    now = now or datetime.now(UTC)
    report = DeliveryReport()
    batch = (
        await session.scalars(
            select(Notification)
            .where(
                Notification.status == NotificationStatus.PENDING,
                Notification.next_attempt_at <= now,
            )
            .order_by(Notification.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()

    for notification in batch:
        user = await session.get(User, notification.user_id)
        order = (
            await orders_repo.get_order(session, notification.order_id)
            if notification.order_id
            else None
        )
        if now - notification.created_at > MAX_AGE or user is None or not user.is_active:
            notification.status = NotificationStatus.EXPIRED
            report.expired += 1
            continue
        if order is None:  # pragma: no cover - every current kind belongs to an order
            notification.status = NotificationStatus.EXPIRED
            report.expired += 1
            continue

        subject, body = _render(notification.kind, user, order, settings.app_base_url)
        notification.recipient = user.email
        notification.subject = subject[:300]
        try:
            await send(build_message(settings, user=user, subject=subject, body=body))
        except (smtplib.SMTPException, OSError) as exc:
            notification.attempts += 1
            notification.last_error = f"{type(exc).__name__}: {exc}"[:500]
            if notification.attempts >= MAX_ATTEMPTS:
                notification.status = NotificationStatus.FAILED
                report.failed += 1
            else:
                notification.next_attempt_at = now + BASE_RETRY_DELAY * 2 ** (
                    notification.attempts - 1
                )
                report.retried += 1
        else:
            notification.status = NotificationStatus.SENT
            notification.sent_at = now
            report.sent += 1

    await session.commit()
    return report


def make_smtp_sender(settings: Settings) -> Sender | None:
    """SMTP sender for the configured server, or None when SMTP_HOST is not set."""
    host = settings.smtp_host
    if not host:
        return None

    def send_sync(message: EmailMessage) -> None:
        context = ssl.create_default_context()
        smtp: smtplib.SMTP
        if settings.smtp_ssl:
            smtp = smtplib.SMTP_SSL(host, settings.smtp_port, timeout=20, context=context)
        else:
            smtp = smtplib.SMTP(host, settings.smtp_port, timeout=20)
        with smtp:
            if settings.smtp_starttls and not settings.smtp_ssl:
                smtp.starttls(context=context)
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            smtp.send_message(message)

    async def send(message: EmailMessage) -> None:
        await asyncio.to_thread(send_sync, message)  # smtplib is blocking

    return send
