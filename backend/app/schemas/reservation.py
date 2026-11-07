from __future__ import annotations

import uuid
from datetime import date

from app.models.enums import ReservationStatus
from app.schemas.book import BookRead
from app.schemas.common import ApiModel, RequestModel


class ReservationCreate(RequestModel):
    book_id: uuid.UUID
    starts_on: date


class ReservationRead(ApiModel):
    id: uuid.UUID
    book: BookRead
    starts_on: date
    status: ReservationStatus


class UpcomingReservationRead(ApiModel):
    id: uuid.UUID
    starts_on: date
    book_id: uuid.UUID
    title: str
    author: str
    reader_name: str
    reader_email: str
