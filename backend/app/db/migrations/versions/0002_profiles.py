"""profiles

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("interests", sa.JSON(), nullable=False),
        sa.Column("genres", sa.JSON(), nullable=False),
        sa.Column("activities", sa.JSON(), nullable=False),
        sa.Column("interaction_style", sa.String(length=16), nullable=False),
        sa.Column("preferred_roles", sa.JSON(), nullable=False),
        sa.Column("availability", sa.JSON(), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("shareable_summary", sa.String(length=160), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "interaction_style IN ('thoughtful', 'playful', 'analytical')",
            name=op.f("ck_profiles_interaction_style"),
        ),
        sa.CheckConstraint(
            "visibility IN ('private', 'match_only')", name=op.f("ck_profiles_visibility")
        ),
        sa.CheckConstraint(
            "length(shareable_summary) <= 160", name=op.f("ck_profiles_summary_length")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_profiles_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_profiles_user_id")),
    )


def downgrade() -> None:
    op.drop_table("profiles")
