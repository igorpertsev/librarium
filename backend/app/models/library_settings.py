from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

SETTINGS_ROW_ID = 1


class LibrarySettings(TimestampMixin, Base):
    """Singleton row with lending/pricing rules (the admin "Batch Configuration" card).

    The frontend has no per-book price: customers pay ``price_per_batch`` for every complete
    batch of ``books_per_batch`` books.
    """

    __tablename__ = "library_settings"
    __table_args__ = (
        sa.CheckConstraint(f"id = {SETTINGS_ROW_ID}", name="singleton"),
        sa.CheckConstraint("books_per_batch BETWEEN 1 AND 100", name="books_per_batch_range"),
        sa.CheckConstraint("price_per_batch >= 0", name="price_per_batch_non_negative"),
        sa.CheckConstraint("loan_period_days BETWEEN 1 AND 365", name="loan_period_range"),
        sa.CheckConstraint("max_renewals BETWEEN 0 AND 10", name="max_renewals_range"),
        sa.CheckConstraint("hold_hours BETWEEN 0 AND 336", name="hold_hours_range"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso4217"),
    )

    id: Mapped[int] = mapped_column(sa.SmallInteger, primary_key=True, default=SETTINGS_ROW_ID)
    books_per_batch: Mapped[int] = mapped_column(sa.Integer)
    price_per_batch: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2))
    currency: Mapped[str] = mapped_column(sa.String(3))
    loan_period_days: Mapped[int] = mapped_column(sa.Integer)
    # How many times a customer may extend a loan by another loan period (0 = never).
    max_renewals: Mapped[int] = mapped_column(sa.SmallInteger, default=1, server_default="1")
    # A returned book is held this long for the reader who has waited longest (0: everybody
    # waiting is emailed at once and the first to order gets it).
    hold_hours: Mapped[int] = mapped_column(sa.SmallInteger, default=48, server_default="48")


DEFAULT_LIBRARY_SETTINGS = {
    "id": SETTINGS_ROW_ID,
    "books_per_batch": 5,
    "price_per_batch": Decimal("15.99"),
    "currency": "USD",
    "loan_period_days": 30,
    "max_renewals": 1,
    "hold_hours": 48,
}
