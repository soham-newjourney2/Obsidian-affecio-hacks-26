"""Importing this package registers every table on Base.metadata (used by Alembic)."""

from backend.app.models.game import GameEvent, GameSession, Vote
from backend.app.models.message import Message
from backend.app.models.profile import Profile
from backend.app.models.room import Room, RoomMember
from backend.app.models.story import Story
from backend.app.models.user import User

__all__ = [
    "GameEvent",
    "GameSession",
    "Message",
    "Profile",
    "Room",
    "RoomMember",
    "Story",
    "User",
    "Vote",
]
