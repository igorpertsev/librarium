from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from app.schemas.book import BookRead
from app.schemas.common import ApiModel, RequestModel


class CartItemCreate(RequestModel):
    book_id: uuid.UUID


class CartItemRead(ApiModel):
    book: BookRead
    added_at: datetime
    batch_number: int
    in_complete_batch: bool


class CartRead(ApiModel):
    """The cart grouped into batches (in the order books were added).

    ``total_amount`` is informational; the authoritative total is recomputed when the
    order is placed.
    """

    items: list[CartItemRead]
    item_count: int
    books_per_batch: int
    price_per_batch: Decimal
    currency: str
    complete_batches: int
    orderable_item_count: int
    total_amount: Decimal
    has_unavailable_items: bool
