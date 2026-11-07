"""purchase requests

Readers suggest books for the library to buy and vote for them; the "purchase added" email.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-21 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
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
    "reservation_ready",
)


def _kind_check(kinds: Sequence[str]) -> str:
    return "kind IN (" + ", ".join(f"'{kind}'" for kind in kinds) + ")"


def upgrade() -> None:
    op.create_table(
        "purchase_requests",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("author", sa.String(length=300), nullable=False),
        sa.Column("isbn", sa.String(length=20), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="open", nullable=False),
        sa.Column("librarian_note", sa.String(length=500), nullable=True),
        sa.Column("book_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('open', 'ordered', 'added', 'declined')",
            name=op.f("ck_purchase_requests_purchase_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_purchase_requests_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["book_id"],
            ["books.id"],
            name=op.f("fk_purchase_requests_book_id_books"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_requests")),
    )
    op.create_index(
        op.f("ix_purchase_requests_created_by_id"),
        "purchase_requests",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_purchase_requests_status"), "purchase_requests", ["status"], unique=False
    )
    op.create_table(
        "purchase_votes",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["purchase_requests.id"],
            name=op.f("fk_purchase_votes_request_id_purchase_requests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_purchase_votes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("request_id", "user_id", name=op.f("pk_purchase_votes")),
    )
    op.create_index(
        op.f("ix_purchase_votes_user_id"), "purchase_votes", ["user_id"], unique=False
    )
    op.drop_constraint(op.f(KIND_CHECK), "notifications", type_="check")
    op.create_check_constraint(
        op.f(KIND_CHECK), "notifications", _kind_check((*KINDS, "purchase_added"))
    )


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind = 'purchase_added'")
    op.drop_constraint(op.f(KIND_CHECK), "notifications", type_="check")
    op.create_check_constraint(op.f(KIND_CHECK), "notifications", _kind_check(KINDS))
    op.drop_index(op.f("ix_purchase_votes_user_id"), table_name="purchase_votes")
    op.drop_table("purchase_votes")
    op.drop_index(op.f("ix_purchase_requests_status"), table_name="purchase_requests")
    op.drop_index(op.f("ix_purchase_requests_created_by_id"), table_name="purchase_requests")
    op.drop_table("purchase_requests")
