import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, UTCDateTime, utcnow

SESSION_STATUSES = ("active", "completed", "failed", "abandoned")


class GameSession(Base):
    __tablename__ = "game_sessions"
    __table_args__ = (CheckConstraint(f"status IN {SESSION_STATUSES}", name="status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rooms.id", ondelete="CASCADE"), unique=True
    )
    story_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("stories.id"))
    story_version: Mapped[int] = mapped_column(Integer)
    variant_id: Mapped[str] = mapped_column(String(40))
    seed: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="active")
    scene_id: Mapped[str] = mapped_column(String(40))
    turn: Mapped[int] = mapped_column(Integer)
    state_version: Mapped[int] = mapped_column(Integer)  # compare-and-swap guard
    canonical_state: Mapped[dict[str, Any]] = mapped_column(JSON)
    outcome: Mapped[str | None] = mapped_column(String(16))  # ending kind
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class GameEvent(Base):
    __tablename__ = "game_events"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_game_events_session_seq"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("game_sessions.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    state_version: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(40))
    actor_member_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    visibility: Mapped[str] = mapped_column(String(60))  # "public" | "member:<id>"
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint("member_id", "client_action_id", name="uq_votes_member_action"),
        CheckConstraint("status IN ('active', 'superseded')", name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("game_sessions.id", ondelete="CASCADE"), index=True
    )
    turn: Mapped[int] = mapped_column(Integer)
    member_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("room_members.id"))
    choice_id: Mapped[str] = mapped_column(String(40))
    client_action_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
