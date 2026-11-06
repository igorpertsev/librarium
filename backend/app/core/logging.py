"""Logging setup: one line per record (JSON in production) with the request id.

Every request gets an id (taken from a valid incoming ``X-Request-ID`` header, otherwise
generated). It is returned in the ``X-Request-ID`` response header, added to every log line
written while the request is handled, and included in ``INTERNAL_ERROR`` responses, so a
user's error report can be matched with the server logs.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")
# Attributes every LogRecord has; anything else was passed with ``extra=...``.
_STANDARD_ATTRS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


def new_request_id(incoming: str | None = None) -> str:
    """Reuse a well-formed id from a proxy or client, otherwise make a new one."""
    if incoming and _VALID_REQUEST_ID.fullmatch(incoming):
        return incoming
    return secrets.token_hex(8)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


_base_record_factory = logging.getLogRecordFactory()


def _record_with_request_id(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _base_record_factory(*args, **kwargs)
    record.request_id = request_id_var.get()
    return record


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            entry["request_id"] = request_id
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and key != "request_id" and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-7s %(name)s [%(request_label)s] %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        record.request_label = getattr(record, "request_id", None) or "-"
        return super().format(record)


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if settings.log_format == "json" else TextFormatter())
    # Every record gets the current request id, whichever handler formats it.
    logging.setLogRecordFactory(_record_with_request_id)

    root = logging.getLogger()
    # Replace our handler from an earlier call; keep handlers others installed (e.g. pytest).
    root.handlers = [h for h in root.handlers if not getattr(h, "_librarium", False)]
    handler._librarium = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(settings.log_level)
    # uvicorn's own loggers go through the same handler; its access log is replaced by the
    # app's (logger "app.request"), which knows the request id and the duration.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True


def init_sentry(settings: Settings) -> bool:
    """Report unhandled errors to Sentry when SENTRY_DSN is set. Returns True if enabled."""
    if settings.sentry_dsn is None:
        return False
    import sentry_sdk  # noqa: PLC0415 - only needed when Sentry is configured

    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment.value,
        send_default_pii=False,  # no IP addresses, cookies or request bodies
        traces_sample_rate=0.0,
    )
    return True
