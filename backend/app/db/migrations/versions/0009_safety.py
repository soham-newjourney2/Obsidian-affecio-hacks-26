"""safety

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("blocker", sa.Uuid(), nullable=False),
        sa.Column("blocked", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["blocked"], ["users.id"], name=op.f("fk_blocks_blocked_users")),
        sa.ForeignKeyConstraint(["blocker"], ["users.id"], name=op.f("fk_blocks_blocker_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blocks")),
        sa.UniqueConstraint("blocker", "blocked", name="uq_blocks_pair"),
    )
    with op.batch_alter_table("blocks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_blocks_blocked"), ["blocked"], unique=False)
        batch_op.create_index(batch_op.f("ix_blocks_blocker"), ["blocker"], unique=False)

    op.create_table(
        "connection_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("from_user", sa.Uuid(), nullable=False),
        sa.Column("to_user", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'withdrawn')",
            name=op.f("ck_connection_requests_status"),
        ),
        sa.ForeignKeyConstraint(
            ["from_user"], ["users.id"], name=op.f("fk_connection_requests_from_user_users")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["game_sessions.id"],
            name=op.f("fk_connection_requests_session_id_game_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_user"], ["users.id"], name=op.f("fk_connection_requests_to_user_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_connection_requests")),
        sa.UniqueConstraint(
            "session_id", "from_user", "to_user", name="uq_connection_requests_pair"
        ),
    )
    with op.batch_alter_table("connection_requests", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_connection_requests_from_user"), ["from_user"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_connection_requests_to_user"), ["to_user"], unique=False
        )

    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reporter", sa.Uuid(), nullable=False),
        sa.Column("reported_user", sa.Uuid(), nullable=True),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('harassment', 'hate', 'spam', 'safety', 'other')",
            name=op.f("ck_reports_category"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'reviewed', 'actioned', 'dismissed')",
            name=op.f("ck_reports_status"),
        ),
        sa.CheckConstraint(
            "length(description) <= 500", name=op.f("ck_reports_description_length")
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name=op.f("fk_reports_message_id_messages")
        ),
        sa.ForeignKeyConstraint(
            ["reported_user"], ["users.id"], name=op.f("fk_reports_reported_user_users")
        ),
        sa.ForeignKeyConstraint(["reporter"], ["users.id"], name=op.f("fk_reports_reporter_users")),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], name=op.f("fk_reports_room_id_rooms")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
    )


def downgrade() -> None:
    op.drop_table("reports")
    with op.batch_alter_table("connection_requests", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_connection_requests_to_user"))
        batch_op.drop_index(batch_op.f("ix_connection_requests_from_user"))

    op.drop_table("connection_requests")
    with op.batch_alter_table("blocks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_blocks_blocker"))
        batch_op.drop_index(batch_op.f("ix_blocks_blocked"))

    op.drop_table("blocks")
