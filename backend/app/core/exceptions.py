"""Domain errors and the centralised, uniform API error format.

Every error response has the shape::

    {"error": {"code": "BOOK_UNAVAILABLE", "message": "...", "details": {...}}}
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code: int = HTTPStatus.BAD_REQUEST
    code: str = "BAD_REQUEST"
    message: str = "Bad request"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = dict(details) if details else None
        self.headers = dict(headers) if headers else None
        super().__init__(self.message)


class BadRequestError(AppError):
    pass


class AuthenticationError(AppError):
    status_code = HTTPStatus.UNAUTHORIZED
    code = "NOT_AUTHENTICATED"
    message = "Authentication required"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        super().__init__(message, code=code, headers={"WWW-Authenticate": "Bearer"})


class PermissionDeniedError(AppError):
    status_code = HTTPStatus.FORBIDDEN
    code = "FORBIDDEN"
    message = "You do not have permission to perform this action"


class NotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "NOT_FOUND"
    message = "Resource not found"


class ConflictError(AppError):
    status_code = HTTPStatus.CONFLICT
    code = "CONFLICT"
    message = "The request conflicts with the current state of the resource"


class BookUnavailableError(ConflictError):
    code = "BOOK_UNAVAILABLE"
    message = "One or more books are unavailable"

    def __init__(self, books: Sequence[tuple[Any, str]], message: str | None = None) -> None:
        """``books`` is a sequence of ``(book_id, title)`` pairs."""
        super().__init__(
            message,
            details={
                "book_ids": [str(book_id) for book_id, _ in books],
                "books": [{"id": str(book_id), "title": title} for book_id, title in books],
            },
        )


def error_payload(
    code: str, message: str, details: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


_STATUS_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "NOT_AUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
}


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101 - registered for AppError only
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(error_payload(exc.code, exc.message, exc.details)),
        headers=exc.headers,
    )


async def _http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    code = _STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
    try:
        default_message = HTTPStatus(exc.status_code).phrase
    except ValueError:
        default_message = "HTTP error"
    message = exc.detail if isinstance(exc.detail, str) else default_message
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(code, message),
        headers=getattr(exc, "headers", None),
    )


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    errors = [
        {
            "loc": list(err.get("loc", ())),
            "message": err.get("msg", "Invalid value"),
            "type": err.get("type", "value_error"),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        content=jsonable_encoder(
            error_payload("VALIDATION_ERROR", "Request validation failed", {"errors": errors})
        ),
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log with traceback server-side; never leak internals to the client.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content=error_payload("INTERNAL_ERROR", "An unexpected error occurred"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
