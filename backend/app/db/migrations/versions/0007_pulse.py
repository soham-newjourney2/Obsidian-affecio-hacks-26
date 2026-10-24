"""pulse

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pulse_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("play_again", sa.String(length=8), nullable=False),
        sa.Column("ease_of_talking", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "play_again IN ('yes', 'maybe', 'no')", name=op.f("ck_pulse_responses_play_again")
        ),
        sa.CheckConstraint(
            "ease_of_talking BETWEEN 1 AND 5", name=op.f("ck_pulse_responses_ease_of_talking")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["game_sessions.id"],
            name=op.f("fk_pulse_responses_session_id_game_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_pulse_responses_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pulse_responses")),
        sa.UniqueConstraint("session_id", "user_id", name="uq_pulse_responses_session_user"),
    )
    with op.batch_alter_table("pulse_responses", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_pulse_responses_session_id"), ["session_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("pulse_responses", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_pulse_responses_session_id"))

    op.drop_table("pulse_responses")
