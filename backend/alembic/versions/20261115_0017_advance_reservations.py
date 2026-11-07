"""advance reservations

A reader reserves a copy of a title for a date; the "reservation ready" email kind.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-15 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KIND_CHECK = "ck_notifications_notification_kind"
KINDS = (
    "order_received",
    "order_confirmed",
    "order_cancelled",
    "due_soon",
    "overdue",
    "book_available",
    "book_held",
)


def _kind_check(kinds: Sequence[str]) -> str:
    return "kind IN (" + ", ".join(f"'{kind}'" for kind in kinds) + ")"


def upgrade() -> None:
    op.create_table(
        "advance_reservations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('active', 'fulfilled', 'cancelled')",
            name=op.f("ck_advance_reservations_reservation_status"),
        ),
        sa.ForeignKeyConstraint(
            ["book_id"],
            ["books.id"],
            name=op.f("fk_advance_reservations_book_id_books"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_advance_reservations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_advance_reservations")),
    )
    op.create_index(
        op.f("ix_advance_reservations_user_id"), "advance_reservations", ["user_id"], unique=False
    )
    op.create_index(
        "ix_advance_reservations_active_book",
        "advance_reservations",
        ["book_id", "starts_on"],
        unique=False,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_constraint(op.f(KIND_CHECK), "notifications", type_="check")
    op.create_check_constraint(
        op.f(KIND_CHECK), "notifications", _kind_check((*KINDS, "reservation_ready"))
    )


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind = 'reservation_ready'")
    op.drop_constraint(op.f(KIND_CHECK), "notifications", type_="check")
    op.create_check_constraint(op.f(KIND_CHECK), "notifications", _kind_check(KINDS))
    op.drop_index(
        "ix_advance_reservations_active_book",
        table_name="advance_reservations",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_index(op.f("ix_advance_reservations_user_id"), table_name="advance_reservations")
    op.drop_table("advance_reservations")
