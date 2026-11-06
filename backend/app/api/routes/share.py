"""Link previews: a small HTML page with Open Graph tags for a book.

Link-preview bots (Telegram, WhatsApp, Slack, ...) do not run JavaScript, so the web server
sends them here for /books/<id> (see deploy/web/Caddyfile); people get the app itself.
"""

from __future__ import annotations

import uuid
from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.api.dependencies import SessionDep, SettingsDep
from app.core.exceptions import AppError
from app.services import books as books_service

router = APIRouter(prefix="/share", tags=["share"])

MAX_DESCRIPTION = 300


def _page(*, title: str, description: str, image: str | None, url: str) -> str:
    tags = [
        ("og:type", "book"),
        ("og:site_name", "Little Dragon"),
        ("og:title", title),
        ("og:description", description),
        ("og:url", url),
        ("twitter:card", "summary_large_image" if image else "summary"),
    ]
    if image:
        tags.append(("og:image", image))
    meta = "\n    ".join(
        f'<meta property="{escape(name)}" content="{escape(value)}">' for name, value in tags
    )
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>{escape(title)}</title>
    <meta name="description" content="{escape(description)}">
    {meta}
    <link rel="canonical" href="{escape(url)}">
    <meta http-equiv="refresh" content="0; url={escape(url)}">
  </head>
  <body><a href="{escape(url)}">{escape(title)}</a></body>
</html>
"""


@router.get(
    "/books/{book_id}",
    response_class=HTMLResponse,
    responses={404: {"description": "No such book"}},
    description="Open Graph page for a book, for link previews; people are redirected to the "
    "book in the app.",
)
async def share_book(
    book_id: uuid.UUID, session: SessionDep, settings: SettingsDep
) -> HTMLResponse:
    url = f"{settings.app_base_url}/books/{book_id}"
    try:
        book = await books_service.get_book(session, book_id)
    except AppError:
        return HTMLResponse(
            _page(title="Little Dragon", description="", image=None, url=settings.app_base_url),
            status_code=404,
        )
    description = book.description.strip()
    if len(description) > MAX_DESCRIPTION:
        description = description[: MAX_DESCRIPTION - 1].rstrip() + "…"
    return HTMLResponse(
        _page(
            title=f"{book.title} — {book.author}",
            description=description,
            image=book.cover_url,
            url=url,
        )
    )
