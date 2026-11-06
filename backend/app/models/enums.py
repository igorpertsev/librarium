"""Domain enumerations shared by models, schemas and services.

String values intentionally match the existing frontend (`src/app/types.ts`), so no
mapping is required for statuses and categories.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"


class ContactMethod(StrEnum):
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    INSTAGRAM = "instagram"
    PHONE = "phone"
    EMAIL = "email"


class BookCategory(StrEnum):
    FICTION = "fiction"
    NON_FICTION = "non-fiction"
    CHILDREN = "children"
    YOUNG_ADULT = "young-adult"
    SCIENCE = "science"
    HISTORY = "history"
    BIOGRAPHY = "biography"


class BookStatus(StrEnum):
    """Status set by librarians. Reservation by orders is computed separately."""

    AVAILABLE = "available"
    AVAILABLE_SOON = "available-soon"
    NOT_AVAILABLE = "not-available"


class OrderStatus(StrEnum):
    PENDING = "pending"  # requested by the customer, books reserved
    CONFIRMED = "confirmed"  # books handed over to the customer
    RETURNED = "returned"  # books are back in the library
    CANCELLED = "cancelled"


# Single source of truth: while an order is in one of these statuses its books are reserved.
ACTIVE_ORDER_STATUSES: frozenset[OrderStatus] = frozenset(
    {OrderStatus.PENDING, OrderStatus.CONFIRMED}
)

# Allowed admin transitions (mirrors the buttons of the admin "Orders" tab).
ORDER_STATUS_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.CONFIRMED, OrderStatus.CANCELLED}),
    OrderStatus.CONFIRMED: frozenset({OrderStatus.RETURNED}),
    OrderStatus.RETURNED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}

# Customers may only withdraw a request that has not been handed over yet.
CUSTOMER_CANCELLABLE_STATUSES: frozenset[OrderStatus] = frozenset({OrderStatus.PENDING})


class NotificationKind(StrEnum):
    ORDER_RECEIVED = "order_received"  # the customer placed an order
    ORDER_CONFIRMED = "order_confirmed"  # books handed over, due date known
    ORDER_CANCELLED = "order_cancelled"  # cancelled by the library
    DUE_SOON = "due_soon"  # reminder a few days before the due date
    OVERDUE = "overdue"  # the due date has passed


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"  # gave up after the maximum number of attempts
    EXPIRED = "expired"  # too old to be useful, or the recipient can no longer receive it
