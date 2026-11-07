"""librarian role and activity log

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-18 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_CHECK = "ck_users_user_role"


def upgrade() -> None:
    op.drop_constraint(op.f(ROLE_CHECK), "users", type_="check")
    op.create_check_constraint(
        op.f(ROLE_CHECK), "users", "role IN ('customer', 'librarian', 'admin')"
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.String(length=300), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    for column in ("actor_id", "action", "entity_id", "created_at"):
        op.create_index(
            op.f(f"ix_audit_events_{column}"), "audit_events", [column], unique=False
        )


def downgrade() -> None:
    for column in ("created_at", "entity_id", "action", "actor_id"):
        op.drop_index(op.f(f"ix_audit_events_{column}"), table_name="audit_events")
    op.drop_table("audit_events")
    op.execute("UPDATE users SET role = 'customer' WHERE role = 'librarian'")
    op.drop_constraint(op.f(ROLE_CHECK), "users", type_="check")
    op.create_check_constraint(op.f(ROLE_CHECK), "users", "role IN ('customer', 'admin')")
