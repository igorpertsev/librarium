"""Management commands.

python -m app.cli seed [--demo-books]   # idempotent: admin from env, optional demo books
python -m app.cli export-openapi PATH   # write the OpenAPI document without a server
python -m app.cli purge-tokens          # delete expired/revoked refresh tokens
python -m app.cli notifications [--loop SECONDS]  # queue reminders, send customer emails
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import Database
from app.core.security import hash_password
from app.main import create_app
from app.models import Book, RefreshToken, User
from app.models.enums import UserRole
from app.schemas.book import BookCreate
from app.schemas.types import NormalizedEmail
from app.services import catalog
from app.services.books import new_book
from app.services.library_settings import ensure_library_settings
from app.services.notifications import deliver_pending, make_smtp_sender, queue_reminders

DEMO_BOOKS_FILE = Path(__file__).parent / "seed_data" / "demo_books.json"
MIN_ADMIN_PASSWORD_LENGTH = 12


async def _seed(
    settings: Settings,
    *,
    demo_books: bool,
    reset_admin_password: bool,
    refresh_demo_covers: bool = False,
) -> None:
    if demo_books and settings.is_production:
        raise SystemExit("Refusing to load demo books in production.")

    db = Database(settings)
    try:
        async with db.sessionmaker() as session:
            await ensure_library_settings(session)

            if settings.seed_admin_email and settings.seed_admin_password:
                email = TypeAdapter(NormalizedEmail).validate_python(settings.seed_admin_email)
                password = settings.seed_admin_password.get_secret_value()
                if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
                    raise SystemExit(
                        f"SEED_ADMIN_PASSWORD must be at least {MIN_ADMIN_PASSWORD_LENGTH} chars."
                    )
                admin = await session.scalar(select(User).where(User.email == email))
                if admin is None:
                    session.add(
                        User(
                            id=uuid.uuid4(),
                            email=email,
                            full_name=settings.seed_admin_name,
                            password_hash=await hash_password(password),
                            role=UserRole.ADMIN,
                        )
                    )
                    print(f"Created admin {email}")
                else:
                    admin.role = UserRole.ADMIN
                    admin.is_active = True
                    if reset_admin_password:
                        admin.password_hash = await hash_password(password)
                    print(f"Admin {email} already exists (ensured role/active).")
            else:
                print("SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD not set: skipping admin user.")

            if demo_books:
                await _seed_demo_books(session, refresh_covers=refresh_demo_covers)

            await session.commit()
    finally:
        await db.dispose()


async def _seed_demo_books(session: AsyncSession, *, refresh_covers: bool) -> None:
    raw: list[dict[str, Any]] = json.loads(DEMO_BOOKS_FILE.read_text("utf-8"))
    # Starter tags a librarian has deleted or merged since are left out.
    known_tags = set((await catalog.tag_lookup(session)).values())
    created = refreshed = linked = 0
    for item in raw:
        data = BookCreate.model_validate(item)
        data.tags = [slug for slug in data.tags if slug in known_tags]
        existing = await session.scalar(
            select(Book).where(Book.isbn == data.isbn, Book.title == data.title)
        )
        if existing is None:
            await new_book(session, data)
            await session.flush()  # a later book may belong to the same new series
            created += 1
            continue
        if refresh_covers and existing.cover_url != data.cover_url:
            existing.cover_url = data.cover_url
            existing.image_urls = data.image_urls
            refreshed += 1
        # Demo books from before tags and series get them, unless edited since.
        if not existing.tags and existing.series_id is None:
            existing.tags = await catalog.resolve_tags(session, data.tags)
            if data.series_name:
                series = await catalog.find_or_create_series(session, name=data.series_name)
                existing.series_id = series.id
                existing.series_position = data.series_position
            linked += bool(existing.tags or data.series_name)
    print(
        f"Demo books: {created} created, {len(raw) - created} already present"
        + (f", {linked} given tags/series" if linked else "")
        + (f", {refreshed} covers refreshed." if refresh_covers else ".")
    )


async def _purge_tokens(settings: Settings, *, older_than_days: int) -> None:
    db = Database(settings)
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    try:
        async with db.sessionmaker() as session:
            result = await session.execute(
                delete(RefreshToken).where(
                    or_(RefreshToken.expires_at < cutoff, RefreshToken.revoked_at < cutoff)
                )
            )
            await session.commit()
            print(f"Deleted {getattr(result, 'rowcount', 0)} refresh tokens.")
    finally:
        await db.dispose()


async def _notifications(settings: Settings, *, loop_seconds: int | None) -> None:
    """Queue due-soon/overdue reminders and deliver pending emails, once or in a loop."""
    db = Database(settings)
    send = make_smtp_sender(settings)
    warned = False
    try:
        while True:
            async with db.sessionmaker() as session:
                queued = await queue_reminders(
                    session, today=datetime.now(UTC).date(), due_soon_days=settings.due_soon_days
                )
                await session.commit()
            if queued:
                print(f"Queued {queued} reminder(s).")
            if send is None:
                if not warned:
                    print("SMTP_HOST is not set: notifications stay queued and are not sent.")
                    warned = True
            else:
                async with db.sessionmaker() as session:
                    report = await deliver_pending(session, settings, send)
                if report.total:
                    print(
                        f"Emails: {report.sent} sent, {report.retried} to retry, "
                        f"{report.failed} failed, {report.expired} expired."
                    )
            if not loop_seconds:
                break
            await asyncio.sleep(loop_seconds)
    finally:
        await db.dispose()


def _export_openapi(path: str) -> None:
    document = create_app(get_settings()).openapi()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(f"OpenAPI schema written to {target}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    seed = commands.add_parser("seed", help="Create the admin from env and optional demo data")
    seed.add_argument("--demo-books", action="store_true", help="Load demo books (not in prod)")
    seed.add_argument(
        "--reset-admin-password",
        action="store_true",
        help="Overwrite the password of an existing admin with SEED_ADMIN_PASSWORD",
    )
    seed.add_argument(
        "--refresh-demo-covers",
        action="store_true",
        help="With --demo-books: update the covers of demo books that already exist",
    )

    export = commands.add_parser("export-openapi", help="Write openapi.json")
    export.add_argument("path", nargs="?", default="openapi.json")

    purge = commands.add_parser("purge-tokens", help="Delete old expired/revoked refresh tokens")
    purge.add_argument("--older-than-days", type=int, default=7)

    notify = commands.add_parser("notifications", help="Queue reminders and send customer emails")
    notify.add_argument(
        "--loop", type=int, metavar="SECONDS", help="Repeat every SECONDS instead of running once"
    )

    args = parser.parse_args(argv)
    if args.command == "seed":
        asyncio.run(
            _seed(
                get_settings(),
                demo_books=args.demo_books,
                reset_admin_password=args.reset_admin_password,
                refresh_demo_covers=args.refresh_demo_covers,
            )
        )
    elif args.command == "export-openapi":
        _export_openapi(args.path)
    elif args.command == "purge-tokens":
        asyncio.run(_purge_tokens(get_settings(), older_than_days=args.older_than_days))
    elif args.command == "notifications":
        asyncio.run(_notifications(get_settings(), loop_seconds=args.loop))


if __name__ == "__main__":
    main(sys.argv[1:])
