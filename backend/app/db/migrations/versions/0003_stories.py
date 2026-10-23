"""stories

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=280), nullable=False),
        sa.Column("genres", sa.JSON(), nullable=False),
        sa.Column("inspiration_title", sa.String(length=120), nullable=False),
        sa.Column("inspiration_author", sa.String(length=80), nullable=False),
        sa.Column("publication_year", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(length=400), nullable=False),
        sa.Column("rights_status", sa.String(length=32), nullable=False),
        sa.Column("rights_notes", sa.Text(), nullable=False),
        sa.Column("rights_reviewed_at", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("min_players", sa.Integer(), nullable=False),
        sa.Column("max_players", sa.Integer(), nullable=False),
        sa.Column("est_minutes", sa.Integer(), nullable=True),
        sa.Column("playable", sa.Boolean(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "rights_status IN ('review_required', 'verified_public_domain', 'excluded')",
            name=op.f("ck_stories_rights_status"),
        ),
        sa.CheckConstraint("min_players <= max_players", name=op.f("ck_stories_player_range")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stories")),
        sa.UniqueConstraint("slug", name=op.f("uq_stories_slug")),
    )


def downgrade() -> None:
    op.drop_table("stories")
