"""Public story views. Only catalogue-safe fields: never variants, clues, decisions or endings."""

from pydantic import BaseModel

from backend.app.models import Story


class Inspiration(BaseModel):
    title: str
    author: str
    year: int
    language: str
    source_url: str


class StoryCard(BaseModel):
    slug: str
    title: str
    description: str
    genres: list[str]
    min_players: int
    max_players: int
    est_minutes: int | None
    playable: bool
    inspiration: Inspiration


class RoleOut(BaseModel):
    name: str
    focus: str


class StoryDetail(StoryCard):
    premise: str | None
    roles: list[RoleOut]
    rights_notes: str


def to_card(story: Story) -> StoryCard:
    return StoryCard(
        slug=story.slug,
        title=story.title,
        description=story.description,
        genres=story.genres,
        min_players=story.min_players,
        max_players=story.max_players,
        est_minutes=story.est_minutes,
        playable=story.playable,
        inspiration=Inspiration(
            title=story.inspiration_title,
            author=story.inspiration_author,
            year=story.publication_year,
            language=story.config["rights"]["original_language"],
            source_url=story.source_url,
        ),
    )


def to_detail(story: Story) -> StoryDetail:
    content = story.config.get("content") or {}
    return StoryDetail(
        **to_card(story).model_dump(),
        premise=content.get("premise"),
        roles=[RoleOut(name=r["name"], focus=r["focus"]) for r in content.get("roles", [])],
        rights_notes=story.rights_notes,
    )
