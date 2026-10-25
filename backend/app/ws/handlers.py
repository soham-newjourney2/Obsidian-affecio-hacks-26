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

from backend.app.ai.chain import validate_theory
from backend.app.core.errors import AppError
from backend.app.core.security import InvalidToken, decode_access_token
from backend.app.db.base import utcnow
from backend.app.game import engine
from backend.app.game.engine import GameError
from backend.app.models import Room, RoomMember, Story, User
from backend.app.models.room import PRESENT_STATUSES
from backend.app.schemas.room import room_view
from backend.app.services import chat
from backend.app.services import game as game_service
from backend.app.services import rooms as room_service
from backend.app.ws.events import (
    MAX_FRAME_BYTES,
    AuthIn,
    ChatSendIn,
    ClientFrame,
    GameHintIn,
    GameShareIn,
    GameTheoryIn,
    GameVoteIn,
    ReadyIn,
    envelope,
    error,
)
from backend.app.ws.manager import Connection
from backend.app.ws.notify import deliver_game, notify_presence, notify_room

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
        game = await game_service.session_for_room(session, conn.room_id)
    view = room_view(
        room, story, members, conn.user_id, session_id=game.id if game else None,
        demo=app.state.settings.demo_mode,
    )  # fmt: skip
    return {
        "room": view.model_dump(mode="json"),
        "you": str(conn.member_id),
        "online": sorted(str(m) for m in app.state.ws.online_members(conn.room_id)),
        "messages": [chat.message_out(m, name) for m, name in history],
        # Reconnect resync: this member's own projection only.
        "game": engine.view(story.config["content"], game.canonical_state, str(conn.member_id))
        if game
        else None,
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
    freed = await game_service.leave_game(app, conn.room_id, conn.member_id)
    if freed:
        await deliver_game(app, freed)
    await notify_room(app, conn.room_id, "left", conn.member_id)
    await app.state.ws.close_member(conn.room_id, conn.member_id, 1000)
    await _close(conn.ws, 1000)
    raise _Closed


GAME_ACTIONS = {
    "game.vote": (GameVoteIn, "vote"),
    "game.hint.request": (GameHintIn, "hint"),
    "game.clue.share": (GameShareIn, "share"),
}


async def _on_game(app: FastAPI, conn: Connection, frame: ClientFrame, session) -> None:
    manager = app.state.ws
    model, kind = GAME_ACTIONS[frame.type]
    data = model.model_validate(frame.payload)
    if not app.state.game_bucket.take(str(conn.member_id)):
        await manager.send(conn, error(conn.room_id, "RATE_LIMITED", frame.id))
        return
    game = await game_service.session_for_room(session, conn.room_id)
    if game is None:
        await manager.send(conn, error(conn.room_id, "NO_SESSION", frame.id))
        return
    action = {
        "type": kind,
        "member_id": str(conn.member_id),  # identity comes from the socket, never the payload
        "action_id": data.client_action_id,
        **data.model_dump(exclude={"client_action_id"}),
    }
    try:
        applied = await game_service.apply_action(app, game.id, action)
    except GameError as exc:
        await manager.send(conn, error(conn.room_id, exc.code, frame.id))
        if exc.code == "STALE_STATE":  # plus a fresh snapshot to resync from
            await manager.send(
                conn, envelope("room.snapshot", conn.room_id, await _snapshot(app, conn))
            )
        return
    if applied.events:
        await deliver_game(app, applied)


async def _on_theory(app: FastAPI, conn: Connection, frame: ClientFrame, session) -> None:
    """Free text -> AI -> one allowed choice (or none) -> a suggestion. Never a vote (D13)."""
    manager = app.state.ws
    data = GameTheoryIn.model_validate(frame.payload)
    if not app.state.theory_bucket.take(str(conn.member_id)):
        await manager.send(conn, error(conn.room_id, "RATE_LIMITED", frame.id))
        return
    game = await game_service.session_for_room(session, conn.room_id)
    if game is None or game.status != "active":
        await manager.send(conn, error(conn.room_id, "NO_SESSION", frame.id))
        return
    story = await session.get(Story, game.story_id)
    content, state = story.config["content"], game.canonical_state
    tool = engine._Story(content)
    decision = tool.decision_for(state["scene"])
    if decision["id"] == engine.CONTINUE:
        await manager.send(conn, error(conn.room_id, "NO_DECISION", frame.id))
        return
    scene = tool.scenes[state["scene"]]
    choices = [{"id": c["id"], "label": c["label"]} for c in decision["choices"]]
    inputs = {
        "scene": scene["title"],
        "objective": scene["objective"],
        "question": decision["prompt"],
        "choices": choices,
        "board": [tool.clue_text(p["clue_id"], state["variant"]) for p in state["board"]],
        "theory": data.text,
    }
    allowed = {c["id"] for c in choices}
    result = await app.state.ai.run(
        purpose="theory",
        inputs=inputs,
        fallback={"choice_id": None, "confidence": 0.0},
        session_id=game.id,
        turn=state["turn"],
        validate=lambda out: validate_theory(out, allowed),
    )
    action = {
        "type": "theory",
        "member_id": str(conn.member_id),
        "action_id": data.client_action_id,
        "choice_id": result.text["choice_id"],
    }
    try:
        applied = await game_service.apply_action(app, game.id, action)
    except GameError as exc:
        await manager.send(conn, error(conn.room_id, exc.code, frame.id))
        return
    if applied.events:
        await deliver_game(app, applied)


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
            elif frame.type == "game.theory.submit":
                await _on_theory(app, conn, frame, session)
            elif frame.type in GAME_ACTIONS:
                await _on_game(app, conn, frame, session)
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
