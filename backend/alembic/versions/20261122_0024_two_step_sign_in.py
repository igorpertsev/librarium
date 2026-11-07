"""two-step sign-in

TOTP secrets (encrypted), recovery code hashes and the last used step on users; the library
setting that requires it for staff.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-22 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_secret", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("mfa_pending_secret", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("mfa_enabled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("mfa_last_step", sa.BigInteger(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "mfa_recovery_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "library_settings",
        sa.Column("require_staff_mfa", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("library_settings", "require_staff_mfa")
    for column in (
        "mfa_recovery_hashes",
        "mfa_last_step",
        "mfa_enabled_at",
        "mfa_pending_secret",
        "mfa_secret",
    ):
        op.drop_column("users", column)
