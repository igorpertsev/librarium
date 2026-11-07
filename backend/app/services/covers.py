"""Book covers uploaded by librarians.

The image is decoded with Pillow (JPEG, PNG or WebP; at most ``max_cover_bytes`` and 40
megapixels), re-encoded as WebP without its metadata in three sizes — L (up to 800 px high),
M (400) and S (160) — and stored as ``<media_dir>/covers/<random>-<size>.webp``. The book (and
every copy of its title) gets ``cover_url = /media/covers/<random>-L.webp``; the frontend asks
for the other sizes by changing the suffix.
"""

from __future__ import annotations

import io
import re
import secrets
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, BadRequestError
from app.models import Book
from app.repositories.books import copy_group_key
from app.schemas.book import BookRead
from app.services.books import book_not_found, get_book

SIZES = {"L": 800, "M": 400, "S": 160}
FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELS = 40_000_000
MEDIA_COVER = re.compile(r"^/media/covers/([0-9a-f]{32})-L\.webp$")

Image.MAX_IMAGE_PIXELS = MAX_PIXELS  # refuse decompression bombs


class CoverTooLargeError(AppError):
    status_code = 413
    code = "IMAGE_TOO_LARGE"
    message = "The image is too large"


def covers_dir(media_dir: str) -> Path:
    path = Path(media_dir) / "covers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _renditions(data: bytes) -> dict[str, bytes]:
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in FORMATS:
                raise BadRequestError("Upload a JPEG, PNG or WebP image", code="INVALID_IMAGE")
            probe.verify()
        with Image.open(io.BytesIO(data)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            out: dict[str, bytes] = {}
            for size, height in SIZES.items():
                copy = image.copy()
                copy.thumbnail((height * 2, height))
                buffer = io.BytesIO()
                copy.save(buffer, "WEBP", quality=82, method=4)
                out[size] = buffer.getvalue()
            return out
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as exc:
        raise BadRequestError(
            "That file is not an image we can read", code="INVALID_IMAGE"
        ) from exc


def _remove(media_dir: str, cover_url: str | None) -> None:
    match = MEDIA_COVER.match(cover_url or "")
    if not match:
        return
    for size in SIZES:
        (covers_dir(media_dir) / f"{match.group(1)}-{size}.webp").unlink(missing_ok=True)


async def upload(
    session: AsyncSession, book_id: uuid.UUID, data: bytes, *, media_dir: str, max_bytes: int
) -> BookRead:
    if len(data) > max_bytes:
        raise CoverTooLargeError(f"The image must be at most {max_bytes // (1024 * 1024)} MB")
    book = await session.get(Book, book_id)
    if book is None:
        raise book_not_found()
    renditions = _renditions(data)
    name = secrets.token_hex(16)
    folder = covers_dir(media_dir)
    for size, content in renditions.items():
        (folder / f"{name}-{size}.webp").write_bytes(content)
    url = f"/media/covers/{name}-L.webp"
    old = book.cover_url
    copies = select(Book.id).where(copy_group_key() == book.group_id).scalar_subquery()
    await session.execute(
        update(Book)
        .where(Book.id.in_(copies))
        .values(
            cover_url=url,
            image_urls=[url, *[u for u in book.image_urls if u not in (old, url)]][:20],
        )
    )
    await session.commit()
    if old != url:
        _remove(media_dir, old)
    return await get_book(session, book_id, include_inactive=True)
