"""Activity log of staff changes.

Every successful POST/PUT/PATCH/DELETE under ``/admin`` is recorded by the router dependency
``app.api.dependencies.audit_trail``: who, which endpoint (``action`` is the endpoint name),
which record (the first id in the path) and the request body, with secrets redacted and long
values shortened. Reading the log is for administrators only.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent, Book, Order, User

SECRET_KEYS = {"password", "current_password", "new_password", "token", "refresh_token", "secret"}
MAX_TEXT = 300
MAX_ITEMS = 20


def _clean(value: Any, depth: int = 0) -> Any:
    if depth > 3:
        return "…"
    if isinstance(value, dict):
        return {
            str(k): "[redacted]" if str(k).lower() in SECRET_KEYS else _clean(v, depth + 1)
            for k, v in list(value.items())[:MAX_ITEMS]
        }
    if isinstance(value, list):
        items = [_clean(v, depth + 1) for v in value[:MAX_ITEMS]]
        return [*items, f"… {len(value) - MAX_ITEMS} more"] if len(value) > MAX_ITEMS else items
    if isinstance(value, str) and len(value) > MAX_TEXT:
        return f"{value[:MAX_TEXT]}… ({len(value)} characters)"
    return value


def details_from_body(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except ValueError:
        return {"body": f"{len(body)} bytes"}
    cleaned = _clean(parsed)
    return cleaned if isinstance(cleaned, dict) else {"body": cleaned}


async def record(
    session: AsyncSession,
    actor: User,
    *,
    action: str,
    method: str,
    path: str,
    path_params: dict[str, Any],
    query: dict[str, str] | None = None,
    body: bytes,
) -> None:
    entity_id = next((_uuid(v) for v in path_params.values() if _uuid(v) is not None), None)
    segments = [s for s in path.split("/") if s and not s.startswith("{")]
    entity_type = segments[segments.index("admin") + 1] if "admin" in segments[:-1] else None
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor.id,
            actor_email=actor.email,
            action=action[:100],
            method=method,
            path=path[:300],
            entity_type=entity_type,
            entity_id=entity_id,
            details={**details_from_body(body), **({"query": query} if query else {})},
        )
    )
    await session.commit()


def _uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class AuditEntry:
    id: uuid.UUID
    created_at: datetime
    actor_email: str
    action: str
    method: str
    path: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    entity_label: str | None
    details: dict[str, Any]


async def _labels(session: AsyncSession, events: list[AuditEvent]) -> dict[uuid.UUID, str]:
    """Readable names of the records: book titles, order numbers, user emails."""
    ids = {e.entity_id for e in events if e.entity_id is not None}
    if not ids:
        return {}
    labels: dict[uuid.UUID, str] = {}
    for book_id, title in await session.execute(
        select(Book.id, Book.title).where(Book.id.in_(ids))
    ):
        labels[book_id] = title
    for order_id, number in await session.execute(
        select(Order.id, Order.number).where(Order.id.in_(ids))
    ):
        labels[order_id] = f"#{number}"
    for user_id, email in await session.execute(
        select(User.id, User.email).where(User.id.in_(ids))
    ):
        labels[user_id] = email
    return labels


async def list_events(
    session: AsyncSession, *, page: int, page_size: int, actor_id: uuid.UUID | None = None
) -> tuple[list[AuditEntry], int]:
    conditions = [AuditEvent.actor_id == actor_id] if actor_id else []
    total = await session.scalar(select(func.count()).select_from(AuditEvent).where(*conditions))
    events = list(
        (
            await session.scalars(
                select(AuditEvent)
                .where(*conditions)
                .order_by(AuditEvent.created_at.desc(), AuditEvent.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    labels = await _labels(session, events)
    return [
        AuditEntry(
            id=e.id,
            created_at=e.created_at,
            actor_email=e.actor_email,
            action=e.action,
            method=e.method,
            path=e.path,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            entity_label=labels.get(e.entity_id) if e.entity_id else None,
            details=e.details,
        )
        for e in events
    ], int(total or 0)
