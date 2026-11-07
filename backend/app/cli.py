"""Management commands.

python -m app.cli seed [--demo-books]   # idempotent: admin from env, optional demo books
python -m app.cli export-openapi PATH   # write the OpenAPI document without a server
python -m app.cli purge-tokens          # delete expired/revoked refresh tokens
python -m app.cli notifications [--loop SECONDS]  # queue reminders, send customer emails
python -m app.cli translate-books --to ru [--no-machine] [--limit N]  # fill missing translations
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
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import Database
from app.core.http import make_http_client, ping_monitor
from app.core.security import hash_password
from app.main import create_app
from app.models import Book, RefreshToken, Series, User
from app.models.enums import UiLanguage, UserRole
from app.repositories.books import copy_group_key
from app.schemas.book import BookCreate
from app.schemas.types import NormalizedEmail
from app.services import catalog, holds, mfa, reservations, telegram, web_push
from app.services.books import new_book, translation_rows
from app.services.library_settings import ensure_library_settings
from app.services.notifications import deliver_pending, make_smtp_sender, queue_reminders
from app.services.openlibrary import OpenLibraryClient
from app.services.translation_lookup import (
    TranslationLookup,
    WikimediaClient,
    make_machine_translator,
)
from app.services.translations import translate_catalogue

DEMO_BOOKS_FILE = Path(__file__).parent / "seed_data" / "demo_books.json"
DEMO_SERIES_RU = {"Harry Potter": "Гарри Поттер", "The Hunger Games": "Голодные игры"}
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
    created = refreshed = linked = translated = 0
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
        # Every copy of the title, also copies added before tags, series and translations.
        copies = (
            await session.scalars(
                select(Book).where(copy_group_key() == existing.group_id, Book.is_active.is_(True))
            )
        ).all()
        series_id = None
        if data.series_name:
            series_id = (await catalog.find_or_create_series(session, name=data.series_name)).id
        tags = await catalog.resolve_tags(session, data.tags)
        for copy in copies:
            if refresh_covers and copy.cover_url != data.cover_url:
                copy.cover_url = data.cover_url
                copy.image_urls = data.image_urls
                refreshed += 1
            # Demo books from before tags and series get them, unless edited since.
            if not copy.tags and copy.series_id is None and (tags or series_id):
                copy.tags = list(tags)
                copy.series_id = series_id
                copy.series_position = data.series_position if series_id else None
                linked += 1
            if not copy.translations and data.translations:
                copy.translations = translation_rows(data.translations)
                translated += 1

    print(
        f"Demo books: {created} created, {len(raw) - created} already present"
        + (f", {linked} given tags/series" if linked else "")
        + (f", {translated} given translations" if translated else "")
        + (f", {refreshed} covers refreshed." if refresh_covers else ".")
    )

    # Russian names of the demo series, unless a librarian has named them since.
    for name, name_ru in DEMO_SERIES_RU.items():
        await session.execute(
            update(Series)
            .where(Series.name == name, Series.name_ru.is_(None))
            .values(name_ru=name_ru)
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


async def _rotate_mfa_keys(settings: Settings) -> None:
    if not settings.mfa_keys:
        print("Set MFA_ENCRYPTION_KEYS first (the new key first); nothing was changed.")
        sys.exit(1)
    db = Database(settings)
    try:
        async with db.sessionmaker() as session:
            result = await mfa.rotate_keys(session, settings)
    finally:
        await db.dispose()
    print(f"Re-encrypted {result.rotated} two-step sign-in secrets with the first key.")
    if result.unreadable:
        print(
            f"{result.unreadable} could not be opened with any configured key; those users have "
            "to set two-step sign-in up again (or an administrator resets it)."
        )


async def _notifications(settings: Settings, *, loop_seconds: int | None) -> None:
    """Queue due-soon/overdue reminders and deliver pending emails, once or in a loop."""
    db = Database(settings)
    send = make_smtp_sender(settings)
    http = make_http_client(settings)
    bot = telegram.make_bot(settings, http)
    push = web_push.make_push_sender(settings, http)
    warned = False
    try:
        while True:
            async with db.sessionmaker() as session:
                # Holds that ran out go to the next reader in line (and queue their emails).
                expired = await holds.expire(session, datetime.now(UTC))
            if expired:
                print(f"{expired} hold(s) expired.")
            async with db.sessionmaker() as session:
                # Reservations whose day has come: hold the copy and email the reader.
                ready = await reservations.activate(session)
            if ready:
                print(f"{ready} reservation(s) ready.")
            async with db.sessionmaker() as session:
                queued = await queue_reminders(
                    session, today=datetime.now(UTC).date(), due_soon_days=settings.due_soon_days
                )
                await session.commit()
            if queued:
                print(f"Queued {queued} reminder(s).")
            if bot is not None:
                async with db.sessionmaker() as session:
                    # Readers linking (or unlinking) their Telegram chat.
                    await telegram.process_updates(session, bot)
            if send is None and not warned:
                print("SMTP_HOST is not set: emails stay queued (Telegram still works if set up).")
                warned = True
            if send is not None or bot is not None or push is not None:
                async with db.sessionmaker() as session:
                    report = await deliver_pending(session, settings, send, telegram=bot, push=push)
                if report.total:
                    print(
                        f"Emails: {report.sent} sent, {report.retried} to retry, "
                        f"{report.failed} failed, {report.expired} expired."
                    )
            await ping_monitor(http, settings.notifier_ping_url)  # "still running"
            if not loop_seconds:
                break
            await asyncio.sleep(loop_seconds)
    finally:
        await http.aclose()
        await db.dispose()


async def _translate_books(
    settings: Settings, *, target: UiLanguage, machine: bool, limit: int
) -> None:
    db = Database(settings)
    http = make_http_client(settings)
    translator, client = make_machine_translator(
        settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None,
        settings.translation_model,
    )
    if machine and translator is None:
        print("ANTHROPIC_API_KEY is not set: only Wikidata and Wikipedia are used.")
    lookup = TranslationLookup(OpenLibraryClient(http), WikimediaClient(http), translator)
    try:
        async with db.sessionmaker() as session:
            done = await translate_catalogue(
                session, lookup, target=target, machine=machine, limit=limit
            )
        print(f"Translated {done} title(s) into {target.value}.")
    finally:
        await http.aclose()
        if client is not None:
            await client.close()
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

    commands.add_parser(
        "generate-vapid-keys", help="Print a new key pair for Web Push (WEB_PUSH_*_KEY)"
    )
    commands.add_parser(
        "rotate-mfa-keys",
        help="Re-encrypt two-step sign-in secrets with the first MFA_ENCRYPTION_KEYS key",
    )

    translate = commands.add_parser(
        "translate-books", help="Find translations for titles that have none (review them later)"
    )
    translate.add_argument("--to", choices=[lang.value for lang in UiLanguage], default="ru")
    translate.add_argument("--no-machine", action="store_true", help="Wikidata and Wikipedia only")
    translate.add_argument("--limit", type=int, default=50, help="At most this many titles")

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
    elif args.command == "generate-vapid-keys":
        public, private = web_push.generate_keys()
        print(f"WEB_PUSH_PUBLIC_KEY={public}")
        print(f"WEB_PUSH_PRIVATE_KEY={private}")
    elif args.command == "rotate-mfa-keys":
        asyncio.run(_rotate_mfa_keys(get_settings()))
    elif args.command == "translate-books":
        asyncio.run(
            _translate_books(
                get_settings(),
                target=UiLanguage(args.to),
                machine=not args.no_machine,
                limit=args.limit,
            )
        )


if __name__ == "__main__":
    main(sys.argv[1:])
