"""Room state fan-out. Views are personal (is_you, you_are_host, can_start), so each socket
gets its own copy built from one database read."""

import uuid

from fastapi import FastAPI

from backend.app.models import Room, Story
from backend.app.schemas.room import room_view
from backend.app.services.rooms import members_with_names
from backend.app.ws.events import envelope

# State events carry each viewer's room view; presence events only the online list.
STATE_EVENTS = ("joined", "left", "ready", "unready", "started")
PRESENCE_EVENTS = ("online", "offline")


async def notify_room(app: FastAPI, room_id: uuid.UUID, event: str, member_id: uuid.UUID) -> None:
    manager = app.state.ws
    connections = manager.connections(room_id)
    if not connections:
        return
    async with app.state.sessionmaker() as session:
        room = await session.get(Room, room_id)
        if room is None:
            return
        story = await session.get(Story, room.story_id)
        members = await members_with_names(session, room)
    online = sorted(str(m) for m in manager.online_members(room_id))
    for conn in connections:
        view = room_view(room, story, members, conn.user_id)
        await manager.send(
            conn,
            envelope(
                "room.member",
                room_id,
                {
                    "event": event,
                    "member_id": str(member_id),
                    "room": view.model_dump(mode="json"),
                    "online": online,
                },
            ),
        )


async def notify_presence(
    app: FastAPI, room_id: uuid.UUID, event: str, member_id: uuid.UUID
) -> None:
    """Online/offline: no database read, so it is safe in disconnect cleanup."""
    manager = app.state.ws
    online = sorted(str(m) for m in manager.online_members(room_id))
    await manager.broadcast(
        room_id,
        envelope(
            "room.member", room_id, {"event": event, "member_id": str(member_id), "online": online}
        ),
    )
