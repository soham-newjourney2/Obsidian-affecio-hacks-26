"""Background AI rewrites: scene narration, hints and the closing summary (§9).

Never on the play path: game events go out at once with the authored text; these tasks may later
replace it with validated AI text (an `ai_text` action + `game.ai_text` event). Inputs are the
minimum needed: titles, the authored text, shared board clues, display names. Never private
clues, emails or internal IDs.
"""

import asyncio
import logging
import uuid
from collections.abc import Coroutine
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select

from backend.app.game import engine
from backend.app.game.engine import GameError
from backend.app.models import GameSession, RoomMember, Story, User
from backend.app.services import game as game_service
from backend.app.services.results import table_facts
from backend.app.ws.notify import deliver_game

log = logging.getLogger("echo.ai")


def schedule(app: FastAPI, applied: game_service.Applied) -> None:
    """Called after each committed game change; starts the matching AI tasks."""
    for event in applied.events:
        payload = event["payload"]
        if event["type"] == "game.scene":
            _spawn(app, _narrate(app, applied.session_id, payload["scene_id"]))
        elif event["type"] == "game.hint":
            _spawn(app, _hint(app, applied.session_id, payload["scene_id"], payload["level"]))
        elif event["type"] == "game.completed" and payload.get("ending_id"):
            _spawn(app, _summary(app, applied.session_id))


def _spawn(app: FastAPI, coro: Coroutine[Any, Any, None]) -> None:
    task = asyncio.get_running_loop().create_task(_guard(coro))
    app.state.ai_tasks.add(task)
    task.add_done_callback(app.state.ai_tasks.discard)


async def _guard(coro: Coroutine[Any, Any, None]) -> None:
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception:  # an AI hiccup must never surface to players
        log.exception("ai task failed")


async def wait_idle(app: FastAPI) -> None:
    """Test helper: waits until every pending AI task has finished."""
    while app.state.ai_tasks:
        await asyncio.gather(*list(app.state.ai_tasks), return_exceptions=True)


# ---- context --------------------------------------------------------------------------------


async def _load(app: FastAPI, session_id: uuid.UUID):
    async with app.state.sessionmaker() as session:
        game = await session.get(GameSession, session_id)
        story = await session.get(Story, game.story_id)
        names = list(
            await session.scalars(
                select(User.display_name)
                .join(RoomMember, RoomMember.user_id == User.id)
                .where(RoomMember.room_id == game.room_id, RoomMember.role.is_not(None))
                .order_by(RoomMember.joined_at, RoomMember.id)
            )
        )
    return game, story, story.config["content"], names


def hidden_strings(content: dict, state: dict, *, reveal_board: bool = True) -> list[str]:
    """Text an AI output must never contain: unshared clue wording, every solution, ending
    texts and internal IDs. Clues already on the shared board may be mentioned."""
    on_board = {p["clue_id"] for p in state.get("board", [])} if reveal_board else set()
    out: list[str] = []
    for clue in content["clues"]:
        out.append(clue["id"])
        if clue["id"] in on_board:
            continue
        out.append(clue["text"])
        out.extend(clue.get("text_by_variant", {}).values())
    out += [v["solution_summary"] for v in content["variants"]] + [
        v["id"] for v in content["variants"]
    ]
    out += [e["text"] for e in content["endings"]] + [e["id"] for e in content["endings"]]
    out += [d["id"] for d in content["decisions"]] + [s["id"] for s in content["scenes"]]
    out += [c["id"] for d in content["decisions"] for c in d["choices"]]
    return out


async def _store(app: FastAPI, session_id: uuid.UUID, key: str, text: str, scene_id: str | None):
    action = {"type": "ai_text", "key": key, "text": text, "scene_id": scene_id}
    try:
        applied = await game_service.apply_action(app, session_id, action)
    except GameError:
        return
    if applied.events:
        await deliver_game(app, applied)


# ---- tasks ----------------------------------------------------------------------------------


async def _narrate(app: FastAPI, session_id: uuid.UUID, scene_id: str) -> None:
    game, story, content, names = await _load(app, session_id)
    state = game.canonical_state
    if state["scene"] != scene_id or state["status"] != "active":
        return
    scene = next(s for s in content["scenes"] if s["id"] == scene_id)
    tool = engine._Story(content)
    board = [tool.clue_text(p["clue_id"], state["variant"]) for p in state["board"]]
    inputs = {
        "story": story.title,
        "scene": scene["title"],
        "base": scene["narration_base"],
        "objective": scene["objective"],
        "board": board,
        "players": names,
    }
    result = await app.state.ai.run(
        purpose="narrate",
        inputs=inputs,
        fallback=scene["narration_base"],
        forbidden=hidden_strings(content, state),
        session_id=session_id,
        turn=state["turn"],
    )
    if result.provider != "fallback" and result.text != scene["narration_base"]:
        await _store(app, session_id, f"narration:{scene_id}", result.text, scene_id)


async def _hint(app: FastAPI, session_id: uuid.UUID, scene_id: str, level: int) -> None:
    game, story, content, _ = await _load(app, session_id)
    state = game.canonical_state
    if state["scene"] != scene_id:
        return
    scene = next(s for s in content["scenes"] if s["id"] == scene_id)
    base = next(h["levels"][level - 1] for h in content["hints"] if h["scene_id"] == scene_id)
    inputs = {
        "story": story.title,
        "scene": scene["title"],
        "objective": scene["objective"],
        "level": level,
        "base": base,
    }
    result = await app.state.ai.run(
        purpose="hint",
        inputs=inputs,
        fallback=base,
        forbidden=hidden_strings(content, state),
        session_id=session_id,
        turn=state["turn"],
    )
    if result.provider != "fallback" and result.text != base:
        await _store(app, session_id, f"hint:{scene_id}:{level}", result.text, scene_id)


async def _summary(app: FastAPI, session_id: uuid.UUID) -> None:
    async with app.state.sessionmaker() as session:
        game = await session.get(GameSession, session_id)
        story = await session.get(Story, game.story_id)
        facts = await table_facts(session, game)
    content = story.config["content"]
    result = await app.state.ai.run(
        purpose="summary",
        inputs=facts,
        fallback=facts["base"],
        forbidden=hidden_strings(content, {"board": []}, reveal_board=False),
        session_id=session_id,
        turn=game.turn,
    )
    if result.provider != "fallback" and result.text != facts["base"]:
        await _store(app, session_id, "summary", result.text, None)
