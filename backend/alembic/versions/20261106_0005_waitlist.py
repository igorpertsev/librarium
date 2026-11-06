"""waitlist

Customers can wait for a book that is out; when it is back they get one email
(notification kind book_available, which refers to a book instead of an order).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06 19:30:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORDER_KINDS = ("order_received", "order_confirmed", "order_cancelled", "due_soon", "overdue")
KIND_CHECK = "ck_notifications_notification_kind"


def _kind_check(kinds: Sequence[str]) -> str:
    return "kind IN (" + ", ".join(f"'{kind}'" for kind in kinds) + ")"


def upgrade() -> None:
    op.create_table(
        "waitlist_entries",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["book_id"], ["books.id"], name=op.f("fk_waitlist_entries_book_id_books"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_waitlist_entries_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_waitlist_entries")),
        sa.UniqueConstraint("user_id", "book_id", name=op.f("uq_waitlist_entries_user_id_book_id")),
    )
    op.create_index(
        op.f("ix_waitlist_entries_book_id"), "waitlist_entries", ["book_id"], unique=False
    )

    op.add_column("notifications", sa.Column("book_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_notifications_book_id_books"),
        "notifications",
        "books",
        ["book_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(op.f(KIND_CHECK), "notifications", type_="check")
    op.create_check_constraint(
        op.f(KIND_CHECK), "notifications", _kind_check((*ORDER_KINDS, "book_available"))
    )


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind = 'book_available'")
    op.drop_constraint(op.f(KIND_CHECK), "notifications", type_="check")
    op.create_check_constraint(op.f(KIND_CHECK), "notifications", _kind_check(ORDER_KINDS))
    op.drop_constraint(op.f("fk_notifications_book_id_books"), "notifications", type_="foreignkey")
    op.drop_column("notifications", "book_id")
    op.drop_index(op.f("ix_waitlist_entries_book_id"), table_name="waitlist_entries")
    op.drop_table("waitlist_entries")
