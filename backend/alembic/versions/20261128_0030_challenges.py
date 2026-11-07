"""reading challenges

Challenges set by the library and the readers (or children) taking part.

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-28 10:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "challenges",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name_en", sa.String(length=200), nullable=False),
        sa.Column("name_ru", sa.String(length=200), nullable=True),
        sa.Column("description_en", sa.Text(), server_default="", nullable=False),
        sa.Column("description_ru", sa.Text(), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("goal", sa.SmallInteger(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "fiction",
                "non-fiction",
                "children",
                "young-adult",
                "science",
                "history",
                "biography",
                name="book_category",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("ends_on >= starts_on", name=op.f("ck_challenges_dates_in_order")),
        sa.CheckConstraint("goal BETWEEN 1 AND 100", name=op.f("ck_challenges_goal_range")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_challenges")),
    )
    op.create_index(op.f("ix_challenges_ends_on"), "challenges", ["ends_on"], unique=False)
    op.create_table(
        "challenge_entries",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("challenge_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=True),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["challenge_id"],
            ["challenges.id"],
            name=op.f("fk_challenge_entries_challenge_id_challenges"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_challenge_entries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["child_id"],
            ["child_profiles.id"],
            name=op.f("fk_challenge_entries_child_id_child_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_challenge_entries")),
        sa.UniqueConstraint(
            "challenge_id",
            "user_id",
            "child_id",
            name="uq_challenge_entries_profile",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        op.f("ix_challenge_entries_challenge_id"),
        "challenge_entries",
        ["challenge_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_challenge_entries_user_id"), "challenge_entries", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_challenge_entries_user_id"), table_name="challenge_entries")
    op.drop_index(op.f("ix_challenge_entries_challenge_id"), table_name="challenge_entries")
    op.drop_table("challenge_entries")
    op.drop_index(op.f("ix_challenges_ends_on"), table_name="challenges")
    op.drop_table("challenges")
