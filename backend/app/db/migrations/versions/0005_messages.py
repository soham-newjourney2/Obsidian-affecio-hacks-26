"""messages

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("client_message_id", sa.String(length=64), nullable=True),
        sa.Column("moderation", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "moderation IN ('allowed', 'hidden')", name=op.f("ck_messages_moderation")
        ),
        sa.CheckConstraint(
            "type IN ('text', 'system', 'companion')", name=op.f("ck_messages_type")
        ),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 1000", name=op.f("ck_messages_body_length")),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["room_members.id"],
            name=op.f("fk_messages_member_id_room_members"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["room_id"], ["rooms.id"], name=op.f("fk_messages_room_id_rooms"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint("member_id", "client_message_id", name="uq_messages_member_client_id"),
    )
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_messages_room_id"), ["room_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_messages_room_id"))

    op.drop_table("messages")
