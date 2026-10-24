import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, UTCDateTime, utcnow


class PulseResponse(Base):
    """The 2-question pulse after a session: the only impact data ECHO collects."""

    __tablename__ = "pulse_responses"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_pulse_responses_session_user"),
        CheckConstraint("play_again IN ('yes', 'maybe', 'no')", name="play_again"),
        CheckConstraint("ease_of_talking BETWEEN 1 AND 5", name="ease_of_talking"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("game_sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    play_again: Mapped[str] = mapped_column(String(8))
    ease_of_talking: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
