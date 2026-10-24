import uuid
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.deps import CurrentUser, SessionDep
from backend.app.core.errors import AppError
from backend.app.game import engine
from backend.app.models import GameSession, Story
from backend.app.models.room import PRESENT_STATUSES
from backend.app.services.results import build_summary, load_finished, save_pulse
from backend.app.services.rooms import member_of

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/{session_id}")
async def snapshot(session_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> dict:
    """The caller's own projection of the game: never anyone else's private clues."""
    game = await session.get(GameSession, session_id)
    if game is None:
        raise AppError(404, "SESSION_NOT_FOUND", "Game not found.")
    member = await member_of(session, game.room_id, user.id)
    if member is None or member.status not in PRESENT_STATUSES:
        raise AppError(403, "NOT_A_MEMBER", "You are not in this game.")
    story = await session.get(Story, game.story_id)
    return {
        "session_id": str(game.id),
        "room_id": str(game.room_id),
        "view": engine.view(story.config["content"], game.canonical_state, str(member.id)),
    }


@router.get("/{session_id}/summary")
async def summary(session_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> dict:
    """Ending, solution and reflection for a finished case, built from recorded events only."""
    game, member = await load_finished(session, session_id, user)
    return await build_summary(session, game, member)


class PulseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    play_again: Literal["yes", "maybe", "no"]
    ease_of_talking: int = Field(ge=1, le=5)


@router.post("/{session_id}/pulse", status_code=201)
async def pulse(
    session_id: uuid.UUID, body: PulseIn, user: CurrentUser, session: SessionDep
) -> Response:
    """Two questions, once per person per case."""
    game, member = await load_finished(session, session_id, user)
    await save_pulse(session, game, member, body.play_again, body.ease_of_talking)
    return Response(status_code=201)
