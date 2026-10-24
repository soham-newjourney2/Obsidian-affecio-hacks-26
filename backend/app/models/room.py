import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, UTCDateTime, utcnow

ROOM_STATUSES = ("waiting", "active", "completed", "abandoned")
MEMBER_STATUSES = ("joined", "ready", "playing", "left", "removed")
PRESENT_STATUSES = ("joined", "ready", "playing")  # counted towards capacity


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (CheckConstraint(f"status IN {ROOM_STATUSES}", name="status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # sha256 of the invite code; cleared when the invite is revoked (on start or abandon).
    invite_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="waiting")
    host_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    story_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("stories.id"))
    story_version: Mapped[int] = mapped_column(Integer)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)  # invite expiry


class RoomMember(Base):
    __tablename__ = "room_members"
    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_room_members_room_user"),
        CheckConstraint(f"status IN {MEMBER_STATUSES}", name="status"),
        CheckConstraint("(user_id IS NULL) <> (companion_key IS NULL)", name="human_xor_companion"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rooms.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    companion_key: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="joined")
    role: Mapped[str | None] = mapped_column(String(40))
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    left_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
