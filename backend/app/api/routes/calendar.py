"""The reader's calendar feed: calendar apps fetch it with the secret link (no sign-in)."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Response

from app.api.dependencies import SessionDep, SettingsDep
from app.core.exceptions import NotFoundError
from app.schemas.common import error_responses
from app.services import calendar
from app.services.library_settings import get_library_settings

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get(
    "/{token}.ics",
    response_class=Response,
    responses={
        200: {"content": {"text/calendar": {}}, "description": "An iCalendar feed"},
        **error_responses(404),
    },
    description="Due dates, pickup appointments, held books and reservations of the reader "
    "whose link this is (see POST /users/me/calendar). 404 for an unknown or replaced link.",
)
async def calendar_feed(token: str, session: SessionDep, settings: SettingsDep) -> Response:
    user = await calendar.reader_for(session, token)
    if user is None:
        raise NotFoundError("Unknown calendar link", code="CALENDAR_NOT_FOUND")
    now = datetime.now(UTC)
    zone = ZoneInfo((await get_library_settings(session)).timezone)
    items = await calendar.events(session, settings, user, zone, now)
    text = calendar.render(
        items,
        calendar_name="Little Dragon",
        host=urlsplit(settings.app_base_url).hostname or "little-dragon",
        now=now,
    )
    return Response(
        text,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Cache-Control": "private, max-age=900",
            "Content-Disposition": 'inline; filename="little-dragon.ics"',
        },
    )
