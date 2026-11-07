"""family accounts

Child profiles of an account; reading log entries per profile; who an order is for.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-25 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "child_profiles",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("birth_year", sa.SmallInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "birth_year IS NULL OR birth_year BETWEEN 1990 AND 2100",
            name=op.f("ck_child_profiles_birth_year_range"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["users.id"],
            name=op.f("fk_child_profiles_parent_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_child_profiles")),
    )
    op.create_index(
        op.f("ix_child_profiles_parent_id"), "child_profiles", ["parent_id"], unique=False
    )
    op.add_column("reading_log_entries", sa.Column("child_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_reading_log_entries_child_id_child_profiles"),
        "reading_log_entries",
        "child_profiles",
        ["child_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_reading_log_entries_child_id"), "reading_log_entries", ["child_id"], unique=False
    )
    op.drop_constraint(
        op.f("uq_reading_log_entries_user_id_book_id"), "reading_log_entries", type_="unique"
    )
    op.create_unique_constraint(
        "uq_reading_log_entries_profile_book",
        "reading_log_entries",
        ["user_id", "child_id", "book_id"],
        postgresql_nulls_not_distinct=True,
    )
    op.add_column("orders", sa.Column("child_name", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "child_name")
    op.execute("DELETE FROM reading_log_entries WHERE child_id IS NOT NULL")
    op.drop_constraint("uq_reading_log_entries_profile_book", "reading_log_entries", type_="unique")
    op.create_unique_constraint(
        op.f("uq_reading_log_entries_user_id_book_id"),
        "reading_log_entries",
        ["user_id", "book_id"],
    )
    op.drop_index(op.f("ix_reading_log_entries_child_id"), table_name="reading_log_entries")
    op.drop_constraint(
        op.f("fk_reading_log_entries_child_id_child_profiles"),
        "reading_log_entries",
        type_="foreignkey",
    )
    op.drop_column("reading_log_entries", "child_id")
    op.drop_index(op.f("ix_child_profiles_parent_id"), table_name="child_profiles")
    op.drop_table("child_profiles")
