# Little Dragon — online library

**English** | [Русский](README.ru.md)

Frontend: React + TypeScript + Vite (design from [Figma](https://www.figma.com/design/3D9jREiGTmIKNYLFQXjh7o/Online-library-website)).
Backend: FastAPI + PostgreSQL (`backend/`).

The app UI defaults to English; Russian is available as an optional language in Settings.

## Screenshots

| Catalogue | Book details |
| --- | --- |
| ![Catalogue with availability badges](docs/screenshots/catalog.jpg) | ![Book details dialog](docs/screenshots/book-details.jpg) |
| **Cart: books are lent in batches** | **Profile: pending requests and borrowed books** |
| ![Cart with a complete and an incomplete batch](docs/screenshots/cart.jpg) | ![Customer profile](docs/screenshots/profile.png) |
| **Admin portal** | **Order management** |
| ![Admin portal with batch configuration and statistics](docs/screenshots/admin.png) | ![Orders tab with status workflow](docs/screenshots/admin-orders.png) |

Sign-in page: [docs/screenshots/login.png](docs/screenshots/login.png). Captured from the demo data at 1280 px.

## Requirements

| Tool | Version | Used for |
| --- | --- | --- |
| Docker + Docker Compose | 24+ / v2 | PostgreSQL, backend, tests |
| Node.js | 20+ | frontend |
| pnpm | 9+ (`corepack enable`) | frontend dependencies (`pnpm-lock.yaml`) |
| Python 3.12 + [uv](https://docs.astral.sh/uv/) | optional | running the backend without Docker |

## Architecture

```
browser ──► Vite dev server (:5173)  React SPA, i18next (en/ru)
   │            src/api/client.ts   fetch + in-memory access token + one refresh on 401
   │            src/api/mappers.ts  DTO (OpenAPI) ⇄ UI models (src/app/types.ts)
   ▼
FastAPI (:8000)  /api/v1/...        routes → services → repositories → SQLAlchemy 2 (async)
   ▼
PostgreSQL 16 (:5433 on the host)   schema managed by Alembic only
```

```
backend/
  app/
    api/            dependencies.py (session, auth, roles), router.py, routes/*.py
    core/           config.py (pydantic-settings), database.py, security.py, exceptions.py
    models/         SQLAlchemy models + enums.py (ACTIVE_ORDER_STATUSES)
    schemas/        Pydantic 2: separate create/update/read schemas
    repositories/   queries (filters, reservation state)
    services/       business logic and transactions (orders.py — checkout)
    cli.py          seed / export-openapi / purge-tokens
  alembic/          migrations (async env.py)
  tests/            pytest + httpx against a real PostgreSQL (`bookstore_test`)
src/api/            API client, generated types, mappers
```

## Quick start (Docker Compose)

```bash
cp .env.example .env
```

```bash
docker compose up -d --build
```

This starts `db` (PostgreSQL with a healthcheck), `migrate` (one-off `alembic upgrade head`) and `backend`.

```bash
curl http://localhost:8000/api/v1/health
```

Create an administrator and demo books (safe to run repeatedly):

```bash
docker compose run --rm -e SEED_ADMIN_PASSWORD='choose-a-long-password' backend python -m app.cli seed --demo-books
```

Frontend:

```bash
pnpm install
```

```bash
pnpm dev
```

Open http://localhost:5173 (use `localhost`, not `127.0.0.1` — see “Troubleshooting”).
Swagger UI: http://localhost:8000/docs.

## Environment variables

The backend reads environment variables or `backend/.env` (template: `backend/.env.example`);
Docker Compose and Vite read the root `.env` (template: `.env.example`). Filled-in `.env` files are never committed.

| Variable | Default | Description |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `development` / `test` / `production` |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5433/bookstore` | `postgres://` and `postgresql://` are normalised to asyncpg |
| `JWT_SECRET_KEY` | — | **required in production**, ≥ 32 characters, not a known weak value; in development an ephemeral secret is generated if empty |
| `JWT_ALGORITHM` | `HS256` | HS256/384/512 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | 1–60 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | 1–180 |
| `REFRESH_COOKIE_NAME` | `refresh_token` | |
| `COOKIE_SECURE` | `false` | must be `true` in production |
| `COOKIE_SAMESITE` | `lax` | `none` is only allowed with `COOKIE_SECURE=true` |
| `FRONTEND_ORIGINS` | `http://localhost:5173` | exact origins, comma-separated; `*` is rejected |
| `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` | — | used by `app.cli seed`, password ≥ 12 characters |
| `TEST_DATABASE_URL` | `…/bookstore_test` | tests only; the database name must end with `_test` |
| `VITE_API_URL` | `http://localhost:8000/api/v1` | API base URL for the frontend |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_STARTTLS`, `SMTP_SSL`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAIL_FROM` | empty / `587` / `true` / `false` | outgoing email; empty `SMTP_HOST` disables sending |
| `APP_BASE_URL`, `DUE_SOON_DAYS` | `http://localhost:5173`, `3` | links in emails; reminder lead time in days |

In production the app refuses to start with a missing/weak `JWT_SECRET_KEY`, `COOKIE_SECURE=false`
or an `http://` origin in `FRONTEND_ORIGINS`.

## Backend without Docker

```bash
cd backend && uv sync
```

```bash
cd backend && cp .env.example .env
```

```bash
docker compose up -d db
```

```bash
cd backend && uv run alembic upgrade head
```

```bash
cd backend && uv run uvicorn app.main:app --reload
```

## Migrations

All commands can run in the `backend-dev` container (`dev` profile, sources are bind-mounted):

```bash
docker compose --profile dev run --rm backend-dev alembic upgrade head
```

```bash
docker compose --profile dev run --rm backend-dev alembic downgrade -1
```

```bash
docker compose --profile dev run --rm backend-dev alembic revision --autogenerate -m "description"
```

```bash
docker compose --profile dev run --rm backend-dev alembic check
```

`alembic check` must print `No new upgrade operations detected.` — models and migrations match.
The application never calls `metadata.create_all()`.

## Seed

`python -m app.cli seed [--demo-books] [--reset-admin-password]`:

- creates/activates the administrator from `SEED_ADMIN_EMAIL` + `SEED_ADMIN_PASSWORD` (no password is stored in code);
  an existing admin's password is only changed with `--reset-admin-password`;
- `--demo-books` adds 16 books from `backend/app/seed_data/demo_books.json`; refuses to run in production;
- `--refresh-demo-covers` (with `--demo-books`) updates the covers of demo books that already exist
  (the demo data uses real covers from Open Library);
- ensures the library settings row exists. Running it again never duplicates anything.

## Tests, lint, typecheck

Backend (PostgreSQL from compose, separate `bookstore_test` database created by an init script/fixture):

```bash
docker compose --profile dev run --rm backend-dev pytest
```

```bash
docker compose --profile dev run --rm backend-dev sh -c "ruff format --check . && ruff check . && mypy"
```

Frontend:

```bash
pnpm typecheck
```

```bash
pnpm build
```

The test session runs migrations `upgrade → downgrade base → upgrade`, truncates tables before each test and does
not wrap tests in a transaction, so concurrent requests really go through separate database connections.

## Generating TypeScript types from OpenAPI

From a running backend:

```bash
pnpm api:types
```

Or from the saved schema (no server needed):

```bash
docker compose --profile dev run --rm --no-deps backend-dev python -m app.cli export-openapi openapi.json
```

```bash
pnpm api:types:file
```

The output is `src/api/generated/schema.d.ts`; **never edit it by hand**. DTO aliases live in `src/api/types.ts`,
conversion to UI models in `src/api/mappers.ts`. After an API change: export the schema → generate → `pnpm typecheck`.

## Authentication

- **Passwords** — Argon2id (`argon2-cffi`), hashed in a thread pool, transparently rehashed on login.
- **Access token** — JWT (HS256), 15 minutes, claims `sub`, `role`, `type`, `jti`, `iat`, `nbf`, `exp`, `iss`, `aud`.
  Sent as `Authorization: Bearer`. The frontend keeps it in memory only.
  Authorisation always uses the role stored in the database; the `role` claim is informational.
- **Refresh token** — random string (`secrets.token_urlsafe(48)`); only its SHA-256 hash is stored.
  It lives in the `refresh_token` cookie: `HttpOnly`, `Secure` (from env), `SameSite=Lax`, `Path=/api/v1/auth`.
  It is never returned in JSON.
- **Rotation**: every `POST /auth/refresh` issues a new token in the same “family” and revokes the old one
  (`replaced_by_token_id`). Presenting a revoked token again is treated as theft → the whole family is revoked
  (`REFRESH_TOKEN_REUSED`).
- **Logout** revokes the current refresh token and deletes the cookie. **Changing the password** revokes all sessions
  and issues a new family. **Disabling** a user (`is_active=false`) revokes their refresh tokens, and their
  access tokens stop working immediately (`ACCOUNT_DISABLED`).
- Login errors are identical for “unknown email” and “wrong password”; Argon2 verification runs even when the user
  does not exist (no timing leak).
- Cookie endpoints (`/auth/*`) additionally reject requests with a foreign `Origin` (`ORIGIN_NOT_ALLOWED`).

**Frontend flow**: on page load `POST /auth/refresh` restores the session from the cookie;
on a 401 the client performs one shared refresh and retries the request once; the refresh call never triggers
another refresh (no loop); if refresh fails, the auth state is cleared. Across tabs refreshes are serialised
with the Web Locks API so two tabs never present the same token.

## CORS

Only the origins in `FRONTEND_ORIGINS`, `allow_credentials=True`, methods `GET/POST/PATCH/DELETE`,
headers `Authorization`, `Content-Type`. A `*` wildcard is rejected at startup.

## Book reservation rules

Each `Book` record is **one physical copy** (that is how the existing UI works:
`isBookUnavailable(bookId)`, no quantities). Reservations are therefore tracked per `book_id`;
two copies of the same title are two records (ISBN is not unique).

- Active order statuses: `ACTIVE_ORDER_STATUSES = {pending, confirmed}` (`app/models/enums.py`).
  `returned` and `cancelled` release the book.
- A book is blocked by **any** active order, including one placed by the same user (as in the UI).
- **Copies**: a book row is one physical copy. Copies of a title share `copy_group_id` (admin “Add a copy”); the
  catalogue (`GET /books`) lists each title once, represented by a copy that can be borrowed if there is one, with
  `copies` and `copies_available`. Catalogue edits apply to all copies of the title; status stays per copy.
- The cart is not a reservation: the same book can sit in several users' carts; adding it checks
  availability, but the decisive check happens at checkout.
- Pricing is per **batch**: `price_per_batch` for every complete set of `books_per_batch` books (library
  settings, the admin “Batch Configuration” card). An order contains the complete batches in the order the
  books were added; books of an incomplete trailing batch stay in the cart.

`POST /api/v1/orders` runs in a single transaction (`app/services/orders.py`):

1. `SELECT … FOR UPDATE` on the cart row (protects against double clicks / two tabs);
2. empty cart → `400 CART_EMPTY`, no complete batch → `400 INCOMPLETE_BATCH`;
3. `SELECT … FOR SHARE` on the settings, `SELECT … FOR UPDATE` on the books **ordered by id** (no deadlocks);
4. checks that each book is active, has status `available` and is not in an active order (`ACTIVE_ORDER_STATUSES` only);
5. on conflict — an exception, the whole transaction rolls back, `409 BOOK_UNAVAILABLE` with the list of books;
6. the total is computed on the server only; items keep a snapshot of title/author/ISBN/cover and a unit price
   (the batch price is split into cents without rounding loss);
7. the ordered items are removed from the cart, commit.

The second line of defence is the partial unique index
`uq_order_items_active_book ON order_items(book_id) WHERE reservation_active`: even code that skips the lock
cannot create a second active reservation (test `test_partial_unique_index_stops_the_race_even_without_row_locks`).
Concurrency is covered by tests in which both requests are held at a barrier right before `FOR UPDATE`.

## Data model and differences from the frontend

| Table | Key points |
| --- | --- |
| `users` | email unique and lower-case (CHECK), Argon2 hash, role `customer/admin`, contacts (nullable), `preferred_contact_method` |
| `books` | one row per physical copy: `cover_url`, `image_urls[]`, `age_range`, `category`, `status` (`available/available-soon/not-available`), `language`, `publication_year`, `is_active` (soft delete), `copy_group_id` (copies of one title) |
| `library_settings` | single row: `books_per_batch`, `price_per_batch NUMERIC(10,2)`, `currency`, `loan_period_days` |
| `carts`, `cart_items` | one cart per user, `UNIQUE(cart_id, book_id)` |
| `orders` | status, total/currency, batch price and contact snapshot, `due_date`, `confirmed_at/returned_at/cancelled_at`, CHECK `total = price × batches` |
| `order_items` | book snapshot and `unit_price`, `reservation_active` + partial unique index |
| `refresh_tokens` | `token_hash`, `family_id`, `expires_at`, `revoked_at`, `replaced_by_token_id`, user agent/IP |

Enumerations are stored as `VARCHAR + CHECK` (changeable without `ALTER TYPE`). Money is `NUMERIC`; in JSON it is a string (`"15.99"`).

Differences (adapters in `src/api/mappers.ts`):

- The UI has no per-book price, only a batch price; therefore `Book` has no `price` — pricing lives in `library_settings` and in the order snapshot.
- Order statuses follow the UI (`pending/confirmed/returned/cancelled`) instead of `processing/completed`.
- `coverImage/images/publishedYear/ageRange` ⇄ `cover_url/image_urls/publication_year/age_range`;
  the UI book status `pending` means “in my cart” and is not stored on the server.
- The server also accepts `email` as `preferred_contact_method`; the UI has no such option, so it shows as “not selected”.
- `User.borrowedBooks` is built from confirmed orders (`active_loans` in `/admin/users`).
- Optional fields were added to the UI models: `Book.isReserved/isAvailable/language`, `Order.currency/contacts`.

## API (`/api/v1`)

| Method | Path | Access |
| --- | --- | --- |
| GET | `/health` (liveness), `/api/v1/health` (DB) | everyone |
| POST | `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout` | everyone |
| GET | `/auth/me`, `/users/me` · PATCH `/users/me` · POST `/auth/change-password` | signed-in user |
| GET | `/books?q&category&age_range&available&sort&page&page_size`, `/books/age-ranges`, `/books/{id}` | everyone |
| GET/DELETE | `/cart` · POST `/cart/items` · DELETE `/cart/items/{book_id}` | signed-in user |
| POST/GET | `/orders` · GET `/orders/{id}` · POST `/orders/{id}/cancel` | signed-in user (own orders only) |
| GET/POST | `/admin/books`, GET `/admin/books/stats`, GET/PATCH/DELETE `/admin/books/{id}` | admin |
| POST | `/admin/books/{id}/copies` (`{count}`: more copies of a title) | admin |
| GET | `/admin/users` · PATCH `/admin/users/{id}` (role, disable) | admin |
| GET | `/admin/orders`, `/admin/orders/{id}` · PATCH `/admin/orders/{id}/status`, `/admin/orders/{id}/due-date` | admin |
| GET/PATCH | `/admin/settings` (batch size, price, currency, loan period) | admin |

Book sorting is allow-listed: `title`, `author`, `publication_year`, `created_at` (prefix `-` for descending).
Status transitions: `pending → confirmed | cancelled`, `confirmed → returned`; customers can only cancel `pending` orders.

Error format (the same for every status):

```json
{"error": {"code": "BOOK_UNAVAILABLE", "message": "One or more books are unavailable",
           "details": {"book_ids": ["…"], "books": [{"id": "…", "title": "…"}]}}}
```

400 `CART_EMPTY`/`INCOMPLETE_BATCH`/`INVALID_CURRENT_PASSWORD`, 401 `NOT_AUTHENTICATED`/`INVALID_CREDENTIALS`/`TOKEN_EXPIRED`/`REFRESH_TOKEN_*`,
403 `FORBIDDEN`/`ACCOUNT_DISABLED`, 404 `*_NOT_FOUND`, 409 `BOOK_UNAVAILABLE`/`EMAIL_ALREADY_EXISTS`/`INVALID_STATUS_TRANSITION`,
422 `VALIDATION_ERROR` (submitted values are not echoed back), 500 `INTERNAL_ERROR` (no stack trace).

## Email notifications

Customers receive an email when they place a request, when the library hands the books over
(with the due date), when the library cancels a request, a few days before the due date and once
the books are overdue. Messages are plain text, in English followed by Russian.

- **Outbox:** a row in `notifications` is written in the same transaction as the order change, so
  an email is never lost or sent for a change that was rolled back. Each event happens at most once
  per order.
- **Delivery:** `python -m app.cli notifications` queues due-date reminders and sends pending emails
  over SMTP (5 attempts with exponential backoff; messages older than 7 days expire).
  `--loop SECONDS` keeps it running; Docker Compose runs it as the `notifier` service.
- **Development:** all mail goes to Mailpit, nothing leaves your machine: http://localhost:8025.
- **Production:** set the `SMTP_*` variables and `MAIL_FROM` (see the table above). Without
  `SMTP_HOST` notifications stay queued and nothing is sent.

## Deployment

Production runs on a single VM with `docker-compose.prod.yml`: Caddy (automatic HTTPS, static
frontend, `/api` reverse proxy), FastAPI and PostgreSQL, with only ports 80/443 exposed.
Step-by-step guide for a free Oracle Cloud VM, including backups and updates:
[deploy/README.md](deploy/README.md).

## Troubleshooting

- **`port is already allocated` for 5432/5433** — set a different `POSTGRES_PORT` in `.env` and update `DATABASE_URL`.
- **Reloading the page sends you back to /login** — the frontend is open on `127.0.0.1` while the API is on `localhost`
  (different sites, so the `SameSite=Lax` cookie is not sent), or `JWT_SECRET_KEY` is not set and the backend restarted.
- **CORS error in the console** — the frontend origin is missing from `FRONTEND_ORIGINS` (exact match, no trailing `/`).
- **`409 BOOK_UNAVAILABLE` at checkout** — the book has just been reserved by someone else; the UI lists it and refreshes the cart/catalogue.
- **Tests refuse to run** — `TEST_DATABASE_URL` must point to a database whose name ends with `_test`.
- **`JWT_SECRET_KEY is too weak` in production** — generate one: `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
- **A new `.sql` init script did not run** — PostgreSQL init scripts only run on an empty volume (`docker compose down -v` deletes the data).
