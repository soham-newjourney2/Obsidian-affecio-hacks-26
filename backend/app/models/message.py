import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, UTCDateTime, utcnow

MESSAGE_TYPES = ("text", "system", "companion")
MODERATION_STATES = ("allowed", "hidden")
MAX_BODY = 1000


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # Dedupe: a client retrying the same send never creates a second row.
        UniqueConstraint("member_id", "client_message_id", name="uq_messages_member_client_id"),
        CheckConstraint(f"type IN {MESSAGE_TYPES}", name="type"),
        CheckConstraint(f"moderation IN {MODERATION_STATES}", name="moderation"),
        CheckConstraint(f"length(body) BETWEEN 1 AND {MAX_BODY}", name="body_length"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rooms.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("room_members.id", ondelete="CASCADE")
    )  # null = system
    type: Mapped[str] = mapped_column(String(16), default="text")
    body: Mapped[str] = mapped_column(Text)
    client_message_id: Mapped[str | None] = mapped_column(String(64))
    moderation: Mapped[str] = mapped_column(String(16), default="allowed")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
