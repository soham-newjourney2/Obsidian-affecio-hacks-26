"""game

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "game_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("story_version", sa.Integer(), nullable=False),
        sa.Column("variant_id", sa.String(length=40), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("scene_id", sa.String(length=40), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("canonical_state", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'failed', 'abandoned')",
            name=op.f("ck_game_sessions_status"),
        ),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["rooms.id"],
            name=op.f("fk_game_sessions_room_id_rooms"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["story_id"], ["stories.id"], name=op.f("fk_game_sessions_story_id_stories")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_game_sessions")),
        sa.UniqueConstraint("room_id", name=op.f("uq_game_sessions_room_id")),
    )
    op.create_table(
        "game_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("actor_member_id", sa.Uuid(), nullable=True),
        sa.Column("visibility", sa.String(length=60), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["game_sessions.id"],
            name=op.f("fk_game_events_session_id_game_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_game_events")),
        sa.UniqueConstraint("session_id", "seq", name="uq_game_events_session_seq"),
    )
    with op.batch_alter_table("game_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_game_events_session_id"), ["session_id"], unique=False)

    op.create_table(
        "votes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("choice_id", sa.String(length=40), nullable=False),
        sa.Column("client_action_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'superseded')", name=op.f("ck_votes_status")),
        sa.ForeignKeyConstraint(
            ["member_id"], ["room_members.id"], name=op.f("fk_votes_member_id_room_members")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["game_sessions.id"],
            name=op.f("fk_votes_session_id_game_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_votes")),
        sa.UniqueConstraint("member_id", "client_action_id", name="uq_votes_member_action"),
    )
    with op.batch_alter_table("votes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_votes_session_id"), ["session_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("votes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_votes_session_id"))

    op.drop_table("votes")
    with op.batch_alter_table("game_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_game_events_session_id"))

    op.drop_table("game_events")
    op.drop_table("game_sessions")
