from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, ClassVar

from pydantic import AfterValidator, Field

from app.schemas.common import ApiModel, PatchModel
from app.schemas.types import CurrencyCode, TimeZoneName

CENT = Decimal("0.01")
# Canonical two-decimal value, identical to what NUMERIC(10, 2) stores.
Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=10, decimal_places=2),
    AfterValidator(lambda v: v.quantize(CENT)),
]


class LibraryRules(ApiModel):
    """Lending rules every reader may know (GET /library/rules)."""

    books_per_batch: int
    price_per_batch: Decimal
    currency: str
    loan_period_days: int
    max_renewals: int
    hold_hours: int = Field(description="How long a returned book is held for the next reader")
    block_overdue: bool = Field(
        description="No new orders while one of the reader's loans is overdue"
    )
    late_fee_per_day: Decimal = Field(
        description="Charged per day late when books come back (0: none)"
    )
    timezone: str = Field(description="IANA time zone of opening hours and pickup slots")
    has_pick: bool = Field(
        default=False, description="A book of the month is chosen (see /library/pick)"
    )
    telegram_bot: str | None = Field(
        None, description="Username of the library's Telegram bot, when notifications can go there"
    )
    web_push_key: str | None = Field(
        default=None,
        description="VAPID public key for Web Push subscriptions (null: push is not set up)",
    )


class LibrarySettingsRead(LibraryRules):
    updated_at: datetime
    require_staff_mfa: bool = Field(description="Staff must use two-step sign-in")


class LibrarySettingsUpdate(PatchModel):
    non_nullable_fields: ClassVar[frozenset[str]] = frozenset(
        {
            "books_per_batch",
            "price_per_batch",
            "currency",
            "loan_period_days",
            "max_renewals",
            "hold_hours",
            "block_overdue",
            "late_fee_per_day",
            "timezone",
            "require_staff_mfa",
        }
    )

    books_per_batch: Annotated[int, Field(ge=1, le=100)] | None = None
    price_per_batch: Money | None = None
    currency: CurrencyCode | None = None
    loan_period_days: Annotated[int, Field(ge=1, le=365)] | None = None
    max_renewals: Annotated[int, Field(ge=0, le=10)] | None = None
    hold_hours: Annotated[int, Field(ge=0, le=336)] | None = None
    block_overdue: bool | None = None
    late_fee_per_day: Money | None = None
    timezone: TimeZoneName | None = None
    require_staff_mfa: bool | None = None
