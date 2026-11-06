# Little Dragon — онлайн-библиотека

[![CI](https://github.com/igorpertsev/librarium/actions/workflows/ci.yml/badge.svg)](https://github.com/igorpertsev/librarium/actions/workflows/ci.yml)

[English](README.md) | **Русский**

> Основная документация — на английском ([README.md](README.md)); этот перевод может отставать.

Frontend: React + TypeScript + Vite (дизайн из [Figma](https://www.figma.com/design/3D9jREiGTmIKNYLFQXjh7o/Online-library-website)).
Backend: FastAPI + PostgreSQL (`backend/`).

## Скриншоты

| Каталог | Карточка книги |
| --- | --- |
| ![Каталог со статусами доступности](docs/screenshots/catalog.jpg) | ![Окно с описанием книги](docs/screenshots/book-details.jpg) |
| **Корзина: книги выдаются партиями** | **Профиль: заявки и взятые книги** |
| ![Корзина с полной и неполной партией](docs/screenshots/cart.jpg) | ![Профиль читателя](docs/screenshots/profile.png) |
| **Админ-панель** | **Управление заказами** |
| ![Админ-панель с настройкой партий и статистикой](docs/screenshots/admin.png) | ![Вкладка заказов со статусами](docs/screenshots/admin-orders.png) |

Страница входа: [docs/screenshots/login.png](docs/screenshots/login.png). Сняты на демо-данных при ширине 1280 px.

## Требования

| Инструмент | Версия | Для чего |
| --- | --- | --- |
| Docker + Docker Compose | 24+ / v2 | PostgreSQL, backend, тесты |
| Node.js | 20+ | frontend |
| pnpm | 9+ (`corepack enable`) | frontend-зависимости (`pnpm-lock.yaml`) |
| Python 3.12 + [uv](https://docs.astral.sh/uv/) | опционально | запуск backend без Docker |

## Архитектура

```
browser ──► Vite dev server (:5173)  React SPA, i18next (en/ru)
   │            src/api/client.ts   fetch + access token в памяти + 1 refresh на 401
   │            src/api/mappers.ts  DTO (OpenAPI) ⇄ UI-модели (src/app/types.ts)
   ▼
FastAPI (:8000)  /api/v1/...        routes → services → repositories → SQLAlchemy 2 (async)
   ▼
PostgreSQL 16 (:5433 на хосте)      схема только через Alembic
```

```
backend/
  app/
    api/            dependencies.py (сессия, auth, роли), router.py, routes/*.py
    core/           config.py (pydantic-settings), database.py, security.py, exceptions.py
    models/         SQLAlchemy-модели + enums.py (ACTIVE_ORDER_STATUSES)
    schemas/        Pydantic 2: create/update/read отдельно
    repositories/   запросы (фильтры, вычисление резервирования)
    services/       бизнес-логика и транзакции (orders.py — оформление заказа)
    cli.py          seed / export-openapi / purge-tokens
  alembic/          миграции (async env.py)
  tests/            pytest + httpx, реальная PostgreSQL (`bookstore_test`)
src/api/            клиент API, сгенерированные типы, мапперы
```

## Быстрый старт (Docker Compose)

```bash
cp .env.example .env
```

```bash
docker compose up -d --build
```

Поднимутся `db` (PostgreSQL с healthcheck), `migrate` (одноразово `alembic upgrade head`) и `backend`.

```bash
curl http://localhost:8000/api/v1/health
```

Создать администратора и демо-книги (повторный запуск безопасен):

```bash
docker compose run --rm -e SEED_ADMIN_PASSWORD='придумайте-длинный-пароль' backend python -m app.cli seed --demo-books
```

Frontend:

```bash
pnpm install
```

```bash
pnpm dev
```

Откройте http://localhost:5173 (именно `localhost`, не `127.0.0.1` — см. «Типичные ошибки»).
Swagger UI: http://localhost:8000/docs.

## Переменные окружения

Backend читает переменные окружения или `backend/.env` (шаблон `backend/.env.example`);
Docker Compose и Vite — корневой `.env` (шаблон `.env.example`). Заполненные `.env` не коммитятся.

| Переменная | По умолчанию | Описание |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `development` / `test` / `production` |
| `LOG_LEVEL`, `LOG_FORMAT` | `INFO`, json в production / text иначе | одна строка на запись, с id запроса |
| `SENTRY_DSN` | — | необязательно: отправка необработанных ошибок в Sentry или совместимый сервис; персональные данные не отправляются |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5433/bookstore` | `postgres://` и `postgresql://` приводятся к asyncpg |
| `JWT_SECRET_KEY` | — | **обязателен в production**, ≥ 32 символов, не из списка слабых; в dev без него генерируется временный секрет |
| `JWT_ALGORITHM` | `HS256` | HS256/384/512 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | 1–60 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | 1–180 |
| `REFRESH_COOKIE_NAME` | `refresh_token` | |
| `COOKIE_SECURE` | `false` | в production обязан быть `true` |
| `COOKIE_SAMESITE` | `lax` | `none` допустим только с `COOKIE_SECURE=true` |
| `FRONTEND_ORIGINS` | `http://localhost:5173` | точные origins через запятую; `*` запрещён |
| `RATE_LIMIT_ENABLED` | `true` | ограничения на вход, регистрацию, обновление токена и смену пароля |
| `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` | — | для `app.cli seed`, пароль ≥ 12 символов |
| `TEST_DATABASE_URL` | `…/bookstore_test` | только для тестов; имя БД обязано оканчиваться на `_test` |
| `VITE_API_URL` | `http://localhost:8000/api/v1` | адрес API для frontend |
| `PASSWORD_RESET_EXPIRE_MINUTES` | `60` | срок действия ссылки для сброса пароля (5–1440) |

В production приложение не стартует при отсутствующем/слабом `JWT_SECRET_KEY`, `COOKIE_SECURE=false`
или `http://` в `FRONTEND_ORIGINS`.

## Backend без Docker

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

## Миграции

Все команды можно выполнять через контейнер `backend-dev` (профиль `dev`, исходники смонтированы):

```bash
docker compose --profile dev run --rm backend-dev alembic upgrade head
```

```bash
docker compose --profile dev run --rm backend-dev alembic downgrade -1
```

```bash
docker compose --profile dev run --rm backend-dev alembic revision --autogenerate -m "описание"
```

```bash
docker compose --profile dev run --rm backend-dev alembic check
```

`alembic check` должен печатать `No new upgrade operations detected.` — модели и миграции совпадают.
Приложение никогда не вызывает `metadata.create_all()`.

## Seed

`python -m app.cli seed [--demo-books] [--reset-admin-password]`:

- создаёт/активирует администратора из `SEED_ADMIN_EMAIL` + `SEED_ADMIN_PASSWORD` (пароль в коде не хранится);
  пароль существующего админа меняется только с `--reset-admin-password`;
- `--demo-books` добавляет 16 книг из `backend/app/seed_data/demo_books.json`; в production отказывается работать;
- `--refresh-demo-covers` (вместе с `--demo-books`) обновляет обложки уже существующих демо-книг
  (демо-данные используют настоящие обложки из Open Library);
- гарантирует строку настроек библиотеки. Повторный запуск ничего не дублирует.

## Тесты, lint, typecheck

Backend (PostgreSQL из compose, отдельная БД `bookstore_test`, создаётся init-скриптом/фикстурой):

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

`pnpm lint` — ESLint (правила TypeScript и React hooks, `eslint.config.js`); `pnpm test` запускает unit-тесты
Vitest (`src/**/*.test.ts`, jsdom): обновление токена и повтор запроса в API-клиенте, мапперы DTO, форматирование
дат и сумм, тексты ошибок. `pnpm test:watch` перезапускает их при изменениях.

**Браузерные тесты** (Playwright, `e2e/`) проверяют настоящее приложение: регистрацию и вход, заказ партии через
корзину, подтверждение и возврат библиотекарем, книги, занятые другим читателем, добавление/изменение/удаление книги,
переключение на русский и проверку доступности axe на основных страницах. Они работают с отдельным временным стеком
(`e2e/docker-compose.yml`: БД в памяти, демо-книги, e2e-администратор, backend на порту 8100) и сервером Vite на
порту 4173, который Playwright запускает сам, поэтому данные разработки не затрагиваются.

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

Вместо загрузки Chromium можно использовать установленный Google Chrome: `PLAYWRIGHT_CHANNEL=chrome pnpm e2e`.
Упавшие тесты оставляют скриншоты и трассировки в `test-results/` (`pnpm exec playwright show-trace <файл>`).

Тесты прогоняют миграции `upgrade → downgrade base → upgrade`, перед каждым тестом очищают таблицы и не
оборачивают тест в транзакцию — поэтому конкурентные запросы реально идут через разные соединения.

**Непрерывная интеграция** (`.github/workflows/ci.yml`) запускается для каждого pull request и при push в `main`:

- *Backend*: `ruff format --check`, `ruff check`, `mypy`, `alembic upgrade head` + `alembic check` + `downgrade base`,
  `pytest` на сервисе PostgreSQL 16 и проверка, что `backend/openapi.json` соответствует коду.
- *Frontend*: `pnpm install --frozen-lockfile`, проверка, что `src/api/generated/schema.d.ts` соответствует
  `backend/openapi.json`, `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build`.
- *Браузерные тесты*: e2e-стек, Chromium и `pnpm e2e`; при ошибке выгружается отчёт Playwright.
- *Production-образы*: `docker compose -f docker-compose.prod.yml build`.

Поэтому после изменения API коммитьте экспортированный `backend/openapi.json` и перегенерированные типы вместе.

## Генерация TypeScript-типов из OpenAPI

Из запущенного backend:

```bash
pnpm api:types
```

Или из сохранённой схемы (без сервера):

```bash
docker compose --profile dev run --rm --no-deps backend-dev python -m app.cli export-openapi openapi.json
```

```bash
pnpm api:types:file
```

Результат — `src/api/generated/schema.d.ts`; **не редактируйте его вручную**. Алиасы DTO — `src/api/types.ts`,
преобразование в UI-модели — `src/api/mappers.ts`. После изменения API: экспорт схемы → генерация → `pnpm typecheck`.

## Аутентификация

- **Пароли** — Argon2id (`argon2-cffi`), хеширование в thread pool, прозрачный rehash при входе.
- **Access token** — JWT (HS256), 15 минут, claims `sub`, `role`, `type`, `jti`, `iat`, `nbf`, `exp`, `iss`, `aud`.
  Передаётся в `Authorization: Bearer`. Frontend держит его только в памяти.
  Роль для авторизации всегда читается из БД, claim `role` — справочный.
- **Refresh token** — случайная строка (`secrets.token_urlsafe(48)`), в БД хранится только SHA-256.
  Лежит в cookie `refresh_token`: `HttpOnly`, `Secure` (из env), `SameSite=Lax`, `Path=/api/v1/auth`.
  В JSON никогда не возвращается.
- **Ротация**: каждый `POST /auth/refresh` выдаёт новый токен той же «семьи» и отзывает старый
  (`replaced_by_token_id`). Повторное предъявление отозванного токена = кража → отзывается вся семья
  (`REFRESH_TOKEN_REUSED`).
- **Сброс пароля**: `POST /auth/forgot-password` отправляет ссылку (`APP_BASE_URL/reset-password#token=…`) активной
  учётной записи и отвечает `202` независимо от того, зарегистрирован ли адрес. Токен — подписанный JWT со своей
  audience; в базе ничего не хранится. Он истекает через `PASSWORD_RESET_EXPIRE_MINUTES` (по умолчанию 60) и содержит
  отпечаток текущего хеша пароля, поэтому перестаёт работать после смены пароля (одно использование).
  `POST /auth/reset-password` задаёт новый пароль и отзывает все сессии (иначе `INVALID_RESET_TOKEN`).
  Письмо отправляет сам API сразу (не через очередь notifier); без `SMTP_HOST` оно не отправляется.
- **Logout** отзывает текущий refresh token и удаляет cookie. **Смена пароля** отзывает все сессии
  и выдаёт новую семью. **Блокировка** пользователя (`is_active=false`) отзывает его refresh-токены,
  а access-токены перестают работать сразу (`ACCOUNT_DISABLED`).
- Ошибки входа одинаковы для «нет такого email» и «неверный пароль»; при отсутствующем пользователе
  всё равно выполняется проверка Argon2 (нет утечки по времени).
- Cookie-эндпоинты (`/auth/*`) дополнительно отклоняют запросы с чужим `Origin` (`ORIGIN_NOT_ALLOWED`).
- **Ограничения частоты** (`app/core/rate_limit.py`) отвечают `429 TOO_MANY_REQUESTS` с заголовком `Retry-After`
  и `details.retry_after` в секундах:

  | Что | Лимит |
  | --- | --- |
  | Неудачные входы на один email (успешный вход их сбрасывает) | 10 за 15 минут |
  | Попытки входа с одного IP | 30 за 5 минут |
  | Регистрации с одного IP | 10 в час |
  | Обновления токена с одного IP | 120 за 5 минут |
  | Неверный текущий пароль при смене пароля, на пользователя | 5 за 15 минут |
  | Письма для сброса пароля с одного IP / на один email | 10 / 3 в час |
  | Попытки задать пароль по ссылке сброса с одного IP | 20 за 15 минут |

  Счётчики хранятся в памяти, что подходит для одного процесса backend в Docker-стеках; при нескольких
  процессах каждый считал бы отдельно. За Caddy IP клиента берётся из `X-Forwarded-For` (uvicorn `--proxy-headers`).
  Неудачные входы на email блокируют и его владельца до 15 минут — обычный компромисс против подбора пароля.

**Frontend-поток**: при загрузке страницы `POST /auth/refresh` восстанавливает сессию по cookie;
на 401 клиент делает один общий refresh и повторяет запрос один раз; refresh сам по себе не вызывает
refresh (нет цикла); при неудаче auth-состояние очищается. Между вкладками refresh сериализуется
через Web Locks API, чтобы две вкладки не предъявили один и тот же токен.

## CORS

Только origins из `FRONTEND_ORIGINS`, `allow_credentials=True`, методы `GET/POST/PATCH/DELETE`,
заголовки `Authorization`, `Content-Type`. Wildcard `*` отклоняется на старте.

**Заголовки безопасности.** Ответы API содержат `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, `Cache-Control: no-store` и `Content-Security-Policy: default-src 'none'`.
В production Caddy добавляет HSTS и Content-Security-Policy для самого приложения (см. `deploy/README.md`).

**Id запросов и логи.** У каждого ответа есть заголовок `X-Request-ID` (корректный id от прокси сохраняется, иначе
создаётся новый). Тот же id есть в каждой строке лога этого запроса, включая строку доступа (`app.request`: метод,
путь без query-строки, статус, длительность, IP клиента), и в `details` ответов `500 INTERNAL_ERROR`; frontend
показывает его как код ошибки, чтобы обращение пользователя можно было сопоставить с логами. В production логи —
строки JSON (`docker compose -f docker-compose.prod.yml logs backend`).

## Правила резервирования книг

Каждая запись `Book` — **один физический экземпляр** (так работает существующий UI:
`isBookUnavailable(bookId)`, нет количества). Поэтому резервирование — на уровне `book_id`;
две копии одного издания — две записи (ISBN не уникален).

- Активные статусы заказа: `ACTIVE_ORDER_STATUSES = {pending, confirmed}` (`app/models/enums.py`).
  `returned` и `cancelled` книгу освобождают.
- Книга блокируется **любым** активным заказом, включая заказ того же пользователя (как в UI).
- Корзина — не резерв: одна книга может лежать в корзинах нескольких пользователей; добавление
  проверяет доступность, но решающая проверка — при оформлении заказа.
- Цена — за **партию**: `price_per_batch` за каждые полные `books_per_batch` книг (настройки
  библиотеки, админ-карточка «Batch Configuration»). В заказ попадают полные партии в порядке
  добавления; книги неполной последней партии остаются в корзине.

**Продление выдачи**: `POST /orders/{id}/renew` переносит срок возврата выданного (`confirmed`) заказа на
`loan_period_days`, не более `max_renewals` раз на заказ (настройки библиотеки, по умолчанию 1; 0 — продление
отключено) и никогда после просрочки (`409 RENEWAL_NOT_ALLOWED`, `details.reason`). Уже отправленные напоминания
о старом сроке удаляются, поэтому перед новым сроком читатель получит напоминание снова.

**Лист ожидания**: для книги, которую сейчас нельзя заказать, `POST /waitlist/{book_id}` (идемпотентно;
`409 BOOK_AVAILABLE`, если её можно заказать) просит прислать письмо, когда она вернётся. Когда заказ возвращён
или отменён либо библиотекарь ставит книге статус `available`, все ждущие доступную теперь книгу получают одно
письмо `book_available` (через outbox уведомлений), а их записи удаляются; книга достаётся тому, кто закажет первым.
Письмо не отправляется, если книгу успели снова заказать. Пока кто-то ждёт книгу, её текущий читатель не может
продлить выдачу (`details.reason = requested_by_others`).

`POST /api/v1/orders` выполняется в одной транзакции (`app/services/orders.py`):

1. `SELECT … FOR UPDATE` строки корзины (защита от двойного клика/двух вкладок);
2. пустая корзина → `400 CART_EMPTY`, нет полной партии → `400 INCOMPLETE_BATCH`;
3. `SELECT … FOR SHARE` настроек, `SELECT … FOR UPDATE` книг **в порядке id** (без дедлоков);
4. проверка активности книги, статуса `available` и активных заказов (только `ACTIVE_ORDER_STATUSES`);
5. при конфликте — исключение, откат всей транзакции, `409 BOOK_UNAVAILABLE` со списком книг;
6. сумма считается только на сервере; позиции получают снимок названия/автора/ISBN/обложки и цену
   (цена партии делится на копейки без потерь);
7. заказанные позиции удаляются из корзины, commit.

Второй уровень защиты — частичный уникальный индекс
`uq_order_items_active_book ON order_items(book_id) WHERE reservation_active`: даже код без блокировки
не сможет создать вторую активную резервацию (тест `test_partial_unique_index_stops_the_race_even_without_row_locks`).
Конкурентность проверяется тестами, где оба запроса синхронизированы барьером прямо перед `FOR UPDATE`.

## Модель данных и расхождения с frontend

| Таблица | Ключевое |
| --- | --- |
| `users` | email уникален и в нижнем регистре (CHECK), Argon2-хеш, роль `customer/admin`, контакты (nullable), `preferred_contact_method` |
| `books` | `cover_url`, `image_urls[]`, `age_range`, `category`, `status` (`available/available-soon/not-available`), `language`, `publication_year`, `is_active` (мягкое удаление) |
| `library_settings` | одна строка: `books_per_batch`, `price_per_batch NUMERIC(10,2)`, `currency`, `loan_period_days` |
| `carts`, `cart_items` | одна корзина на пользователя, `UNIQUE(cart_id, book_id)` |
| `orders` | статус, сумма/валюта, снимок цены партии и контактов, `due_date`, `confirmed_at/returned_at/cancelled_at`, CHECK `total = price × batches` |
| `order_items` | снимок книги и `unit_price`, `reservation_active` + частичный уникальный индекс |
| `refresh_tokens` | `token_hash`, `family_id`, `expires_at`, `revoked_at`, `replaced_by_token_id`, user-agent/IP |

Перечисления хранятся как `VARCHAR + CHECK` (меняются без `ALTER TYPE`). Деньги — `NUMERIC`, в JSON — строки (`"15.99"`).

Расхождения (адаптеры в `src/api/mappers.ts`):

- В UI нет цены книги — есть цена партии; поэтому у `Book` нет `price`, цена живёт в `library_settings` и в снимке заказа.
- Статусы заказа взяты из UI (`pending/confirmed/returned/cancelled`) вместо `processing/completed`.
- `coverImage/images/publishedYear/ageRange` ⇄ `cover_url/image_urls/publication_year/age_range`;
  статус книги `pending` в UI означает «в моей корзине» и на сервере не хранится.
- `preferred_contact_method` на сервере допускает `email`; в UI такого варианта нет — отображается как «не выбран».
- `User.borrowedBooks` собирается из подтверждённых заказов (`active_loans` в `/admin/users`).
- Добавлены необязательные поля UI-моделей: `Book.isReserved/isAvailable/language`, `Order.currency/contacts`.

## API (`/api/v1`)

| Метод | Путь | Доступ |
| --- | --- | --- |
| GET | `/health` (liveness), `/api/v1/health` (DB) | все |
| POST | `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/forgot-password`, `/auth/reset-password` | все |
| GET | `/auth/me`, `/users/me` · PATCH `/users/me` · POST `/auth/change-password` | пользователь |
| GET | `/books?q&category&age_range&available&sort&page&page_size`, `/books/age-ranges`, `/books/{id}` | все |
| GET/DELETE | `/cart` · POST `/cart/items` · DELETE `/cart/items/{book_id}` | пользователь |
| POST/GET | `/orders` · GET `/orders/{id}` · POST `/orders/{id}/cancel`, `/orders/{id}/renew` | пользователь (только свои) |
| GET | `/library/rules` (размер и цена партии, срок выдачи, число продлений) | все |
| GET `/waitlist` · POST/DELETE `/waitlist/{book_id}` | «сообщите, когда книга вернётся» | пользователь |
| GET/POST | `/admin/books`, GET `/admin/books/stats`, GET/PATCH/DELETE `/admin/books/{id}` | admin |
| POST | `/admin/books/import` (CSV, всё или ничего, `dry_run`), GET `/admin/isbn/{isbn}` (данные из Open Library) | admin |
| GET | `/admin/users` · PATCH `/admin/users/{id}` (роль, блокировка) | admin |
| GET | `/admin/orders`, `/admin/orders/{id}` · PATCH `/admin/orders/{id}/status`, `/admin/orders/{id}/due-date` | admin |
| GET/PATCH | `/admin/settings` (партия, цена, валюта, срок выдачи) | admin |

Сортировка книг — только из списка: `title`, `author`, `publication_year`, `created_at` (с `-` для убывания).
Переходы статусов: `pending → confirmed | cancelled`, `confirmed → returned`; клиент может отменить только `pending`.

Формат ошибок (единый для всех статусов):

```json
{"error": {"code": "BOOK_UNAVAILABLE", "message": "One or more books are unavailable",
           "details": {"book_ids": ["…"], "books": [{"id": "…", "title": "…"}]}}}
```

400 `CART_EMPTY`/`INCOMPLETE_BATCH`/`INVALID_CURRENT_PASSWORD`, 401 `NOT_AUTHENTICATED`/`INVALID_CREDENTIALS`/`TOKEN_EXPIRED`/`REFRESH_TOKEN_*`,
403 `FORBIDDEN`/`ACCOUNT_DISABLED`, 404 `*_NOT_FOUND`, 409 `BOOK_UNAVAILABLE`/`EMAIL_ALREADY_EXISTS`/`INVALID_STATUS_TRANSITION`,
422 `VALIDATION_ERROR` (без эха введённых значений), 500 `INTERNAL_ERROR` (без stack trace).

## Email-уведомления

Читатели получают письмо, когда оформляют заявку, когда библиотека выдаёт книги (со сроком
возврата), когда библиотека отменяет заявку, за несколько дней до срока возврата и при просрочке.
Письма текстовые, на английском и русском.

- **Outbox:** запись в `notifications` создаётся в той же транзакции, что и изменение заказа, —
  письмо не теряется и не уходит для отменённого изменения. Каждое событие — не больше одного раза
  на заказ.
- **Просроченные выдачи:** во вкладке «Заказы» админки есть фильтр *Просрочено* (и счётчик в статистике);
  *Напомнить* (`POST /admin/orders/{id}/remind`) сразу ставит в очередь письмо о просрочке или скором сроке,
  не чаще раза в 24 часа на заказ (`409 REMINDER_RECENTLY_SENT`).
- **Отправка:** `python -m app.cli notifications` ставит напоминания и отправляет письма по SMTP
  (5 попыток с экспоненциальной задержкой; письма старше 7 дней не отправляются). `--loop SECONDS`
  повторяет команду; в Docker Compose это сервис `notifier`.
- **Разработка:** вся почта уходит в Mailpit и никуда дальше: http://localhost:8025.
- **Production:** задайте переменные `SMTP_*` и `MAIL_FROM`. Без `SMTP_HOST` письма остаются в
  очереди и не отправляются.

## Развёртывание

Production — одна VM с `docker-compose.prod.yml`: Caddy (автоматический HTTPS, статический
frontend, прокси `/api`), FastAPI и PostgreSQL; наружу открыты только порты 80/443.
Пошаговая инструкция для бесплатной VM в Oracle Cloud, включая бэкапы и обновления
(на английском): [deploy/README.md](deploy/README.md). Бэкапы: `deploy/backup.sh` (ежедневный дамп,
необязательная копия вне VM через rclone) и `deploy/verify-backup.sh` (проверка восстановления во временном контейнере).

## Типичные ошибки

- **`port is already allocated` для 5432/5433** — задайте другой `POSTGRES_PORT` в `.env` и обновите `DATABASE_URL`.
- **После перезагрузки страницы выкидывает на /login** — frontend открыт на `127.0.0.1`, а API на `localhost`
  (разные сайты, cookie `SameSite=Lax` не отправляется) или не задан `JWT_SECRET_KEY` и backend перезапускался.
- **CORS-ошибка в консоли** — origin фронтенда не указан в `FRONTEND_ORIGINS` (точное совпадение, без `/` в конце).
- **`409 BOOK_UNAVAILABLE` при оформлении** — книгу уже зарезервировали; UI показывает список и обновляет корзину/каталог.
- **Тесты отказываются запускаться** — `TEST_DATABASE_URL` должен указывать на БД с суффиксом `_test`.
- **`JWT_SECRET_KEY is too weak` в production** — сгенерируйте: `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
- **Новый `.sql` init-скрипт не применился** — init-скрипты PostgreSQL выполняются только на пустом volume (`docker compose down -v` удалит данные).
