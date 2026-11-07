"""stocktaking

Counts of the books on the shelves, one open at a time.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-20 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stocktakes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("started_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("marked_missing", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["started_by_id"],
            ["users.id"],
            name=op.f("fk_stocktakes_started_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stocktakes")),
    )
    op.create_index(
        "uq_stocktakes_one_open",
        "stocktakes",
        [sa.text("(finished_at IS NULL)")],
        unique=True,
        postgresql_where=sa.text("finished_at IS NULL"),
    )
    op.create_table(
        "stocktake_counts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("stocktake_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.Column("isbn", sa.String(length=20), nullable=True),
        sa.Column("counted", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("counted >= 0", name=op.f("ck_stocktake_counts_counted_non_negative")),
        sa.CheckConstraint(
            "(group_id IS NULL) <> (isbn IS NULL)",
            name=op.f("ck_stocktake_counts_title_or_unknown_isbn"),
        ),
        sa.ForeignKeyConstraint(
            ["stocktake_id"],
            ["stocktakes.id"],
            name=op.f("fk_stocktake_counts_stocktake_id_stocktakes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stocktake_counts")),
        sa.UniqueConstraint(
            "stocktake_id", "group_id", name=op.f("uq_stocktake_counts_stocktake_id_group_id")
        ),
        sa.UniqueConstraint(
            "stocktake_id", "isbn", name=op.f("uq_stocktake_counts_stocktake_id_isbn")
        ),
    )
    op.create_index(
        op.f("ix_stocktake_counts_stocktake_id"), "stocktake_counts", ["stocktake_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_stocktake_counts_stocktake_id"), table_name="stocktake_counts")
    op.drop_table("stocktake_counts")
    op.drop_index("uq_stocktakes_one_open", table_name="stocktakes")
    op.drop_table("stocktakes")
