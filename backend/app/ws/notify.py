"""Room state fan-out. Views are personal (is_you, you_are_host, can_start), so each socket
gets its own copy built from one database read."""

import uuid
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select

from backend.app.game import engine
from backend.app.models import GameSession, Room, Story
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
        game_id = await session.scalar(select(GameSession.id).where(GameSession.room_id == room_id))
    online = sorted(str(m) for m in manager.online_members(room_id))
    for conn in connections:
        view = room_view(room, story, members, conn.user_id, session_id=game_id)
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


async def deliver_game(app: FastAPI, applied: Any) -> None:
    """Sends game events to each socket: only events addressed to it (public, or its own member
    id), each carrying that member's own projection. Private clues never leave their owner.
    Then starts any AI rewrites, so a rewrite can never overtake the event it rewrites."""
    try:
        await _send_game(app, applied)
    finally:
        hook = getattr(app.state, "on_game_change", None)  # services/ai_hooks.schedule
        if hook is not None and applied.events:
            hook(app, applied)


async def _send_game(app: FastAPI, applied: Any) -> None:
    manager = app.state.ws
    for conn in manager.connections(applied.room_id):
        member = str(conn.member_id)
        mine = [e for e in applied.events if e["visibility"] in ("public", f"member:{member}")]
        if not mine:
            continue
        projection = engine.view(applied.content, applied.state, member)
        for event in mine:
            await manager.send(
                conn,
                envelope(
                    event["type"],
                    applied.room_id,
                    {
                        **event["payload"],
                        "session_id": str(applied.session_id),
                        "state_version": applied.state["version"],
                        "view": projection,
                    },
                ),
            )
