from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.models.enums import BookCategory, ContactMethod, NotificationKind, OrderStatus
from app.schemas.book import BookBrief
from app.schemas.common import ApiModel, Page, RequestModel


class OrderItemRead(ApiModel):
    id: uuid.UUID
    book_id: uuid.UUID
    position: int
    batch_number: int
    # Snapshot taken when the order was placed; never changes afterwards.
    title: str
    author: str
    isbn: str | None
    cover_url: str | None
    category: BookCategory
    age_range: str
    unit_price: Decimal
    currency: str
    # Current catalogue data (description, images...) for display purposes.
    book: BookBrief


class OrderRead(ApiModel):
    id: uuid.UUID
    number: int
    user_id: uuid.UUID
    status: OrderStatus
    total_amount: Decimal
    currency: str
    books_per_batch: int
    price_per_batch: Decimal
    batch_count: int
    contact_name: str
    contact_email: str
    contact_whatsapp: str | None
    contact_telegram: str | None
    contact_instagram: str | None
    contact_phone: str | None
    contact_preferred_method: ContactMethod | None
    due_date: date
    confirmed_at: datetime | None
    returned_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemRead]


class OrderPage(Page[OrderRead]):
    pass


class OrderStatusUpdate(RequestModel):
    status: OrderStatus


class OrderDueDateUpdate(RequestModel):
    due_date: date


class ReminderQueued(ApiModel):
    kind: NotificationKind
    queued_at: datetime
