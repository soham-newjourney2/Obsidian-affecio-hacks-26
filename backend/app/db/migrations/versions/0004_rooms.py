"""rooms

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invite_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("host_user_id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("story_version", sa.Integer(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('waiting', 'active', 'completed', 'abandoned')",
            name=op.f("ck_rooms_status"),
        ),
        sa.ForeignKeyConstraint(
            ["host_user_id"], ["users.id"], name=op.f("fk_rooms_host_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["story_id"], ["stories.id"], name=op.f("fk_rooms_story_id_stories")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rooms")),
        sa.UniqueConstraint("invite_hash", name=op.f("uq_rooms_invite_hash")),
    )
    op.create_table(
        "room_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("companion_key", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('joined', 'ready', 'playing', 'left', 'removed')",
            name=op.f("ck_room_members_status"),
        ),
        sa.CheckConstraint(
            "(user_id IS NULL) <> (companion_key IS NULL)",
            name=op.f("ck_room_members_human_xor_companion"),
        ),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["rooms.id"],
            name=op.f("fk_room_members_room_id_rooms"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_room_members_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_room_members")),
        sa.UniqueConstraint("room_id", "user_id", name="uq_room_members_room_user"),
    )
    with op.batch_alter_table("room_members", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_room_members_room_id"), ["room_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("room_members", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_room_members_room_id"))

    op.drop_table("room_members")
    op.drop_table("rooms")
