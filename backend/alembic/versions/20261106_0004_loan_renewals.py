"""loan renewals

Customers may extend a borrowed order by one loan period, up to
library_settings.max_renewals times (default 1).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06 19:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("renewal_count", sa.SmallInteger(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_orders_renewal_count_non_negative"), "orders", "renewal_count >= 0"
    )
    op.add_column(
        "library_settings",
        sa.Column("max_renewals", sa.SmallInteger(), server_default="1", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_library_settings_max_renewals_range"),
        "library_settings",
        "max_renewals BETWEEN 0 AND 10",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_library_settings_max_renewals_range"), "library_settings", type_="check"
    )
    op.drop_column("library_settings", "max_renewals")
    op.drop_constraint(op.f("ck_orders_renewal_count_non_negative"), "orders", type_="check")
    op.drop_column("orders", "renewal_count")
