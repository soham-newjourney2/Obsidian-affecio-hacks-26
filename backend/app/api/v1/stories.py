from fastapi import APIRouter

from backend.app.api.deps import SessionDep
from backend.app.core.errors import AppError
from backend.app.schemas.story import StoryCard, StoryDetail, to_card, to_detail
from backend.app.services.stories import get_story, list_catalogue

router = APIRouter(prefix="/stories", tags=["stories"])


@router.get("")
async def catalogue(session: SessionDep) -> list[StoryCard]:
    return [to_card(story) for story in await list_catalogue(session)]


@router.get("/{slug}")
async def story_detail(slug: str, session: SessionDep) -> StoryDetail:
    story = await get_story(session, slug)
    if story is None:
        raise AppError(404, "STORY_NOT_FOUND", "Story not found.")
    return to_detail(story)
