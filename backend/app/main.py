"""Application factory. Run with ``uvicorn app.main:app``.

The schema is managed by Alembic only (``alembic upgrade head``); the app never calls
``metadata.create_all()``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.database import Database
from app.core.exceptions import register_exception_handlers
from app.core.rate_limit import RateLimiter
from app.services.notifications import make_smtp_sender

logger = logging.getLogger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    database = Database(settings)
    if settings.jwt_secret_is_ephemeral:
        logger.warning(
            "JWT_SECRET_KEY is not set; using an ephemeral random secret. "
            "All sessions are invalidated on restart. Set JWT_SECRET_KEY to persist them."
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # explicit list, never "*" with credentials
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )

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

    register_exception_handlers(app)

    @app.get("/health", tags=["health"], summary="Liveness probe (no dependencies)")
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router)
    return app


app = create_app()
