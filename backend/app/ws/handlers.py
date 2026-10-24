"""`/ws/rooms/{room_id}`: auth-first, members only, membership re-checked on every frame.

Close codes: 4401 no/invalid/expired auth (or none within AUTH_TIMEOUT_S), 4403 not a member
(including after leaving or being removed). Errors on a live socket are `error{code, ref_id}`.
"""

import asyncio
import contextlib
import time
import uuid
from datetime import timedelta

import anyio
from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.app.core.errors import AppError
from backend.app.core.security import InvalidToken, decode_access_token
from backend.app.db.base import utcnow
from backend.app.models import Room, RoomMember, Story, User
from backend.app.models.room import PRESENT_STATUSES
from backend.app.schemas.room import room_view
from backend.app.services import chat
from backend.app.services import rooms as room_service
from backend.app.ws.events import (
    MAX_FRAME_BYTES,
    AuthIn,
    ChatSendIn,
    ClientFrame,
    ReadyIn,
    envelope,
    error,
)
from backend.app.ws.manager import Connection
from backend.app.ws.notify import notify_presence, notify_room

router = APIRouter()

AUTH_TIMEOUT_S = 5.0
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403
SEEN_EVERY = timedelta(seconds=20)  # last_seen_at write throttle


class _Closed(Exception):
    """Raised by a handler after it has closed the socket."""


async def _close(ws: WebSocket, code: int) -> None:
    with contextlib.suppress(Exception):
        await ws.close(code)


async def _authenticate(ws: WebSocket, room_id: uuid.UUID) -> Connection | None:
    app = ws.app
    try:
        raw = await asyncio.wait_for(ws.receive_text(), AUTH_TIMEOUT_S)
        frame = ClientFrame.model_validate_json(raw)
        if frame.type != "auth" or len(raw.encode()) > MAX_FRAME_BYTES:
            raise ValueError("first frame must be auth")
        token = AuthIn.model_validate(frame.payload).token
        claims = decode_access_token(token, app.state.settings.secret_key.get_secret_value())
        user_id = uuid.UUID(claims.sub)
    except (TimeoutError, WebSocketDisconnect, KeyError, ValueError, ValidationError, InvalidToken):
        await _close(ws, CLOSE_UNAUTHORIZED)
        return None
    if app.state.denylist.is_revoked(claims.jti):
        await _close(ws, CLOSE_UNAUTHORIZED)
        return None
    async with app.state.sessionmaker() as session:
        user = await session.get(User, user_id)
        if user is None or user.status != "active":
            await _close(ws, CLOSE_UNAUTHORIZED)
            return None
        member = await room_service.member_of(session, room_id, user.id)
        if member is None or member.status not in PRESENT_STATUSES:
            await _close(ws, CLOSE_FORBIDDEN)
            return None
        return Connection(
            ws=ws, room_id=room_id, member_id=member.id, user_id=user.id, claims=claims
        )


async def _snapshot(app: FastAPI, conn: Connection) -> dict:
    async with app.state.sessionmaker() as session:
        room = await session.get(Room, conn.room_id)
        story = await session.get(Story, room.story_id)
        members = await room_service.members_with_names(session, room)
        history = await chat.recent_messages(session, conn.room_id)
    return {
        "room": room_view(room, story, members, conn.user_id).model_dump(mode="json"),
        "you": str(conn.member_id),
        "online": sorted(str(m) for m in app.state.ws.online_members(conn.room_id)),
        "messages": [chat.message_out(m, name) for m, name in history],
    }


async def _touch(app: FastAPI, member_id: uuid.UUID, *, force: bool = False) -> None:
    async with app.state.sessionmaker() as session:
        member = await session.get(RoomMember, member_id)
        now = utcnow()
        if member is not None and (
            force or member.last_seen_at is None or now - member.last_seen_at >= SEEN_EVERY
        ):
            member.last_seen_at = now
            await session.commit()


async def _on_chat(
    app: FastAPI, conn: Connection, member: RoomMember, frame: ClientFrame, session
) -> None:
    manager = app.state.ws
    if not app.state.chat_bucket.take(str(conn.member_id)):
        await manager.send(conn, error(conn.room_id, "RATE_LIMITED", frame.id))
        return
    room = await session.get(Room, conn.room_id)
    if room.status not in ("waiting", "active"):
        await manager.send(conn, error(conn.room_id, "ROOM_CLOSED", frame.id))
        return
    data = ChatSendIn.model_validate(frame.payload)
    user = await session.get(User, conn.user_id)
    message, created = await chat.save_message(session, member, data.body, data.client_message_id)
    out = envelope("chat.message", conn.room_id, chat.message_out(message, user.display_name))
    if created:
        await manager.broadcast(conn.room_id, out)
    else:  # a retry: confirm to the sender only, never a second copy for everyone
        await manager.send(conn, out)


async def _on_ready(app: FastAPI, conn: Connection, frame: ClientFrame, session) -> None:
    ready = ReadyIn.model_validate(frame.payload).ready
    user = await session.get(User, conn.user_id)
    await room_service.set_ready(session, user, conn.room_id, ready)
    await notify_room(app, conn.room_id, "ready" if ready else "unready", conn.member_id)


async def _on_leave(app: FastAPI, conn: Connection, session) -> None:
    user = await session.get(User, conn.user_id)
    await room_service.leave_room(session, user, conn.room_id)
    conn.open = False  # stop receiving; tell the others before the socket goes away
    await notify_room(app, conn.room_id, "left", conn.member_id)
    await app.state.ws.close_member(conn.room_id, conn.member_id, 1000)
    await _close(conn.ws, 1000)
    raise _Closed


async def _handle(app: FastAPI, conn: Connection, raw: str) -> None:
    manager = app.state.ws
    if len(raw.encode()) > MAX_FRAME_BYTES:
        await manager.send(conn, error(conn.room_id, "FRAME_TOO_LARGE"))
        return
    try:
        frame = ClientFrame.model_validate_json(raw)
    except ValidationError:
        await manager.send(conn, error(conn.room_id, "INVALID_FRAME"))
        return

    # The token can be revoked (logout) or expire while the socket is open.
    if app.state.denylist.is_revoked(conn.claims.jti) or conn.claims.exp <= time.time():
        await _close(conn.ws, CLOSE_UNAUTHORIZED)
        raise _Closed

    async with app.state.sessionmaker() as session:
        member = await session.get(RoomMember, conn.member_id)
        if member is None or member.status not in PRESENT_STATUSES:
            await _close(conn.ws, CLOSE_FORBIDDEN)
            raise _Closed
        try:
            if frame.type == "presence.ping":
                await _touch(app, conn.member_id)
            elif frame.type == "chat.send":
                await _on_chat(app, conn, member, frame, session)
            elif frame.type == "player.ready":
                await _on_ready(app, conn, frame, session)
            elif frame.type == "room.leave":
                await _on_leave(app, conn, session)
            else:
                await manager.send(conn, error(conn.room_id, "UNKNOWN_TYPE", frame.id))
        except ValidationError:
            await manager.send(conn, error(conn.room_id, "VALIDATION_ERROR", frame.id))
        except AppError as exc:
            await manager.send(conn, error(conn.room_id, exc.code, frame.id))


@router.websocket("/ws/rooms/{room_id}")
async def room_socket(ws: WebSocket, room_id: uuid.UUID) -> None:
    await ws.accept()
    app = ws.app
    conn = await _authenticate(ws, room_id)
    if conn is None:
        return
    manager = app.state.ws
    came_online = manager.add(conn)
    try:
        await _touch(app, conn.member_id, force=True)
        await manager.send(conn, envelope("room.snapshot", room_id, await _snapshot(app, conn)))
        if came_online:
            await notify_presence(app, room_id, "online", conn.member_id)
        while conn.open:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break
            text = message.get("text")
            if text is None:  # binary frames are not part of the protocol
                await manager.send(conn, error(room_id, "INVALID_FRAME"))
                continue
            await _handle(app, conn, text)
    except (_Closed, WebSocketDisconnect):
        pass
    finally:
        # Shielded (in-memory sends only): the offline notice goes out even if cancelled.
        with anyio.CancelScope(shield=True):
            if manager.remove(conn):
                await notify_presence(app, room_id, "offline", conn.member_id)
