import uuid
from datetime import date
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

RIGHTS_STATUSES = ("review_required", "verified_public_domain", "excluded")


class Story(Base):
    __tablename__ = "stories"
    __table_args__ = (
        CheckConstraint(f"rights_status IN {RIGHTS_STATUSES}", name="rights_status"),
        CheckConstraint("min_players <= max_players", name="player_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(280))
    genres: Mapped[list[str]] = mapped_column(JSON)
    inspiration_title: Mapped[str] = mapped_column(String(120))
    inspiration_author: Mapped[str] = mapped_column(String(80))
    publication_year: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str] = mapped_column(String(400))
    rights_status: Mapped[str] = mapped_column(String(32))
    rights_notes: Mapped[str] = mapped_column(Text)
    rights_reviewed_at: Mapped[date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer)
    min_players: Mapped[int] = mapped_column(Integer)
    max_players: Mapped[int] = mapped_column(Integer)
    est_minutes: Mapped[int | None] = mapped_column(Integer)
    playable: Mapped[bool] = mapped_column(Boolean)
    # The full validated story file (content included). Never sent to clients as-is.
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
