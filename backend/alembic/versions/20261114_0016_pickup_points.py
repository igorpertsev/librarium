"""pickup points

Places where readers collect orders, with weekly hours and time slots; the pickup point and
time chosen for an order; the library's time zone.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-14 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pickup_points",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column(
            "hours",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("slot_minutes", sa.SmallInteger(), server_default="60", nullable=False),
        sa.Column("slot_capacity", sa.SmallInteger(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "slot_minutes BETWEEN 15 AND 240", name=op.f("ck_pickup_points_slot_minutes_range")
        ),
        sa.CheckConstraint(
            "slot_capacity IS NULL OR slot_capacity BETWEEN 1 AND 100",
            name=op.f("ck_pickup_points_slot_capacity_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pickup_points")),
    )
    op.add_column("orders", sa.Column("pickup_point_id", sa.Uuid(), nullable=True))
    op.add_column("orders", sa.Column("pickup_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_orders_pickup_point_id_pickup_points"),
        "orders",
        "pickup_points",
        ["pickup_point_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_orders_pickup", "orders", ["pickup_point_id", "pickup_at"], unique=False)
    op.add_column(
        "library_settings",
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("library_settings", "timezone")
    op.drop_index("ix_orders_pickup", table_name="orders")
    op.drop_constraint(
        op.f("fk_orders_pickup_point_id_pickup_points"), "orders", type_="foreignkey"
    )
    op.drop_column("orders", "pickup_at")
    op.drop_column("orders", "pickup_point_id")
    op.drop_table("pickup_points")
