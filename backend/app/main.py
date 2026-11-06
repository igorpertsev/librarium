"""Application factory. Run with ``uvicorn app.main:app``.

The schema is managed by Alembic only (``alembic upgrade head``); the app never calls
``metadata.create_all()``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import API_PREFIX, api_router
from app.core.config import Settings, get_settings
from app.core.database import Database
from app.core.etag import ETagMiddleware
from app.core.exceptions import register_exception_handlers
from app.core.http import make_http_client
from app.core.logging import configure_logging, init_sentry, new_request_id, request_id_var
from app.core.rate_limit import RateLimiter
from app.services.notifications import make_smtp_sender
from app.services.openlibrary import OpenLibraryClient
from app.services.translation_lookup import (
    TranslationLookup,
    WikimediaClient,
    make_machine_translator,
)

logger = logging.getLogger("app")
access_logger = logging.getLogger("app.request")

# Health checks run every few seconds; their access lines are only logged at DEBUG.
_QUIET_PATHS = frozenset({"/health", "/api/v1/health"})


def _add_cors_and_caching(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # explicit list, never "*" with credentials
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )
    # The public catalogue revalidates with ETags instead of being downloaded again.
    app.add_middleware(
        ETagMiddleware,
        prefixes=tuple(
            f"{API_PREFIX}{path}" for path in ("/books", "/tags", "/series", "/library/rules")
        ),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    if init_sentry(settings):
        logger.info("Error reporting to Sentry is enabled")
    database = Database(settings)
    if settings.jwt_secret_is_ephemeral:
        logger.warning(
            "JWT_SECRET_KEY is not set; using an ephemeral random secret. "
            "All sessions are invalidated on restart. Set JWT_SECRET_KEY to persist them."
        )

    # Outgoing HTTP (Open Library, Wikidata and Wikipedia lookups from the admin portal).
    http = make_http_client(settings)

    # Optional machine translation (ANTHROPIC_API_KEY); Wikidata and Wikipedia work without it.
    machine, machine_client = make_machine_translator(
        settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None,
        settings.translation_model,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await http.aclose()
        if machine_client is not None:
            await machine_client.close()
        await database.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Backend of the Little Dragon online library. "
        "Errors use the shape `{error: {code, message, details}}`.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = database
    app.state.rate_limiter = RateLimiter(enabled=settings.rate_limit_enabled)
    # Emails sent directly by the API (password reset); None when SMTP_HOST is not set.
    app.state.mail_sender = make_smtp_sender(settings)
    app.state.openlibrary = OpenLibraryClient(http)
    app.state.translation_lookup = TranslationLookup(
        app.state.openlibrary, WikimediaClient(http), machine
    )

    _add_cors_and_caching(app, settings)

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
            # JSON only: nothing in an API response may load or run anything. (Not applied to
            # /docs, which loads Swagger UI from a CDN.)
            response.headers.setdefault(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )
        return response

    # Added last = outermost: it runs in the same task as the error handler, which therefore
    # still sees the request id (inner BaseHTTPMiddleware layers run in child tasks).
    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = new_request_id(request.headers.get("x-request-id"))
        request.state.request_id = request_id  # read by the error handler for 500s
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            path = request.url.path  # without the query string
            access_logger.log(
                logging.DEBUG if path in _QUIET_PATHS else logging.INFO,
                "%s %s %s",
                request.method,
                path,
                status,
                extra={
                    "method": request.method,
                    "path": path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "client_ip": request.client.host if request.client else None,
                },
            )
            if status != 500:  # keep the id for the error handler, which runs outside
                request_id_var.reset(token)

    register_exception_handlers(app)

    @app.get("/health", tags=["health"], summary="Liveness probe (no dependencies)")
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router)
    return app


app = create_app()
