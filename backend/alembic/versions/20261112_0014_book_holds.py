"""book holds

A returned copy is held for the reader who has waited longest (library_settings.hold_hours,
default 48 hours); the "book held" email kind.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-12 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
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
)


def _kind_check(kinds: Sequence[str]) -> str:
    return "kind IN (" + ", ".join(f"'{kind}'" for kind in kinds) + ")"


def upgrade() -> None:
    op.create_table(
        "book_holds",
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("held_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["book_id"], ["books.id"], name=op.f("fk_book_holds_book_id_books"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_book_holds_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("book_id", name=op.f("pk_book_holds")),
    )
    op.create_index(op.f("ix_book_holds_user_id"), "book_holds", ["user_id"], unique=False)
    op.create_index(op.f("ix_book_holds_held_until"), "book_holds", ["held_until"], unique=False)
    op.add_column(
        "library_settings",
        sa.Column("hold_hours", sa.SmallInteger(), server_default="48", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_library_settings_hold_hours_range"),
        "library_settings",
        "hold_hours BETWEEN 0 AND 336",
    )
    op.drop_constraint(op.f(KIND_CHECK), "notifications", type_="check")
    op.create_check_constraint(
        op.f(KIND_CHECK), "notifications", _kind_check((*KINDS, "book_held"))
    )


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind = 'book_held'")
    op.drop_constraint(op.f(KIND_CHECK), "notifications", type_="check")
    op.create_check_constraint(op.f(KIND_CHECK), "notifications", _kind_check(KINDS))
    op.drop_constraint(
        op.f("ck_library_settings_hold_hours_range"), "library_settings", type_="check"
    )
    op.drop_column("library_settings", "hold_hours")
    op.drop_index(op.f("ix_book_holds_held_until"), table_name="book_holds")
    op.drop_index(op.f("ix_book_holds_user_id"), table_name="book_holds")
    op.drop_table("book_holds")
