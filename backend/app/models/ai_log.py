import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, UTCDateTime, utcnow

AI_STATUSES = ("success", "timeout", "invalid", "error", "fallback")


class AILog(Base):
    """One row per AI attempt. Never stores prompt or response bodies."""

    __tablename__ = "ai_logs"
    __table_args__ = (CheckConstraint(f"status IN {AI_STATUSES}", name="status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("game_sessions.id", ondelete="CASCADE"), index=True
    )
    turn: Mapped[int | None] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(20))  # groq | gemini | mock | fallback
    model: Mapped[str | None] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(40))
    purpose: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
