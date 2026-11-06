from __future__ import annotations

from datetime import datetime

from app.schemas.book import BookBrief
from app.schemas.common import ApiModel


class WaitlistEntryRead(ApiModel):
    book: BookBrief
    created_at: datetime
