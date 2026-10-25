import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models import Room, RoomMember, Story


class CreateRoomIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_slug: str = Field(max_length=40)


class JoinRoomIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=32)


class ReadyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool


class RoomStoryOut(BaseModel):
    slug: str
    title: str
    min_players: int
    max_players: int


class MemberOut(BaseModel):
    """What co-players see of each other: display name and seat state only."""

    member_id: uuid.UUID
    display_name: str
    status: Literal["joined", "ready", "playing"]
    is_host: bool
    is_you: bool
    is_companion: bool  # D12: AI companions are always labelled


class RoomOut(BaseModel):
    id: uuid.UUID
    status: Literal["waiting", "active", "completed", "abandoned"]
    story: RoomStoryOut
    members: list[MemberOut]
    you_are_host: bool
    can_start: bool
    invite_expires_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    session_id: uuid.UUID | None  # the game, once the case has started
    companions_allowed: bool  # demo mode, host, waiting and a free seat


class CreatedRoomOut(RoomOut):
    # Shown once: only a hash is stored, so the host's tab keeps the code.
    invite_code: str


def room_view(
    room: Room,
    story: Story,
    members: list[tuple[RoomMember, str]],
    viewer_id: uuid.UUID,
    session_id: uuid.UUID | None = None,
    demo: bool = False,
) -> RoomOut:
    you_are_host = room.host_user_id == viewer_id
    ready_count = sum(m.status == "ready" for m, _ in members)
    return RoomOut(
        id=room.id,
        status=room.status,
        story=RoomStoryOut(
            slug=story.slug,
            title=story.title,
            min_players=story.min_players,
            max_players=story.max_players,
        ),
        members=[
            MemberOut(
                member_id=m.id,
                display_name=name,
                status=m.status,
                is_host=m.user_id is not None and m.user_id == room.host_user_id,
                is_you=m.user_id is not None and m.user_id == viewer_id,
                is_companion=m.companion_key is not None,
            )
            for m, name in members
        ],
        you_are_host=you_are_host,
        can_start=(
            you_are_host
            and room.status == "waiting"
            and story.min_players <= len(members) <= story.max_players
            and ready_count == len(members)
        ),
        invite_expires_at=room.expires_at if room.invite_hash else None,
        created_at=room.created_at,
        started_at=room.started_at,
        session_id=session_id,
        companions_allowed=(
            demo and you_are_host and room.status == "waiting" and len(members) < story.max_players
        ),
    )
