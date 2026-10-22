import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, UTCDateTime, utcnow


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint(
            "interaction_style IN ('thoughtful', 'playful', 'analytical')",
            name="interaction_style",
        ),
        CheckConstraint("visibility IN ('private', 'match_only')", name="visibility"),
        CheckConstraint("length(shareable_summary) <= 160", name="summary_length"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    interests: Mapped[list[str]] = mapped_column(JSON)
    genres: Mapped[list[str]] = mapped_column(JSON)
    activities: Mapped[list[str]] = mapped_column(JSON)
    interaction_style: Mapped[str] = mapped_column(String(16))
    preferred_roles: Mapped[list[str]] = mapped_column(JSON)
    availability: Mapped[list[str]] = mapped_column(JSON)
    visibility: Mapped[str] = mapped_column(String(16), default="private")
    shareable_summary: Mapped[str] = mapped_column(String(160), default="")
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
