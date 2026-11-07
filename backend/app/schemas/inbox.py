from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.models.enums import NotificationKind
from app.schemas.book import BookBrief
from app.schemas.common import ApiModel, RequestModel


class InboxItem(ApiModel):
    id: uuid.UUID
    kind: NotificationKind
    created_at: datetime
    read: bool
    order_id: uuid.UUID | None
    order_number: int | None
    book: BookBrief | None = Field(description="For news about a book (back, held, ready)")


class Inbox(ApiModel):
    items: list[InboxItem]
    unread: int


class MarkRead(RequestModel):
    ids: list[uuid.UUID] | None = Field(
        default=None, max_length=100, description="Leave out to mark everything read"
    )
