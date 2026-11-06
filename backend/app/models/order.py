from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, str_enum, uuid_pk
from app.models.book import Book
from app.models.enums import BookCategory, ContactMethod, OrderStatus
from app.models.pickup import PickupPoint

MONEY = sa.Numeric(10, 2)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        sa.CheckConstraint("batch_count > 0", name="batch_count_positive"),
        sa.CheckConstraint("books_per_batch > 0", name="books_per_batch_positive"),
        sa.CheckConstraint("price_per_batch >= 0", name="price_per_batch_non_negative"),
        sa.CheckConstraint(
            "total_amount = price_per_batch * batch_count", name="total_matches_batches"
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso4217"),
        sa.CheckConstraint("renewal_count >= 0", name="renewal_count_non_negative"),
        sa.Index("ix_orders_user_created", "user_id", "created_at"),
        sa.Index("ix_orders_pickup", "pickup_point_id", "pickup_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # Human-friendly sequential number shown to customers and staff (#1001, #1002, ...).
    number: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(start=1001), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[OrderStatus] = mapped_column(
        str_enum(OrderStatus, "order_status"),
        default=OrderStatus.PENDING,
        server_default=OrderStatus.PENDING.value,
        index=True,
    )

    # Pricing snapshot (the library charges per complete batch of books).
    total_amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(sa.String(3))
    books_per_batch: Mapped[int] = mapped_column(sa.Integer)
    price_per_batch: Mapped[Decimal] = mapped_column(MONEY)
    batch_count: Mapped[int] = mapped_column(sa.Integer)

    # Contact snapshot at the moment the order was placed.
    contact_name: Mapped[str] = mapped_column(sa.String(200))
    contact_email: Mapped[str] = mapped_column(sa.String(320))
    contact_whatsapp: Mapped[str | None] = mapped_column(sa.String(100))
    contact_telegram: Mapped[str | None] = mapped_column(sa.String(100))
    contact_instagram: Mapped[str | None] = mapped_column(sa.String(100))
    contact_phone: Mapped[str | None] = mapped_column(sa.String(100))
    contact_preferred_method: Mapped[ContactMethod | None] = mapped_column(
        str_enum(ContactMethod, "contact_method")
    )

    due_date: Mapped[date] = mapped_column(sa.Date)
    # How often the customer has extended the loan (limited by library_settings.max_renewals).
    renewal_count: Mapped[int] = mapped_column(sa.SmallInteger, default=0, server_default="0")
    # Charged when the books came back late (days late x the library's fee per day); NULL when
    # returned on time or no fee applied. Settled when paid or waived by the library.
    late_fee: Mapped[Decimal | None] = mapped_column(MONEY)
    late_fee_settled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    # Where and when the reader collects the books (when the library has pickup points).
    pickup_point_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("pickup_points.id", ondelete="RESTRICT")
    )
    pickup_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    returned_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    pickup_point: Mapped[PickupPoint | None] = relationship(lazy="selectin")
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order",
        lazy="raise",
        cascade="all, delete-orphan",
        order_by="OrderItem.position",
    )


class OrderItem(Base):
    """A book in an order, with an immutable snapshot of what was ordered.

    ``reservation_active`` mirrors ``order.status in ACTIVE_ORDER_STATUSES`` and backs a
    partial unique index, so PostgreSQL itself refuses two active reservations of one copy.
    """

    __tablename__ = "order_items"
    __table_args__ = (
        sa.UniqueConstraint("order_id", "book_id"),
        sa.CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso4217"),
        sa.Index(
            "uq_order_items_active_book",
            "book_id",
            unique=True,
            postgresql_where=sa.text("reservation_active"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("orders.id", ondelete="CASCADE"))
    book_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("books.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(sa.SmallInteger)
    batch_number: Mapped[int] = mapped_column(sa.SmallInteger)

    title: Mapped[str] = mapped_column(sa.String(500))
    author: Mapped[str] = mapped_column(sa.String(300))
    isbn: Mapped[str | None] = mapped_column(sa.String(32))
    cover_url: Mapped[str | None] = mapped_column(sa.String(2048))
    category: Mapped[BookCategory] = mapped_column(str_enum(BookCategory, "book_category"))
    age_range: Mapped[str] = mapped_column(sa.String(20))
    unit_price: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(sa.String(3))

    reservation_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())

    order: Mapped[Order] = relationship(back_populates="items", lazy="raise")
    book: Mapped[Book] = relationship(lazy="raise")
