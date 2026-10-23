"""Story files -> validated StoryFile -> `stories` rows. Seeding is idempotent by slug."""

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.game.story_schema import StoryFile
from backend.app.models import Story

STORIES_DIR = Path(__file__).resolve().parents[1] / "content" / "stories"


def load_story_files(directory: Path = STORIES_DIR) -> list[StoryFile]:
    """Parses and validates every *.json story; raises on the first invalid file."""
    stories = []
    for path in sorted(directory.glob("*.json")):
        try:
            story = StoryFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except ValueError as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
        if story.story_id != path.stem:
            raise ValueError(f"{path.name}: story_id {story.story_id!r} must match file name")
        stories.append(story)
    return stories


def _row_values(story: StoryFile) -> dict:
    rights = story.rights
    return {
        "title": story.title,
        "description": story.description,
        "genres": list(story.genres),
        "inspiration_title": rights.inspiration_title,
        "inspiration_author": rights.inspiration_author,
        "publication_year": rights.publication_year,
        "source_url": rights.source_url,
        "rights_status": rights.status,
        "rights_notes": rights.notes,
        "rights_reviewed_at": rights.reviewed_at,
        "version": story.version,
        "min_players": story.min_players,
        "max_players": story.max_players,
        "est_minutes": story.est_minutes,
        "playable": story.playable,
        "config": story.model_dump(mode="json"),
    }


@dataclass(frozen=True)
class SeedResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0


async def seed_stories(session: AsyncSession, stories: list[StoryFile]) -> SeedResult:
    created = updated = unchanged = 0
    for story in stories:
        values = _row_values(story)
        row = await session.scalar(select(Story).where(Story.slug == story.story_id))
        if row is None:
            session.add(Story(slug=story.story_id, **values))
            created += 1
        elif any(getattr(row, key) != value for key, value in values.items()):
            for key, value in values.items():
                setattr(row, key, value)
            updated += 1
        else:
            unchanged += 1
    await session.commit()
    return SeedResult(created, updated, unchanged)


async def list_catalogue(session: AsyncSession) -> list[Story]:
    """Visible stories: playable first, then by title. Excluded rights never show."""
    result = await session.scalars(
        select(Story)
        .where(Story.rights_status != "excluded")
        .order_by(case((Story.playable, 0), else_=1), Story.title)
    )
    return list(result)


async def get_story(session: AsyncSession, slug: str) -> Story | None:
    return await session.scalar(
        select(Story).where(Story.slug == slug, Story.rights_status != "excluded")
    )
