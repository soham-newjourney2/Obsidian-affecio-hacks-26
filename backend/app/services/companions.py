"""AI companions (demo mode only): labelled seats that play along, never decide.

Per scene a companion pins its own revealed clue, says one line in chat (AI-rephrased, with an
authored fallback) and, once every human has voted, votes with the humans' majority.
Companions have no user account: they are excluded from matching, connections, pulse and stats.
"""

import asyncio
import logging
import uuid
from collections import Counter
from datetime import timedelta

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.content.companions import companion_name
from backend.app.core.errors import AppError
from backend.app.db.base import utcnow
from backend.app.game import engine
from backend.app.game.engine import GameError
from backend.app.models import GameSession, RoomMember, Story, User
from backend.app.services import ai_hooks, chat
from backend.app.services import game as game_service
from backend.app.services import rooms as room_service
from backend.app.ws.events import envelope
from backend.app.ws.notify import deliver_game

log = logging.getLogger("echo.companions")

COMPANION_DELAY_S = 1.5  # a beat, so companions don't act faster than people can read
REACT_TO = {"game.started", "game.scene", "game.vote.tally", "game.decision.resolved"}


async def add_companions(
    session: AsyncSession, user: User, room_id: uuid.UUID, count: int
) -> tuple:
    room = await room_service._locked_room(session, room_id)
    try:
        if room.host_user_id != user.id:
            raise AppError(403, "NOT_HOST", "Only the host can add companions.")
        if room.status != "waiting":
            raise AppError(409, "ROOM_NOT_WAITING", "This case has already begun.")
        story = await session.get(Story, room.story_id)
        present = await room_service.present_members(session, room)
        free = story.max_players - len(present)
        if free <= 0:
            raise AppError(409, "ROOM_FULL", "This room is full.")
    except AppError:
        await session.rollback()
        raise
    used = {m.companion_key for m in present if m.companion_key}
    added = []
    for n in range(1, len(used) + count + 2):
        key = f"companion-{n}"
        if key in used:
            continue
        # Distinct join times keep seat order stable (Wren, Moss, Ember).
        joined = utcnow() + timedelta(microseconds=len(added))
        member = RoomMember(room_id=room.id, companion_key=key, status="ready", joined_at=joined)
        session.add(member)
        added.append(member)
        if len(added) == min(count, free):
            break
    await session.commit()
    return room, added[0].id


def schedule(app: FastAPI, applied: game_service.Applied) -> None:
    if any(e["type"] in REACT_TO for e in applied.events):
        ai_hooks._spawn(app, _act(app, applied.session_id))


async def _act(app: FastAPI, session_id: uuid.UUID) -> None:
    await asyncio.sleep(COMPANION_DELAY_S)
    async with app.state.sessionmaker() as session:
        game = await session.get(GameSession, session_id)
        companions = {
            str(m.id): m
            for m in await session.scalars(
                select(RoomMember).where(
                    RoomMember.room_id == game.room_id, RoomMember.companion_key.is_not(None)
                )
            )
        }
        story = await session.get(Story, game.story_id)
    if not companions or game.status != "active":
        return
    content, state = story.config["content"], game.canonical_state
    for seat in state["seats"]:
        member_id = seat["member_id"]
        if not seat["active"] or member_id not in companions:
            continue
        state = await _share_and_speak(app, game, content, state, companions[member_id])
        state = await _vote(app, game, state, member_id, companions)


async def _apply(app: FastAPI, session_id: uuid.UUID, action: dict, state: dict) -> dict:
    try:
        applied = await game_service.apply_action(app, session_id, action)
    except GameError:
        return state
    if applied.events:
        await deliver_game(app, applied)
    return applied.state


async def _share_and_speak(app, game, content, state, member: RoomMember) -> dict:
    me = str(member.id)
    tool = engine._Story(content)
    on_board = {p["clue_id"] for p in state["board"]}
    mine = [c for c in state["revealed"] if state["clue_owner"].get(c) == me]
    for clue in [c for c in mine if c not in on_board][:1]:
        action = {"type": "share", "member_id": me, "action_id": f"share-{clue}", "clue_id": clue}
        state = await _apply(app, game.id, action, state)
    shared = [c for c in mine if c in {p["clue_id"] for p in state["board"]}]
    if shared:
        clue_text = tool.clue_text(shared[-1], state["variant"])
        base = f'I pinned what I found to the board: "{clue_text}"'
    else:
        base = "Nothing in my notes for this part yet. I'm listening: what have you all found?"
    await _say(app, game, content, state, member, base)
    return state


async def _say(app, game, content, state, member: RoomMember, base: str) -> None:
    cid = f"line-{state['scene']}"
    async with app.state.sessionmaker() as session:
        if await session.scalar(
            select(chat.Message.id).where(
                chat.Message.member_id == member.id, chat.Message.client_message_id == cid
            )
        ):
            return  # one line per scene
    result = await app.state.ai.run(
        purpose="companion",
        inputs={
            "scene": tool_title(content, state),
            "base": base,
            "speaker": companion_name(member.companion_key),
        },
        fallback=base,
        forbidden=ai_hooks.hidden_strings(content, state),
        session_id=game.id,
        turn=state["turn"],
    )
    async with app.state.sessionmaker() as session:
        member = await session.get(RoomMember, member.id)
        message, created = await chat.save_message(session, member, result.text, cid, "companion")
    if created:
        out = chat.message_out(message, companion_name(member.companion_key))
        await app.state.ws.broadcast(game.room_id, envelope("chat.message", game.room_id, out))


def tool_title(content: dict, state: dict) -> str:
    return next(s["title"] for s in content["scenes"] if s["id"] == state["scene"])


async def _vote(app, game, state, member_id: str, companions: dict) -> dict:
    """Follow the humans: vote only once every human seat has voted, with their majority."""
    humans = [
        s["member_id"] for s in state["seats"] if s["active"] and s["member_id"] not in companions
    ]
    if state["status"] != "active" or member_id in state["votes"] or not humans:
        return state
    if not all(h in state["votes"] for h in humans):
        return state
    counts = Counter(state["votes"][h] for h in humans)
    top = max(counts.values())
    choice = sorted(c for c, n in counts.items() if n == top)[0]
    action = {
        "type": "vote",
        "member_id": member_id,
        "action_id": f"vote-{state['turn']}",
        "choice_id": choice,
        "turn": state["turn"],
        "state_version": state["version"],
    }
    return await _apply(app, game.id, action, state)
