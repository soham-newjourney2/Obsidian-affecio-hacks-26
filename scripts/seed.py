"""Validate every story file and upsert it into the database. Safe to run repeatedly.

uv run python scripts/seed.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.db.session import create_engine, create_sessionmaker  # noqa: E402
from backend.app.services.stories import load_story_files, seed_stories  # noqa: E402


async def main() -> None:
    stories = load_story_files()
    engine = create_engine(get_settings().database_url)
    try:
        async with create_sessionmaker(engine)() as session:
            result = await seed_stories(session, stories)
    finally:
        await engine.dispose()
    print(
        f"stories: {len(stories)} valid; "
        f"{result.created} created, {result.updated} updated, {result.unchanged} unchanged"
    )


if __name__ == "__main__":
    asyncio.run(main())
