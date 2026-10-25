import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, UTCDateTime, utcnow

REPORT_CATEGORIES = ("harassment", "hate", "spam", "safety", "other")


class ConnectionRequest(Base):
    """Mutual opt-in between human co-players of a finished case (P16)."""

    __tablename__ = "connection_requests"
    __table_args__ = (
        UniqueConstraint("session_id", "from_user", "to_user", name="uq_connection_requests_pair"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'withdrawn')", name="status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("game_sessions.id", ondelete="CASCADE")
    )
    from_user: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    to_user: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("blocker", "blocked", name="uq_blocks_pair"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    blocker: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    blocked: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(f"category IN {REPORT_CATEGORIES}", name="category"),
        CheckConstraint("status IN ('open', 'reviewed', 'actioned', 'dismissed')", name="status"),
        CheckConstraint("length(description) <= 500", name="description_length"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reporter: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    reported_user: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    room_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("rooms.id"))
    message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("messages.id"))
    category: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(10), default="open")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
