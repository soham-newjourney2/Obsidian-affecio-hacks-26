"""ai_logs

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("turn", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('success', 'timeout', 'invalid', 'error', 'fallback')",
            name=op.f("ck_ai_logs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["game_sessions.id"],
            name=op.f("fk_ai_logs_session_id_game_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_logs")),
    )
    with op.batch_alter_table("ai_logs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_ai_logs_session_id"), ["session_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("ai_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ai_logs_session_id"))

    op.drop_table("ai_logs")
