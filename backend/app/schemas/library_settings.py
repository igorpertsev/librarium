from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, ClassVar

from pydantic import AfterValidator, Field

from app.schemas.common import ApiModel, PatchModel
from app.schemas.types import CurrencyCode

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


class LibrarySettingsRead(LibraryRules):
    updated_at: datetime


class LibrarySettingsUpdate(PatchModel):
    non_nullable_fields: ClassVar[frozenset[str]] = frozenset(
        {"books_per_batch", "price_per_batch", "currency", "loan_period_days", "max_renewals"}
    )

    books_per_batch: Annotated[int, Field(ge=1, le=100)] | None = None
    price_per_batch: Money | None = None
    currency: CurrencyCode | None = None
    loan_period_days: Annotated[int, Field(ge=1, le=365)] | None = None
    max_renewals: Annotated[int, Field(ge=0, le=10)] | None = None
