"""Game sessions: start from a room, apply actions with compare-and-swap, schedule vote timers.

Every action runs under an in-process asyncio.Lock per session, and the write is a CAS:
`UPDATE game_sessions SET state_version = v+1 ... WHERE id = ? AND state_version = v`.
If another writer won (rowcount 0) the action is re-applied to the fresh state.
"""

import asyncio
import logging
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import utcnow
from backend.app.game import engine
from backend.app.game.engine import GameError
from backend.app.models import GameEvent, GameSession, Room, RoomMember, Story, Vote
from backend.app.ws.notify import deliver_game

log = logging.getLogger("echo.game")

VOTE_GRACE_S = 45.0
CAS_ATTEMPTS = 3
TICK_SLACK_S = 0.05


@dataclass(frozen=True)
class Applied:
    session_id: uuid.UUID
    room_id: uuid.UUID
    content: dict[str, Any]
    state: dict[str, Any]
    events: list[dict[str, Any]]


async def _content(session: AsyncSession, story_id: uuid.UUID) -> dict[str, Any]:
    story = await session.get(Story, story_id)
    return story.config["content"]


async def session_for_room(session: AsyncSession, room_id: uuid.UUID) -> GameSession | None:
    return await session.scalar(select(GameSession).where(GameSession.room_id == room_id))


async def _record_events(
    session: AsyncSession, game: GameSession, events: list[dict], version: int, actor: str | None
) -> None:
    last = await session.scalar(
        select(func.max(GameEvent.seq)).where(GameEvent.session_id == game.id)
    )
    for offset, event in enumerate(events, start=1):
        session.add(
            GameEvent(
                session_id=game.id,
                seq=(last or 0) + offset,
                state_version=version,
                type=event["type"],
                actor_member_id=uuid.UUID(actor) if actor else None,
                visibility=event["visibility"],
                payload=event["payload"],
            )
        )


async def start_game(app: FastAPI, room_id: uuid.UUID) -> Applied:
    """Creates the session for a just-started room. Seats are the members now playing."""
    async with app.state.sessionmaker() as session:
        room = await session.get(Room, room_id)
        members = list(
            await session.scalars(
                select(RoomMember)
                .where(RoomMember.room_id == room_id, RoomMember.status == "playing")
                .order_by(RoomMember.joined_at, RoomMember.id)
            )
        )
        content = await _content(session, room.story_id)
        seed = secrets.randbits(31)
        state, events = engine.start(
            content, [str(m.id) for m in members], seed, time.time(), {"vote_grace_s": VOTE_GRACE_S}
        )
        game = GameSession(
            room_id=room.id,
            story_id=room.story_id,
            story_version=room.story_version,
            variant_id=state["variant"],
            seed=seed,
            scene_id=state["scene"],
            turn=state["turn"],
            state_version=state["version"],
            canonical_state=state,
        )
        session.add(game)
        await session.flush()
        roles = {s["member_id"]: s["roles"] for s in state["seats"]}
        for member in members:
            member.role = ",".join(roles[str(member.id)])
        await _record_events(session, game, events, state["version"], None)
        await session.commit()
        return Applied(game.id, room.id, content, state, events)


async def apply_action(app: FastAPI, session_id: uuid.UUID, action: dict) -> Applied:
    """Applies one action atomically. Raises GameError for rule violations."""
    async with app.state.game_locks[session_id]:
        for _ in range(CAS_ATTEMPTS):
            async with app.state.sessionmaker() as session:
                game = await session.get(GameSession, session_id, populate_existing=True)
                if game is None:
                    raise GameError("NO_SESSION")
                content = await _content(session, game.story_id)
                expected = game.state_version
                state, events = engine.apply(content, game.canonical_state, action, time.time())
                if not events:  # idempotent repeat or nothing due
                    return Applied(game.id, game.room_id, content, state, [])
                values = {
                    "canonical_state": state,
                    "state_version": state["version"],
                    "scene_id": state["scene"],
                    "turn": state["turn"],
                    "status": state["status"],
                }
                if state["status"] != "active":
                    ending = state["ending"]
                    values["outcome"] = (
                        engine._Story(content).endings[ending]["kind"] if ending else "abandoned"
                    )
                    values["ended_at"] = utcnow()
                result = await session.execute(
                    update(GameSession)
                    .where(GameSession.id == game.id, GameSession.state_version == expected)
                    .values(**values)
                )
                if result.rowcount != 1:  # lost the race: retry on the fresh state
                    await session.rollback()
                    continue
                actor = action.get("member_id")
                await _record_events(session, game, events, state["version"], actor)
                if action["type"] == "vote":
                    await _record_vote(session, game.id, action)
                if state["status"] != "active":
                    room = await session.get(Room, game.room_id)
                    room.status = "completed" if state["status"] == "completed" else "abandoned"
                    room.ended_at = utcnow()
                await session.commit()
                applied = Applied(game.id, game.room_id, content, state, events)
                _schedule_tick(app, applied)
                return applied
        raise GameError("CONFLICT")


async def _record_vote(session: AsyncSession, session_id: uuid.UUID, action: dict) -> None:
    member_id = uuid.UUID(action["member_id"])
    await session.execute(
        update(Vote)
        .where(
            Vote.session_id == session_id,
            Vote.member_id == member_id,
            Vote.turn == action["turn"],
            Vote.status == "active",
        )
        .values(status="superseded")
    )
    session.add(
        Vote(
            session_id=session_id,
            turn=action["turn"],
            member_id=member_id,
            choice_id=action["choice_id"],
            client_action_id=action["action_id"],
        )
    )


def _schedule_tick(app: FastAPI, applied: Applied) -> None:
    """When a majority starts the grace clock, resolve the vote once it runs out."""
    timers: dict = app.state.game_timers
    previous = timers.pop(applied.session_id, None)
    if previous is not None and previous is not asyncio.current_task():
        previous.cancel()
    state = applied.state
    if state["status"] != "active" or state["majority_since"] is None:
        return
    deadline = state["majority_since"] + state["rules"]["vote_grace_s"]
    timers[applied.session_id] = asyncio.get_running_loop().create_task(
        _tick_at(app, applied.session_id, deadline)
    )


async def _tick_at(app: FastAPI, session_id: uuid.UUID, deadline: float) -> None:
    # Wake a little after the deadline: sleeping exactly to it can land a hair early.
    await asyncio.sleep(max(0.0, deadline - time.time()) + TICK_SLACK_S)
    if app.state.game_timers.get(session_id) is asyncio.current_task():
        del app.state.game_timers[session_id]
    try:
        applied = await apply_action(app, session_id, {"type": "tick"})
    except GameError:
        return
    if applied.events:
        await deliver_game(app, applied)
    else:  # not due after all (or a newer vote moved the clock): look again
        _schedule_tick(app, applied)


def cancel_timers(app: FastAPI) -> None:
    for task in app.state.game_timers.values():
        task.cancel()
    app.state.game_timers.clear()


async def leave_game(app: FastAPI, room_id: uuid.UUID, member_id: uuid.UUID) -> Applied | None:
    """Frees a member's seat when they leave mid-game (their vote no longer counts)."""
    async with app.state.sessionmaker() as session:
        game = await session_for_room(session, room_id)
    if game is None or game.status != "active":
        return None
    try:
        return await apply_action(
            app,
            game.id,
            {
                "type": "leave",
                "member_id": str(member_id),
                "action_id": f"leave-{uuid.uuid4().hex}",
            },
        )
    except GameError:  # already unseated or game over
        return None
