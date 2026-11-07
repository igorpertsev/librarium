"""late returns

Library settings block_overdue (no new orders while a loan is overdue) and late_fee_per_day;
the late fee charged on an order returned late and when it was settled.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-13 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "library_settings",
        sa.Column("block_overdue", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "library_settings",
        sa.Column(
            "late_fee_per_day", sa.Numeric(precision=10, scale=2), server_default="0", nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_library_settings_late_fee_non_negative"),
        "library_settings",
        "late_fee_per_day >= 0",
    )
    op.add_column("orders", sa.Column("late_fee", sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column(
        "orders", sa.Column("late_fee_settled_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("orders", "late_fee_settled_at")
    op.drop_column("orders", "late_fee")
    op.drop_constraint(
        op.f("ck_library_settings_late_fee_non_negative"), "library_settings", type_="check"
    )
    op.drop_column("library_settings", "late_fee_per_day")
    op.drop_column("library_settings", "block_overdue")
