"""Test fixtures.

Tests run against a real PostgreSQL database (``TEST_DATABASE_URL``) whose name must end in
``_test``. The schema is built with Alembic (upgrade → downgrade → upgrade, which also
exercises the downgrade path) and tables are truncated before each test. No transaction
wrapping is used, so concurrent requests really hit the database in parallel.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from argparse import Namespace
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from pydantic import SecretStr
from sqlalchemy import make_url, text, update

from alembic import command
from app.core.config import Environment, Settings
from app.main import create_app
from app.models import Book, LibrarySettings, User
from app.models.enums import BookCategory, BookStatus, UserRole
from app.models.library_settings import DEFAULT_LIBRARY_SETTINGS

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5433/bookstore_test"
)
API = "/api/v1"
PASSWORD = "correct-horse-battery"
FRONTEND_ORIGIN = "http://localhost:5173"


def _assert_test_database(url: str) -> None:
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        pytest.exit(f"Refusing to run tests against database {name!r}: name must end with _test")


async def _create_database_if_missing(url: str) -> None:
    parsed = make_url(url)
    conn = await asyncpg.connect(
        user=parsed.username,
        password=parsed.password,
        host=parsed.host,
        port=parsed.port or 5432,
        database="postgres",
    )
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", parsed.database):
            await conn.execute(f'CREATE DATABASE "{parsed.database}"')
    finally:
        await conn.close()


def _alembic(*commands: tuple[str, str]) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    cfg.cmd_opts = Namespace(x=[f"db_url={TEST_DATABASE_URL}"])
    for name, revision in commands:
        getattr(command, name)(cfg, revision)


@pytest.fixture(scope="session")
async def database_url() -> str:
    _assert_test_database(TEST_DATABASE_URL)
    await _create_database_if_missing(TEST_DATABASE_URL)
    # env.py calls asyncio.run(), so migrations run in a worker thread without a loop.
    await asyncio.to_thread(
        _alembic, ("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")
    )
    return TEST_DATABASE_URL


def make_settings(database_url: str, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": Environment.TEST,
        "database_url": database_url,
        "jwt_secret_key": SecretStr("test-secret-" + "x" * 52),
        "cookie_secure": False,
        "frontend_origins": FRONTEND_ORIGIN,
        "database_pool_size": 10,
        "media_dir": tempfile.mkdtemp(prefix="librarium-media-"),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture(scope="session")
async def app(database_url: str) -> AsyncIterator[FastAPI]:
    application = create_app(make_settings(database_url))
    yield application
    await application.state.db.dispose()


@pytest.fixture(autouse=True)
async def _clean_database(app: FastAPI) -> None:
    app.state.rate_limiter.reset()
    async with app.state.db.engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE users, books, carts, cart_items, orders, order_items, refresh_tokens, "
                "notifications, waitlist_entries, reading_list_entries, reviews, book_holds, "
                "tags, series, pickup_points, advance_reservations, reading_log_entries, "
                "audit_events, stocktakes, stocktake_counts, purchase_requests, purchase_votes, "
                "user_identities "
                "RESTART IDENTITY CASCADE"
            )
        )
        defaults = {k: v for k, v in DEFAULT_LIBRARY_SETTINGS.items() if k != "id"}
        await conn.execute(update(LibrarySettings).values(**defaults))


MakeClient = Callable[[], AsyncClient]


@pytest.fixture
async def make_client(app: FastAPI) -> AsyncIterator[MakeClient]:
    """Each client has its own cookie jar, i.e. behaves like a separate browser."""
    clients: list[AsyncClient] = []

    def factory() -> AsyncClient:
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.aclose()


@pytest.fixture
async def client(make_client: MakeClient) -> AsyncClient:
    return make_client()


@dataclass
class ApiUser:
    client: AsyncClient
    access_token: str
    data: dict[str, Any]
    password: str = PASSWORD
    refresh_token: str | None = field(default=None)

    @property
    def id(self) -> str:
        return str(self.data["id"])

    @property
    def email(self) -> str:
        return str(self.data["email"])

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    async def get(self, url: str, **kwargs: Any) -> Response:
        return await self.client.get(url, headers=self.headers, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Response:
        return await self.client.post(url, headers=self.headers, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> Response:
        return await self.client.patch(url, headers=self.headers, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> Response:
        return await self.client.put(url, headers=self.headers, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> Response:
        return await self.client.delete(url, headers=self.headers, **kwargs)


RegisterUser = Callable[..., Awaitable[ApiUser]]


@pytest.fixture
def register_user(make_client: MakeClient) -> RegisterUser:
    async def _register(
        email: str | None = None,
        password: str = PASSWORD,
        full_name: str = "Test Reader",
        **contacts: Any,
    ) -> ApiUser:
        client = make_client()
        payload = {
            "email": email or f"reader-{uuid.uuid4().hex[:10]}@example.com",
            "password": password,
            "full_name": full_name,
            **(contacts or {"telegram": "@reader", "preferred_contact_method": "telegram"}),
        }
        response = await client.post(f"{API}/auth/register", json=payload)
        assert response.status_code == 201, response.text
        body = response.json()
        return ApiUser(
            client=client,
            access_token=body["access_token"],
            data=body["user"],
            password=password,
            refresh_token=response.cookies.get("refresh_token"),
        )

    return _register


@pytest.fixture
async def customer(register_user: RegisterUser) -> ApiUser:
    return await register_user(full_name="Charlie Customer")


@pytest.fixture
async def other_customer(register_user: RegisterUser) -> ApiUser:
    return await register_user(full_name="Olivia Other")


@pytest.fixture
async def admin(app: FastAPI, register_user: RegisterUser) -> ApiUser:
    user = await register_user(email="librarian@example.com", full_name="Libby Librarian")
    async with app.state.db.sessionmaker() as session:
        await session.execute(
            update(User).where(User.id == uuid.UUID(user.id)).values(role=UserRole.ADMIN)
        )
        await session.commit()
    # Log in again so the access token carries the new role claim.
    response = await user.client.post(
        f"{API}/auth/login", json={"email": user.email, "password": user.password}
    )
    assert response.status_code == 200, response.text
    user.access_token = response.json()["access_token"]
    user.data = response.json()["user"]
    return user


CreateBook = Callable[..., Awaitable[str]]


@pytest.fixture
def create_book(app: FastAPI) -> CreateBook:
    counter = 0

    async def _create(
        title: str | None = None,
        *,
        author: str = "Ann Author",
        category: BookCategory = BookCategory.FICTION,
        status: BookStatus = BookStatus.AVAILABLE,
        is_active: bool = True,
        age_range: str = "12+",
        isbn: str | None = None,
    ) -> str:
        nonlocal counter
        counter += 1
        book = Book(
            id=uuid.uuid4(),
            title=title or f"Book {counter:03d}",
            author=author,
            description="A test book.",
            category=category,
            age_range=age_range,
            status=status,
            cover_url="https://images.example.com/cover.jpg",
            image_urls=["https://images.example.com/cover.jpg"],
            isbn=isbn or f"978-00000{counter:05d}",
            language="en",
            publication_year=2000 + counter,
            is_active=is_active,
        )
        async with app.state.db.sessionmaker() as session:
            session.add(book)
            await session.commit()
        return str(book.id)

    return _create


SetBatch = Callable[..., Awaitable[None]]


@pytest.fixture
def set_batch(app: FastAPI) -> SetBatch:
    async def _set(books_per_batch: int, price_per_batch: str = "15.99") -> None:
        async with app.state.db.sessionmaker() as session:
            await session.execute(
                update(LibrarySettings).values(
                    books_per_batch=books_per_batch, price_per_batch=Decimal(price_per_batch)
                )
            )
            await session.commit()

    return _set


async def fill_cart(user: ApiUser, book_ids: list[str]) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for book_id in book_ids:
        response = await user.post(f"{API}/cart/items", json={"book_id": book_id})
        assert response.status_code == 200, response.text
        body = response.json()
    return body


async def place_order(user: ApiUser) -> Response:
    return await user.post(f"{API}/orders")
