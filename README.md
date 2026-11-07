# Little Dragon — online library

[![CI](https://github.com/igorpertsev/librarium/actions/workflows/ci.yml/badge.svg)](https://github.com/igorpertsev/librarium/actions/workflows/ci.yml)

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
| `LOG_LEVEL`, `LOG_FORMAT` | `INFO`, json in production / text otherwise | one line per record with the request id |
| `SENTRY_DSN` | — | optional: report unhandled errors to Sentry or a compatible service; no personal data is sent |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5433/bookstore` | `postgres://` and `postgresql://` are normalised to asyncpg |
| `JWT_SECRET_KEY` | — | **required in production**, ≥ 32 characters, not a known weak value; in development an ephemeral secret is generated if empty |
| `JWT_ALGORITHM` | `HS256` | HS256/384/512 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | 1–60 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | 1–180 |
| `REFRESH_COOKIE_NAME` | `refresh_token` | |
| `COOKIE_SECURE` | `false` | must be `true` in production |
| `COOKIE_SAMESITE` | `lax` | `none` is only allowed with `COOKIE_SECURE=true` |
| `FRONTEND_ORIGINS` | `http://localhost:5173` | exact origins, comma-separated; `*` is rejected |
| `RATE_LIMIT_ENABLED` | `true` | limits on login, registration, token refresh and password changes |
| `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` | — | used by `app.cli seed`, password ≥ 12 characters |
| `TEST_DATABASE_URL` | `…/bookstore_test` | tests only; the database name must end with `_test` |
| `VITE_API_URL` | `http://localhost:8000/api/v1` | API base URL for the frontend |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_STARTTLS`, `SMTP_SSL`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAIL_FROM` | empty / `587` / `true` / `false` | outgoing email; empty `SMTP_HOST` disables sending |
| `APP_BASE_URL`, `DUE_SOON_DAYS` | `http://localhost:5173`, `3` | links in emails; reminder lead time in days |
| `MEDIA_DIR`, `MAX_COVER_BYTES` | `media`, `5242880` | where uploaded covers are kept (the `media` volume, `/app/media`, in Docker); upload limit |
| `PASSWORD_RESET_EXPIRE_MINUTES` | `60` | lifetime of password reset links (5–1440) |
| `ANTHROPIC_API_KEY`, `TRANSLATION_MODEL` | —, `claude-opus-5-5` | optional machine translation of book titles and descriptions when Wikidata and Wikipedia have none; without a key only those two are used |

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
- `--demo-books` adds 19 books from `backend/app/seed_data/demo_books.json`, with tags and two series (*Harry Potter*,
  *The Hunger Games*); demo books loaded before tags existed get their tags and series unless they were edited since;
  starter tags a librarian deleted are skipped; every demo book has a Russian title, author and description
  (added to demo books loaded earlier that have no translation); refuses to run in production;
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
pnpm lint
```

```bash
pnpm typecheck
```

```bash
pnpm test
```

```bash
pnpm build
```

`pnpm lint` is ESLint (TypeScript and React hooks rules, `eslint.config.js`); `pnpm test` runs the Vitest unit
tests (`src/**/*.test.ts`, jsdom): the API client's refresh-and-retry logic, the DTO mappers, date/money
formatting and error messages. `pnpm test:watch` reruns them on change.

**Browser tests** (Playwright, `e2e/`) drive the real app: registration and sign-in, borrowing a batch through
checkout, confirmation and return by the librarian, books taken by another reader, adding/editing/deleting a book,
switching to Russian, and an axe accessibility audit of the main pages. They run against a separate, throwaway
stack (`e2e/docker-compose.yml`: database in memory, demo books, an e2e admin, backend on port 8100) and a Vite
server on port 4173 that Playwright starts itself, so your development data is never touched.

```bash
pnpm e2e:stack
```

```bash
pnpm exec playwright install chromium
```

```bash
pnpm e2e
```

```bash
pnpm e2e:stack:down
```

Instead of downloading Chromium you can use an installed Google Chrome: `PLAYWRIGHT_CHANNEL=chrome pnpm e2e`.
Failed tests leave screenshots and traces in `test-results/` (`pnpm exec playwright show-trace <file>`).

The test session runs migrations `upgrade → downgrade base → upgrade`, truncates tables before each test and does
not wrap tests in a transaction, so concurrent requests really go through separate database connections.

**Continuous integration** (`.github/workflows/ci.yml`) runs on every pull request and on pushes to `main`:

- *Backend*: `ruff format --check`, `ruff check`, `mypy`, `alembic upgrade head` + `alembic check` + `downgrade base`,
  `pytest` against a PostgreSQL 16 service, and a check that `backend/openapi.json` matches the code.
- *Frontend*: `pnpm install --frozen-lockfile`, a check that `src/api/generated/schema.d.ts` matches
  `backend/openapi.json`, `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build`.
- *Browser tests*: the e2e stack, Chromium and `pnpm e2e`; the Playwright report is uploaded when they fail.
- *Production images*: `docker compose -f docker-compose.prod.yml build`.

So after an API change, commit the exported `backend/openapi.json` and the regenerated types together.

**Code splitting.** Pages other than sign-in are loaded when first opened (`lazy` routes in `src/app/routes.tsx`);
React and i18next get their own long-cached files (`vite.config.ts`). If an open tab asks for page files that a new
release has replaced, it reloads once to get the new version.

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
- **Two-step sign-in** — optional for every account (profile → *Two-step sign-in*): confirm the password
  (`POST /users/me/mfa/setup`), scan the `otpauth://` QR code with an authenticator app, confirm with a code
  (`/users/me/mfa/enable`) and keep the ten recovery codes it returns (shown once, stored as SHA-256 hashes, each
  works once). TOTP per RFC 6238 (SHA-1, 6 digits, 30 s, ±1 step); a code is never accepted twice. Secrets are
  encrypted (Fernet, key derived from `JWT_SECRET_KEY` with HKDF), so changing `JWT_SECRET_KEY` turns every
  user's two-step sign-in unusable — reset it for them or let them set it up again. With it on, `/auth/login`
  answers `403 MFA_REQUIRED` with `details.mfa_token` (5 minutes) and `/auth/login/mfa` takes that token and a
  code or recovery code (rate-limited like the password). Administrators can require it for staff (setting
  `require_staff_mfa`; only after turning it on for themselves): staff without it get `403 MFA_SETUP_REQUIRED`
  from the admin API until they set it up. Administrators reset it for a user who lost their phone and codes
  (`PATCH /admin/users/{id}` `{"reset_mfa": true}`).
- **Roles** — `customer`, `librarian`, `admin`. Librarians use the admin portal for books, copies, imports, orders,
  reviews, tags and series, data quality and reports. Changing users and roles, library settings and pickup points,
  and reading the activity log need an administrator (`ADMIN_ONLY` in `app/api/routes/admin.py`). Administrators
  change roles on the *Users* tab; staff accounts cannot be deleted by their owners (`ADMIN_ACCOUNT`).
- **Activity log** — every successful `POST/PUT/PATCH/DELETE` under `/admin` is recorded after it succeeded (router
  dependency `audit_trail`): who, which endpoint, which record (the first id in the path) and the request body,
  with passwords and tokens redacted and long values shortened. Failed requests and reads are not logged.
  Administrators read it on the *Activity* tab (`GET /admin/audit`, `actor_id` filter); the actor's email is kept
  even if the account is deleted later.
- **Refresh token** — random string (`secrets.token_urlsafe(48)`); only its SHA-256 hash is stored.
  It lives in the `refresh_token` cookie: `HttpOnly`, `Secure` (from env), `SameSite=Lax`, `Path=/api/v1/auth`.
  It is never returned in JSON.
- **Rotation**: every `POST /auth/refresh` issues a new token in the same “family” and revokes the old one
  (`replaced_by_token_id`). Presenting a revoked token again is treated as theft → the whole family is revoked
  (`REFRESH_TOKEN_REUSED`).
- **Password reset**: `POST /auth/forgot-password` emails a link (`APP_BASE_URL/reset-password#token=…`) to an
  active account and answers `202` whether or not the address is registered. The token is a signed JWT with its
  own audience; nothing is stored. It expires after `PASSWORD_RESET_EXPIRE_MINUTES` and carries a fingerprint
  of the current password hash, so it stops working once the password has changed (one use).
  `POST /auth/reset-password` sets the new password and revokes every session (`INVALID_RESET_TOKEN` otherwise).
  The email is sent right away by the API (not through the notifier queue); without `SMTP_HOST` it is not sent.
- **Logout** revokes the current refresh token and deletes the cookie. **Changing the password** revokes all sessions
  and issues a new family. **Disabling** a user (`is_active=false`) revokes their refresh tokens, and their
  access tokens stop working immediately (`ACCOUNT_DISABLED`).
- Login errors are identical for “unknown email” and “wrong password”; Argon2 verification runs even when the user
  does not exist (no timing leak).
- Cookie endpoints (`/auth/*`) additionally reject requests with a foreign `Origin` (`ORIGIN_NOT_ALLOWED`).
- **Rate limits** (`app/core/rate_limit.py`) answer `429 TOO_MANY_REQUESTS` with a `Retry-After` header and
  `details.retry_after` in seconds:

  | What | Limit |
  | --- | --- |
  | Failed logins per email address (a successful login clears them) | 10 per 15 minutes |
  | Login attempts per IP address | 30 per 5 minutes |
  | Registrations per IP address | 10 per hour |
  | Token refreshes per IP address | 120 per 5 minutes |
  | Wrong current passwords when changing the password, per user | 5 per 15 minutes |
  | Password reset emails per IP address / per email address | 10 / 3 per hour |
  | New-password attempts with a reset link per IP address | 20 per 15 minutes |

  The counters are kept in memory, which suits the single backend process of the Docker stacks; with several
  processes each would count separately. Behind Caddy the client IP comes from `X-Forwarded-For`
  (uvicorn `--proxy-headers`). Note that failed logins for an email address also block its owner for up to
  15 minutes; that is the usual trade-off against password guessing.

**Frontend flow**: on page load `POST /auth/refresh` restores the session from the cookie;
on a 401 the client performs one shared refresh and retries the request once; the refresh call never triggers
another refresh (no loop); if refresh fails, the auth state is cleared. Across tabs refreshes are serialised
with the Web Locks API so two tabs never present the same token.

## CORS

Only the origins in `FRONTEND_ORIGINS`, `allow_credentials=True`, methods `GET/POST/PATCH/DELETE`,
headers `Authorization`, `Content-Type`. A `*` wildcard is rejected at startup.

**Security headers.** API responses carry `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, `Cache-Control: no-store` and `Content-Security-Policy: default-src 'none'`.
In production Caddy adds HSTS and a Content-Security-Policy for the app itself (see `deploy/README.md`).

**Request ids and logs.** Every response has an `X-Request-ID` header (a valid id from a proxy is kept, otherwise a
new one is made). The same id appears on every log line written for that request, including one access line per
request (`app.request`: method, path without the query string, status, duration, client IP), and in the `details`
of `500 INTERNAL_ERROR` responses; the frontend shows it as a reference code, so a user's report can be matched with
the logs. In production the logs are JSON lines (`docker compose -f docker-compose.prod.yml logs backend`).

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
- **Search** (`GET /books?q=`): PostgreSQL full-text search over title, author and description (generated
  `search_vector`, `simple` configuration, so English and Russian are treated alike; web-search syntax: `"phrase"`,
  `-word`), substring matches on title, author and ISBN (hyphens ignored), and typo tolerance via `pg_trgm`
  (`word_similarity` ≥ 0.5: “hobit” finds *The Hobbit*). `sort=relevance` ranks the best match first. Tag names
  (English and Russian) and series names (also misspelt) match as well.
- **Tags** (`GET /tags`, filter `GET /books?tags=fantasy,magic`: a book must have **every** listed tag, up to 10):
  a curated list kept by librarians (admin “Tags & series” tab: create, rename, merge, delete), each with an English
  and a Russian name; 20 starter tags come with migration 0009. Tags belong to the title (all copies get them).
  The catalogue keeps the selection in the address bar (`?tags=`).
- **Series** (`GET /series`, `GET /books?series=<id>&sort=series`): a book has at most one series and a volume
  number (`series_position`, may be fractional, e.g. 1.5). The book form, the CSV import and the API take a series
  by name (`series_name`, matched in any case, created when new) or by `series_id`; `series_id: null` takes a book
  out of its series. “Fill in from ISBN” reads the series from the Open Library work record (key and volume, the same
  for every edition and language) or from the edition's free-text series (“Dune chronicles, bk. 1”), stores the
  Open Library key with the series so other editions find it, and suggests tags from the book's subjects. The
  catalogue shows the series on each card (link to the series), lists a series in volume order and can put every
  available volume into the cart (“Take the whole series”).
- **Translations**: a book row keeps the text of the edition on the shelf; `translations` adds its title, author and
  description in the other interface language (`book_translations`, one per language, the same on every copy). The
  catalogue, the book dialog, the cart and the waiting list show the reader's language with the original title next
  to it and a “Language: English” badge, and search finds books by their translated text too. In the book form,
  “Find translation” (`POST /admin/translations/suggest`, nothing is saved) fills the empty fields: the official name
  of the work and its authors from **Wikidata** (matched by the Open Library work of the ISBN, property P648, not by
  title), the first paragraph of the **Wikipedia** article in that language (CC BY-SA: readers see a link to the
  article), and, for what is still missing, **machine translation** with Claude when `ANTHROPIC_API_KEY` is set
  (marked “Translated automatically” until a librarian edits it; a declined request falls back server-side to
  Anthropic's recommended model). `python -m app.cli translate-books --to ru [--no-machine] [--limit 50]` does the
  same for titles without a translation (pausing 1 s between titles); review the results in the admin portal.
  Fantlab is not used: its API documentation states no terms for reusing its user-written texts.
- **Open catalogue**: the catalogue and book pages (`/books/<id>`, opening the book over the catalogue) need no
  account; the cart, profile and admin portal do. A visitor's "Sign in to borrow" comes back to the same page after
  signing in. Link-preview bots get a page with the book's title, description and cover (`/share/books/{id}`).
- The cart is not a reservation: the same book can sit in several users' carts; adding it checks
  availability, but the decisive check happens at checkout.
- Pricing is per **batch**: `price_per_batch` for every complete set of `books_per_batch` books (library
  settings, the admin “Batch Configuration” card). An order contains the complete batches in the order the
  books were added; books of an incomplete trailing batch stay in the cart.
- **Extending a loan**: `POST /orders/{id}/renew` moves the due date of a borrowed (`confirmed`) order by
  `loan_period_days`, at most `max_renewals` times per order (library settings, default 1; 0 turns it off) and
  never once the books are overdue (`409 RENEWAL_NOT_ALLOWED`, `details.reason`). Due-date reminders already sent
  for the old date are dropped, so the customer is reminded again before the new one.
- **Waiting list**: for a book that cannot be ordered now, `POST /waitlist/{book_id}` (idempotent; `409
  BOOK_AVAILABLE` if it can be ordered) asks for an email once it is back. Waiting is per title: any copy of it
  counts. When an order is returned or cancelled, or a librarian sets a book to `available`, everyone waiting for
  a now-orderable title gets one
  `book_available` email (through the notification outbox) and their entries are removed; the first to order
  gets it. The email is dropped if the book is taken again before it is sent. While someone waits for a book,
  its borrower cannot extend the loan (`details.reason = requested_by_others`).
- **Holds**: with `hold_hours` > 0 (library setting, default 48) a returned copy is not announced to everybody: it is
  held for the reader who has waited longest, who gets a `book_held` email and sees it under "Held for you" on the
  profile. Only they can add that copy to the cart until the hold ends; ordering it ends the hold. A hold that runs
  out (the notifier checks every cycle) or that the reader gives up (`DELETE /users/me/holds/{book_id}`) passes to
  the next reader in line. `hold_hours = 0` keeps the old behaviour: everybody waiting is emailed.
- **Late returns**: with `block_overdue` (library setting, default on) a reader with an overdue loan cannot place a
  new order (`409 OVERDUE_LOANS`, `details.orders` lists the order numbers); the profile says so. With
  `late_fee_per_day` > 0 (default 0: no fees), marking an overdue order returned stores `late_fee` = fee × days
  late on the order. The librarian records it as paid or waives it (`PATCH /admin/orders/{id}/late-fee` with
  `{"action": "paid" | "waived"}`; waiving sets the fee to 0; `409 NO_LATE_FEE` if nothing is owed), which sets
  `late_fee_settled_at`. The app does not take payments: the fee is paid at the library.
- **Pickup points**: the library can list where orders are collected (admin tab *Pickup*): name, address, a note,
  weekly opening hours in the library's time zone (`library_settings.timezone`, IANA name, default `UTC`), slot
  length (15–240 minutes) and optionally how many orders fit in a slot. While at least one point is active, checkout
  asks for a point and a slot (`GET /library/pickup-points`, `GET /library/pickup-points/{id}/slots`: the next two
  weeks, from an hour ahead, with `left` places) and `POST /orders` needs `{"pickup_point_id", "pickup_at"}`
  (`400 PICKUP_REQUIRED` / `INVALID_PICKUP_SLOT`, `409 PICKUP_SLOT_FULL`; the point's row is locked so two readers
  cannot take the last place). Cancelled orders free their place. Without active points nothing changes. The
  "order received" email, the profile and the admin order list show the place and time. A point used by orders
  cannot be deleted (`409 PICKUP_POINT_IN_USE`); switch it off instead.
- **Reserve ahead**: a reader can reserve a title for a day from tomorrow to 90 days ahead (book dialog, `POST
  /users/me/reservations` `{book_id, starts_on}`; at most 5 at a time, one per title). A copy is set aside that can
  be free then: no other reservation within a loan period of the day, and not out on a loan due on or after it
  (`409 NO_COPY_FOR_DATE` otherwise). From one loan period before the day nobody else can borrow that copy (the
  catalogue shows it back one loan after the day) and loans of it cannot be extended past the day
  (`requested_by_others`). On the day, or as soon as a late copy is back, the notifier holds it for the reader for
  at least 48 hours (`hold_hours` if longer) and emails them (`reservation_ready`); from there it works like any
  hold. Cancelling (`DELETE /users/me/reservations/{id}`) gives a set-aside copy to the readers waiting for it.
  Librarians see upcoming reservations above the order list (`GET /admin/reservations`). Deleting an account
  drops its holds and reservations and passes those copies on.
- **Book suggestions**: readers suggest books for the library to buy (`/suggestions`, also offered when a search
  finds nothing and on the profile) and vote for each other's ideas (`GET/POST /purchase-requests`, `PUT/DELETE
  /purchase-requests/{id}/vote`). The same book again (ISBN, or title and author in any case) counts as a vote
  (`created: false`); books already in the catalogue are refused (`409 ALREADY_IN_CATALOGUE`); at most 10 open
  suggestions per reader. Staff see them most-voted first on the *Suggestions* tab and mark them ordered, added or
  declined with a note for readers (`PATCH /admin/purchase-requests/{id}`). *Added* needs the book in the catalogue
  (`409 BOOK_NOT_IN_CATALOGUE`) and emails everyone who voted (`purchase_added`, also under the bell).
- **Cover upload**: *Upload cover* in the book form (when editing) takes a JPEG, PNG or WebP up to 5 MB
  (`POST /admin/books/{id}/cover`, multipart `file`). Pillow decodes it (at most 40 megapixels), drops its metadata
  and stores WebP renditions L/M/S (800/400/160 px high) as `media/covers/<random>-<size>.webp`; every copy of the
  title gets `cover_url = /media/covers/<random>-L.webp`, and the previous upload is deleted. The backend serves
  `/media` with long-lived cache headers (Caddy passes `/media/*` to it); the frontend loads the size it needs (S
  in lists, M on cards, L in the dialog). Share previews use the full address (`APP_BASE_URL` + path).
- **Stocktaking** (admin tab, staff): start a count, scan every book on the shelves (the ISBN scanner keeps
  scanning; typed ISBNs work too) or count books without an ISBN by hand (+1/−1). Copies are counted per title. A
  title is expected on the shelf with every active copy that is not out on loan and not marked *not available*.
  The report lists titles with missing or extra copies first, and ISBNs that are not in the catalogue. Finishing
  can mark the copies that were not found *not available* with a note (never copies on loan). One count is open at
  a time (`409 STOCKTAKE_OPEN`); scans are not written to the activity log, starting and finishing are.
- **ISBN scanner**: the camera button next to the ISBN field in the book form reads the barcode on the back of a
  book and runs the Open Library lookup. It uses the browser's `BarcodeDetector` where there is one (Chrome, Edge,
  Android) and otherwise ZXing (`@zxing/browser`, loaded only when scanning). Only ISBN barcodes (EAN-13 978/979
  with a valid check digit) are taken; without a camera the ISBN can be typed in the same dialog. The camera needs
  HTTPS (or localhost) and `Permissions-Policy: camera=(self)`, which Caddy sends.
- **Bulk edit**: in the admin book list, tick titles (or the whole page) and apply one change to every copy of
  them: status, category, condition, add or remove a tag, or remove them from the catalogue (asks first; drops them
  from carts). Unknown tags change nothing (`UNKNOWN_TAGS`).
- **Copy condition**: each copy has a condition (`new/good/worn/damaged`) and an optional note, set in the book
  form and when an order comes back (*Mark Returned* asks how each copy came back; only changed copies are saved).
  It is not shared between copies of a title. Worn and damaged copies are marked in the admin book list, and
  damaged ones are listed under *Data quality* (`quality=damaged`).
- **Notification bell**: the header shows the reader's news — the same events as the emails (`notifications`), even
  when an email could not be sent, except news that went stale before delivery. Opening the list marks it read
  (`read_at`); it refreshes every minute while the tab is visible. Notifications from before the bell existed
  count as read.
- **Reading log and badges**: readers mark titles they finished ("I've read it" in the book dialog or for borrowed
  titles on the profile; `PUT /users/me/reading-log/{book_id}` `{finished_on}`, default today, never in the future;
  per title). The profile shows how many this year and in total, the finished books, and eight badges worked out
  from the log each time (1, 5, 10, 25 books; 3 categories; 2 languages; every title of a series; a book in each
  of the last 3 months), with progress towards the ones not earned yet.

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
| `users` | email unique and lower-case (CHECK), Argon2 hash, role `customer/librarian/admin`, contacts (nullable), `preferred_contact_method` |
| `books` | one row per physical copy: `cover_url`, `image_urls[]`, `age_range`, `category`, `status` (`available/available-soon/not-available`), `condition` (`new/good/worn/damaged`, per copy) + `condition_note`, `language`, `publication_year`, `is_active` (soft delete), `copy_group_id` (copies of one title), `series_id` + `series_position` (CHECK > 0) |
| `tags`, `book_tags` | tag `slug` (unique, CHECK format), `name_en`, `name_ru`; book ↔ tag link table |
| `series` | `name` (unique), `name_en` / `name_ru` (names in each interface language, optional), `description`, `openlibrary_key` (unique, from ISBN lookups) |
| `book_translations` | per book and language (`en`/`ru`): `title`, `author`, `description`, `title_source`/`description_source` (`manual/wikidata/wikipedia/machine`), `source_url` (Wikipedia attribution) |
| `library_settings` | single row: `books_per_batch`, `price_per_batch NUMERIC(10,2)`, `currency`, `loan_period_days`, `max_renewals`, `hold_hours`, `block_overdue`, `late_fee_per_day NUMERIC(10,2)`, `timezone` |
| `reading_log_entries` | reader, copy, `finished_on`, `UNIQUE(user_id, book_id)` (one per title in the service) |
| `stocktakes`, `stocktake_counts` | counts of the shelves (one open at a time: partial unique index); counts per title (`group_id`) or unknown `isbn` |
| `purchase_requests`, `purchase_votes` | readers' suggestions (`status` `open/ordered/added/declined`, `book_id` once added) and one vote per reader |
| `audit_events` | actor (`SET NULL`) and email snapshot, `action`, `method`, `path`, `entity_type`, `entity_id`, `details JSONB` |
| `advance_reservations` | reader, copy, `starts_on`, `status` (`active/fulfilled/cancelled`) |
| `pickup_points` | `name`, `address`, `notes`, `hours JSONB` (`[{weekday, opens, closes}]`), `slot_minutes`, `slot_capacity` (NULL: no limit), `active` |
| `carts`, `cart_items` | one cart per user, `UNIQUE(cart_id, book_id)` |
| `waitlist_entries` | customer waiting for a book, `UNIQUE(user_id, book_id)` |
| `reading_list_entries` | “want to read”, one per reader and title, `UNIQUE(user_id, book_id)` |
| `reviews` | rating 1–5 (CHECK), text, `status` (`pending/published/rejected`), one per reader and title |
| `orders` | status, total/currency, batch price and contact snapshot, `due_date`, `renewal_count`, `confirmed_at/returned_at/cancelled_at`, `late_fee`/`late_fee_settled_at`, `pickup_point_id`/`pickup_at`, CHECK `total = price × batches` |
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
| POST | `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/forgot-password`, `/auth/reset-password` | everyone |
| GET | `/auth/me`, `/users/me` · PATCH `/users/me` · POST `/auth/change-password` | signed-in user |
| GET | `/users/me/next-in-series` (the next volume of each series the reader borrowed from) | signed-in user |
| GET | `/users/me/export` (everything stored about the reader, JSON) · DELETE `/users/me` (`{password}`; orders are kept without name and contacts; 409 `ACTIVE_ORDERS` / `ADMIN_ACCOUNT`) | signed-in user |
| GET | `/books?q&category&age_range&available&tags&series&language&author&sort&page&page_size`, `/books/age-ranges`, `/books/languages`, `/books/{id}`, `/books/{id}/series-neighbours`, `/books/{id}/also-borrowed` (titles borrowed by at least two of the same readers) | everyone |
| GET | `/tags` (with title counts), `/series?q`, `/series/{id}` | everyone |
| GET/DELETE | `/cart` · POST `/cart/items` · DELETE `/cart/items/{book_id}` | signed-in user |
| POST/GET | `/orders` · GET `/orders/{id}` · POST `/orders/{id}/cancel`, `/orders/{id}/renew` | signed-in user (own orders only) |
| GET | `/library/rules` (batch size and price, loan period, extensions per loan, time zone) · `/library/pickup-points`, `/library/pickup-points/{id}/slots` | everyone |
| GET | `/share/books/{id}` (Open Graph page for link previews; Caddy sends bots on `/books/<id>` here) | everyone |
| GET `/waitlist` · POST/DELETE `/waitlist/{book_id}` | “email me when this book is back” | signed-in user |
| GET `/reading-list` · POST/DELETE `/reading-list/{book_id}` | “want to read”: titles kept for later, separate from the cart | signed-in user |
| GET `/books/{id}/reviews` (average and published reviews) · GET/PUT/DELETE `/books/{id}/my-review` (`{rating 1-5, text}`; only after borrowing, 403 `NOT_BORROWED`) | ratings and reviews; text waits for moderation | everyone / signed-in user |
| GET `/admin/reviews?status` · PATCH/DELETE `/admin/reviews/{id}` | moderation (publish, reject) | admin |
| GET `/users/me/recommendations` (titles ranked by the tags of borrowed and saved ones) | “For you” shelf | signed-in user |
| GET `/users/me/holds` · DELETE `/users/me/holds/{book_id}` | books held for the reader; give one up | signed-in user |
| GET/POST `/users/me/reservations` · DELETE `/users/me/reservations/{id}` | reserve a title for a date; cancel | signed-in user |
| GET/POST `/purchase-requests` · PUT/DELETE `/purchase-requests/{id}/vote` | suggest books to buy, vote | signed-in user |
| GET `/users/me/reading-log` · PUT/DELETE `/users/me/reading-log/{book_id}` | finished titles, counts, badges, borrowed titles to log | signed-in user |
| GET `/users/me/notifications` · POST `/users/me/notifications/read` (`{ids}` or nothing for all) | the bell: latest 30 news items of the last 60 days and the unread count | signed-in user |
| GET/POST | `/admin/books`, GET `/admin/books/stats`, GET/PATCH/DELETE `/admin/books/{id}` | admin |
| POST | `/admin/books/import` (CSV, all or nothing, `dry_run`; `warnings` for rows that look like books already there), GET `/admin/isbn/{isbn}` (details from Open Library) | admin |
| GET | `/admin/books/duplicates?isbn&title&author` (titles with the same ISBN, or the same title and author) | admin |
| GET | `/admin/books/quality` (titles without cover, description, tags, ISBN or translation; unchecked machine translations) · `/admin/books?quality=<issue>` lists them | admin |
| GET | `/admin/reports/summary`, `/admin/reports/demand` (longest waiting lists, most saved titles, most borrowed tags), `/admin/reports/orders.csv` (`date_from`, `date_to`; default last 30 days) | admin |
| POST | `/admin/books/{id}/copies` (`{count}`: more copies of a title) | admin |
| POST | `/admin/books/bulk` (`book_ids` ≤ 200 and one or more of `status`, `category`, `condition`, `add_tags`, `remove_tags`, `deactivate`: every copy of each title, all or nothing) | staff |
| POST/PATCH/DELETE | `/admin/tags`, `/admin/tags/{id}` · POST `/admin/tags/{id}/merge`; the same for `/admin/series` | admin |
| POST | `/admin/translations/suggest` (title, author and description in another language; saves nothing) | admin |
| GET | `/admin/users` (staff) · PATCH `/admin/users/{id}` (role, disable) | admin |
| GET | `/admin/audit` (activity log, newest first) | admin |
| GET | `/admin/purchase-requests` · PATCH `/admin/purchase-requests/{id}` (`status`, `librarian_note`) | staff |
| GET/POST | `/admin/stocktakes` · GET `/admin/stocktakes/{id}` (report) · POST `/admin/stocktakes/{id}/scan` `{isbn}`, `/count` `{book_id, delta}`, `/finish` `{mark_missing}` | staff |
| GET/POST | `/admin/pickup-points` · PATCH/DELETE `/admin/pickup-points/{id}` | admin |
| GET | `/admin/reservations` (titles reserved for a date, soonest first) | admin |
| GET | `/admin/orders`, `/admin/orders/{id}` · PATCH `/admin/orders/{id}/status`, `/admin/orders/{id}/due-date`, `/admin/orders/{id}/late-fee` | admin |
| GET/PATCH | `/admin/settings` (batch size, price, currency, loan period) | admin |

Public catalogue responses (`/books…`, `/tags`, `/series…`, `/library/rules`) carry a weak `ETag` with
`Cache-Control: no-cache`: browsers revalidate and get `304 Not Modified` while nothing changed; every other
API response is `no-store`. Cards load Open Library's medium cover size, lists the small one.

Book sorting is allow-listed: `title`, `author`, `publication_year`, `created_at` (prefix `-` for descending),
`relevance`, `series` (volume order).
Status transitions: `pending → confirmed | cancelled`, `confirmed → returned`; customers can only cancel `pending` orders.

Error format (the same for every status):

```json
{"error": {"code": "BOOK_UNAVAILABLE", "message": "One or more books are unavailable",
           "details": {"book_ids": ["…"], "books": [{"id": "…", "title": "…"}]}}}
```

400 `CART_EMPTY`/`INCOMPLETE_BATCH`/`INVALID_CURRENT_PASSWORD`, 401 `NOT_AUTHENTICATED`/`INVALID_CREDENTIALS`/`TOKEN_EXPIRED`/`REFRESH_TOKEN_*`,
400 `UNKNOWN_TAGS` (`details.tags`), 403 `FORBIDDEN`/`ACCOUNT_DISABLED`, 404 `*_NOT_FOUND`, 409 `BOOK_UNAVAILABLE`/`EMAIL_ALREADY_EXISTS`/`INVALID_STATUS_TRANSITION`/`TAG_EXISTS`/`SERIES_EXISTS`,
422 `VALIDATION_ERROR` (submitted values are not echoed back), 500 `INTERNAL_ERROR` (no stack trace).

## Email notifications

Customers receive an email when they place a request, when the library hands the books over
(with the due date), when the library cancels a request, a few days before the due date, once
the books are overdue, and when a book on their waiting list is back. Messages are plain text in the
language the customer chose in the interface (`users.preferred_language`, saved at sign-up and when the
language is changed in Settings), or in English followed by Russian when it is not known.

- **Outbox:** a row in `notifications` is written in the same transaction as the order change, so
  an email is never lost or sent for a change that was rolled back. Each event happens at most once
  per order.
- **Overdue loans:** the admin Orders tab has an *Overdue* filter (and the count in the statistics); *Remind*
  (`POST /admin/orders/{id}/remind`) queues an overdue or due-soon email right away, at most once per order
  every 24 hours (`409 REMINDER_RECENTLY_SENT`).
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
[deploy/README.md](deploy/README.md). Backups: `deploy/backup.sh` (daily dump, optional off-site copy with
rclone) and `deploy/verify-backup.sh` (restore drill in a throwaway container).

## Troubleshooting

- **`port is already allocated` for 5432/5433** — set a different `POSTGRES_PORT` in `.env` and update `DATABASE_URL`.
- **Reloading the page sends you back to /login** — the frontend is open on `127.0.0.1` while the API is on `localhost`
  (different sites, so the `SameSite=Lax` cookie is not sent), or `JWT_SECRET_KEY` is not set and the backend restarted.
- **CORS error in the console** — the frontend origin is missing from `FRONTEND_ORIGINS` (exact match, no trailing `/`).
- **`409 BOOK_UNAVAILABLE` at checkout** — the book has just been reserved by someone else; the UI lists it and refreshes the cart/catalogue.
- **Tests refuse to run** — `TEST_DATABASE_URL` must point to a database whose name ends with `_test`.
- **`JWT_SECRET_KEY is too weak` in production** — generate one: `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
- **A new `.sql` init script did not run** — PostgreSQL init scripts only run on an empty volume (`docker compose down -v` deletes the data).
