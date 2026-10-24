import uuid

from fastapi import APIRouter

from backend.app.api.deps import CurrentUser, SessionDep
from backend.app.core.errors import AppError
from backend.app.game import engine
from backend.app.models import GameSession, Story
from backend.app.models.room import PRESENT_STATUSES
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
