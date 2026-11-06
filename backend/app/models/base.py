"""Declarative base, naming conventions and shared column helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012 - SQLAlchemy reads this class attribute
        datetime: sa.DateTime(timezone=True),
        uuid.UUID: sa.Uuid(),
    }


def str_enum[E: StrEnum](enum_cls: type[E], name: str) -> sa.Enum:
    """Portable string enum: VARCHAR + CHECK constraint storing the enum *values*.

    Chosen over native PostgreSQL ENUM types because adding/removing values is a plain
    constraint change instead of ``ALTER TYPE`` gymnastics.
    """
    return sa.Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        validate_strings=True,
        values_callable=lambda members: [m.value for m in members],
    )


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        sa.Uuid(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, server_default=sa.func.now()
    )
    # Python-side onupdate keeps the value loaded after flush (no lazy refresh under asyncio).
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=sa.func.now(),
    )
