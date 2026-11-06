from __future__ import annotations

from datetime import datetime

from app.schemas.book import BookRead
from app.schemas.common import ApiModel


class HeldBookRead(ApiModel):
    book: BookRead
    held_until: datetime
